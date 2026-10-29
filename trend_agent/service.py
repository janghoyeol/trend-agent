"""웹·일일 배치 공용 분석 (ADR 0005). 탐지는 무료(네이버)라 항상 하고, Claude 설명만 예산·횟수로 막는다."""
import threading
from collections import defaultdict
from datetime import date, timedelta

from .agent import DEFAULT_MODEL, Explanation, explain, news_window
from .budget import DailyBudget
from .detect import Spike, detect
from .naver import fetch_trend, is_adult

DAYS = 90
MAX_KEYWORD_LEN = 30
IP_DAILY_EXPLAINS = 5


def spike_json(s: Spike) -> dict:
    lo, hi = news_window(s)
    return {
        "start": s.start.isoformat(), "end": s.end.isoformat(), "peak_date": s.peak_date.isoformat(),
        "peak_value": round(s.peak_value, 1), "baseline": round(s.baseline_median, 1),
        "baseline_kind": s.baseline_kind, "news_period": [lo.isoformat(), hi.isoformat()],
    }


def explanation_json(e: Explanation) -> dict:
    return {
        "status": e.status,
        "cause": e.cause,
        "citations": [{"n": i, "title": a["title"], "link": a["link"], "date": a["date"].isoformat()}
                      for i, a in enumerate(e.citations, 1)],
        "searches": [{"query": s["query"], "in_period": s["in_window"]} for s in e.searches],
        "model": e.model,
        "cost_usd": round(e.cost_usd, 5),
        "note": e.note,
    }


def _spike_key(keyword: str, spike: dict) -> tuple:
    return keyword, spike["start"], spike["end"]


class Service:
    def __init__(self, budget: DailyBudget, client_factory, model: str = DEFAULT_MODEL,
                 ip_daily: int = IP_DAILY_EXPLAINS, today=date.today,
                 trend=fetch_trend, adult=is_adult, explain_fn=explain):
        self.budget, self.model, self.ip_daily = budget, model, ip_daily
        self._client_factory, self._client = client_factory, None
        self._today, self._trend, self._adult, self._explain = today, trend, adult, explain_fn
        self._detections: dict[tuple, dict] = {}
        self._explanations: dict[tuple, dict] = {}
        self._ip_count: dict[tuple, int] = defaultdict(int)
        self._lock = threading.Lock()

    def seed(self, keyword: str, spike: dict, explanation: dict) -> None:
        """일일 배치 결과를 캐시에 넣어 같은 급등은 다시 설명하지 않는다."""
        self._explanations[_spike_key(keyword, spike)] = explanation

    def _client_once(self):
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _detect(self, keyword: str) -> tuple[dict, list[Spike]]:
        end = self._today() - timedelta(days=1)  # 데이터는 어제까지 (ADR 0001)
        start = end - timedelta(days=DAYS - 1)
        key = (keyword, end)
        if key not in self._detections:
            if self._adult(keyword):
                self._detections[key] = ({"keyword": keyword, "blocked": True}, [])
            else:
                d = detect(self._trend(keyword, start, end), start, end)
                self._detections[key] = ({
                    "keyword": keyword, "blocked": False,
                    "start": start.isoformat(), "end": end.isoformat(),
                    "series": [[day.isoformat(), round(v, 2)] for day, v in d.series],
                    "insufficient": d.insufficient, "reason": d.reason,
                    "spikes": [spike_json(s) for s in d.spikes],
                }, d.spikes)
        base, spikes = self._detections[key]
        return {**base, "spikes": [dict(s) for s in base.get("spikes", [])]}, spikes

    def analyze(self, keyword: str, ip: str = "", recent_days: int | None = None) -> dict:
        """최근 급등 1건만 설명한다 (나머지는 캐시에 있으면 붙임). recent_days: 이보다 오래된 급등은 설명 안 함."""
        keyword = " ".join(keyword.split())[:MAX_KEYWORD_LEN]
        result, spikes = self._detect(keyword)
        for sj in result.get("spikes", []):
            cached = self._explanations.get(_spike_key(keyword, sj))
            sj["explanation"], sj["explain_state"] = cached, "done" if cached else "not_requested"
        if not spikes:
            return result
        i = max(range(len(spikes)), key=lambda k: spikes[k].start)
        target = result["spikes"][i]
        if target["explanation"] is not None:
            return result
        if recent_days is not None and spikes[i].end < self._today() - timedelta(days=recent_days):
            return result
        target["explain_state"] = self._explain_one(keyword, spikes[i], target, ip)
        return result

    def _explain_one(self, keyword: str, spike: Spike, target: dict, ip: str) -> str:
        day = self._today()
        with self._lock:
            if ip and self._ip_count[(ip, day)] >= self.ip_daily:
                return "rate_limited"
            reserved = self.budget.reserve(self.model)
            if reserved is None:
                return "budget_exhausted"
            if ip:
                self._ip_count[(ip, day)] += 1
        try:
            exp = self._explain(keyword, spike, self._client_once(), model=self.model)
        except Exception as e:  # API 장애 — 비용은 보수적으로 예약액만큼 쓴 것으로
            self.budget.settle(reserved, reserved)
            target["error"] = type(e).__name__
            return "error"
        self.budget.settle(reserved, exp.cost_usd)
        target["explanation"] = explanation_json(exp)
        self._explanations[_spike_key(keyword, target)] = target["explanation"]
        return "done"
