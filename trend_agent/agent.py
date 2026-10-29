"""급등 원인 설명 에이전트 (ADR 0004).

Claude는 검색어만 고른다. 기사 기간 필터, 인용 검증, 숫자는 전부 코드가 한다.
"""
import json
from dataclasses import dataclass, field
from datetime import date, timedelta

from .detect import Spike
from .news import in_range, search_news

DEFAULT_MODEL = "claude-haiku-5-5"  # 예산 하루 $0.1 → Sonnet은 1~2건뿐 (ADR 0005)
MAX_SEARCHES = 5
ARTICLES_PER_SEARCH = 10
DESC_CHARS = 100  # 입력 토큰 절약: 요약문 앞부분만
HINTS = 5  # 기간 내 기사가 없을 때 맥락어 힌트로 보여줄 기간 밖 제목 수 (인용 불가)
DAYS_BEFORE = 2  # 기사가 검색보다 먼저 나는 경우 (예: 전날 밤 발표)
DAYS_AFTER = 2
PRICES = {  # $/1M tokens (input, output)
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
FALLBACK_MODELS = {"claude-sonnet-5-5"}  # 서버측 거절 폴백 지원 모델 (Haiku는 미지원)

SYSTEM = """당신은 네이버 검색량 급등의 원인을 뉴스 기사로 설명하는 분석가입니다.

- search_news 도구로 기사를 찾으세요. 도구는 급등 기간 전후에 나온 기사만 돌려줍니다.
- 키워드만으로는 과거 기사가 잘 안 잡힙니다. 기간 내 기사가 없으면 out_of_period_hints(인용 불가)를 단서로 쓰세요. 첫 결과에서 단서(인물, 사건, 작품명 등)를 찾으면 \
"키워드 + 맥락어"로 다시 검색하세요. 검색은 최대 {max_searches}회입니다.
- 원인은 도구가 돌려준 기사에 근거해서만 쓰세요. 배경지식으로 추측하지 마세요.
- 근거 기사를 id로 인용하세요 (가장 직접적인 기사 1~3개).
- 검색량 수치(배수, 지수, %)는 쓰지 마세요. 그 숫자는 시스템이 따로 붙입니다.
- 기사로 원인을 확인할 수 없으면 status를 "unknown"으로 답하세요. 지어내는 것보다 낫습니다.
- cause는 한국어 한두 문장, 무슨 일이 있었는지 구체적으로 (누가, 무엇을)."""

SEARCH_TOOL = {
    "name": "search_news",
    "description": "네이버 뉴스를 관련도순으로 검색해 급등 기간 전후 기사만 돌려준다. "
                   "결과: 기간 내 기사 수, 기사 목록[{id, date, title, description}].",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "검색어. 예: '암살자들 역사왜곡'"}},
        "required": ["query"],
        "additionalProperties": False,
    },
}

ANSWER_FORMAT = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["found", "unknown"]},
            "cause": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "cause", "citations"],
        "additionalProperties": False,
    },
}


@dataclass
class Explanation:
    keyword: str
    spike: Spike
    status: str  # "found" | "unknown"
    cause: str
    citations: list[dict]  # 검증된 인용 기사 [{id, title, link, pubDate, date}]
    searches: list[dict] = field(default_factory=list)  # [{query, scanned, in_window}]
    rejected: list[str] = field(default_factory=list)  # 검증에서 탈락한 인용 id
    model: str = DEFAULT_MODEL
    input_tokens: int = 0
    output_tokens: int = 0
    note: str = ""

    @property
    def cost_usd(self) -> float:
        p_in, p_out = PRICES.get(self.model, (0.0, 0.0))
        return (self.input_tokens * p_in + self.output_tokens * p_out) / 1e6


def news_window(spike: Spike) -> tuple[date, date]:
    return spike.start - timedelta(days=DAYS_BEFORE), spike.end + timedelta(days=DAYS_AFTER)


class _NewsTool:
    """검색 실행 + 기사 id 부여. Claude에게 보여준 기사만 인용 가능하다."""

    def __init__(self, lo: date, hi: date, search=search_news):
        self.lo, self.hi, self.search = lo, hi, search
        self.shown: dict[str, dict] = {}
        self._by_link: dict[str, str] = {}
        self.log: list[dict] = []

    def __call__(self, query: str) -> dict:
        found = self.search(query)
        hits = in_range(found, self.lo, self.hi)
        self.log.append({"query": query, "scanned": len(found), "in_window": len(hits)})
        listed = []
        for a in hits[:ARTICLES_PER_SEARCH]:
            aid = self._by_link.get(a["link"])
            if aid is None:
                aid = f"a{len(self.shown) + 1}"
                self._by_link[a["link"]] = aid
                self.shown[aid] = {"id": aid, **a}
            listed.append({"id": aid, "date": a["date"].isoformat(),
                           "title": a["title"], "description": a["description"][:DESC_CHARS]})
        out = {
            "query": query,
            "period": f"{self.lo}~{self.hi}",
            "scanned": len(found),
            "in_period": len(hits),
            "articles": listed,
        }
        if not hits and found:
            near = sorted(found, key=lambda a: min(abs((a["date"] - self.lo).days), abs((a["date"] - self.hi).days)))
            out["out_of_period_hints"] = {
                "note": "기간 밖 기사 제목입니다. 인용할 수 없고, 다음 검색어의 맥락어 단서로만 쓰세요.",
                "titles": [f"{a['date']} {a['title']}" for a in near[:HINTS]],
            }
        return out


def _final_answer(content) -> dict | None:
    texts = [b.text for b in content if b.type == "text"]
    if not texts:
        return None
    try:
        return json.loads(texts[-1])
    except json.JSONDecodeError:
        return None


def explain(keyword: str, spike: Spike, client, model: str = DEFAULT_MODEL, effort: str = "medium",
            search=search_news, max_searches: int = MAX_SEARCHES) -> Explanation:
    lo, hi = news_window(spike)
    tool = _NewsTool(lo, hi, search)
    span = f"{spike.start}~{spike.end}" if spike.start != spike.end else f"{spike.start}"
    messages = [{"role": "user", "content":
                 f"키워드 '{keyword}'의 네이버 검색량이 {span}에 급등했습니다 (정점 {spike.peak_date}). "
                 f"기사 검색 범위: {lo}~{hi}. 원인을 찾아 주세요."}]
    extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} \
        if model in FALLBACK_MODELS else {}
    exp = Explanation(keyword, spike, "unknown", "", [], model=model)
    searches = 0

    for _ in range(max_searches + 3):
        resp = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM.format(max_searches=max_searches),
            tools=[SEARCH_TOOL],
            messages=messages,
            output_config={"effort": effort, "format": ANSWER_FORMAT},
            cache_control={"type": "ephemeral"},
            **extra,
        )
        u = resp.usage
        exp.input_tokens += u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
        exp.output_tokens += u.output_tokens
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "refusal":
            exp.note = "모델이 응답을 거절함"
            break
        if resp.stop_reason == "pause_turn":
            continue
        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            answer = _final_answer(resp.content)
            if answer is None:
                exp.note = f"최종 응답 파싱 실패 (stop_reason={resp.stop_reason})"
            else:
                exp.status, exp.cause = answer["status"], answer["cause"]
                _verify(exp, answer["citations"], tool)
            break
        results = []
        for c in calls:
            searches += 1
            if searches > max_searches:
                results.append({"type": "tool_result", "tool_use_id": c.id, "is_error": True,
                                "content": f"검색 한도({max_searches}회)를 넘었습니다. 지금까지 본 기사로 답하세요."})
                continue
            out = tool(c.input["query"])
            results.append({"type": "tool_result", "tool_use_id": c.id,
                            "content": json.dumps(out, ensure_ascii=False)})
        messages.append({"role": "user", "content": results})
    else:
        exp.note = "반복 한도 초과"

    exp.searches = tool.log
    return exp


def _verify(exp: Explanation, cited: list[str], tool: _NewsTool) -> None:
    """인용 id가 실제로 보여준 기사이고 날짜가 기간 안인지 확인. 근거가 없으면 원인 불명."""
    seen = set()
    for cid in cited:
        a = tool.shown.get(cid)
        if a is None or not (tool.lo <= a["date"] <= tool.hi) or cid in seen:
            exp.rejected.append(cid)
            continue
        seen.add(cid)
        exp.citations.append(a)
    if exp.status == "found" and not exp.citations:
        exp.status = "unknown"
        exp.note = "인용이 검증을 통과하지 못해 원인 불명 처리"
    if exp.status == "unknown":
        exp.citations = []


def _num(v: float) -> str:
    return f"{round(v, 1):g}"


def render(exp: Explanation) -> str:
    """사람이 읽는 요약. 숫자는 탐지 결과에서만 넣는다."""
    s = exp.spike
    span = f"{s.start}~{s.end}" if s.start != s.end else f"{s.start}"
    base = "직전 28일 중앙값" if s.baseline_kind == "rolling" else "직전 4주 같은 요일 중앙값"
    lines = [f"[{exp.keyword}] {span} 급등 — 정점 {s.peak_date} 상대지수 {_num(s.peak_value)} "
             f"({base} {_num(s.baseline_median)})"]
    if exp.status == "found":
        refs = "".join(f"[{i}]" for i in range(1, len(exp.citations) + 1))
        lines.append(f"  원인: {exp.cause} {refs}")
        for i, a in enumerate(exp.citations, 1):
            lines.append(f"  [{i}] {a['date']} {a['title']} — {a['link']}")
    else:
        lines.append("  원인 불명: 기간 내 기사로 원인을 확인하지 못했습니다." + (f" ({exp.note})" if exp.note else ""))
    return "\n".join(lines)


@dataclass
class Report:
    keyword: str
    start: date
    end: date
    blocked: bool = False  # 성인 검색어 게이트
    detection: object = None  # detect.Detection
    explanations: list[Explanation] = field(default_factory=list)


def analyze(keyword: str, client=None, days: int = 90, max_spikes: int = 3, **kw) -> Report:
    """Gate → 트렌드 → 탐지 → 최근 급등부터 원인 설명. LLM은 마지막 단계에서만 호출된다."""
    from .detect import detect
    from .naver import fetch_trend, is_adult

    end = date.today() - timedelta(days=1)  # 데이터는 어제까지 (ADR 0001)
    start = end - timedelta(days=days - 1)
    report = Report(keyword, start, end)
    if is_adult(keyword):
        report.blocked = True
        return report
    report.detection = detect(fetch_trend(keyword, start, end), start, end)
    if report.detection.spikes:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        for s in sorted(report.detection.spikes, key=lambda s: s.start, reverse=True)[:max_spikes]:
            report.explanations.append(explain(keyword, s, client, **kw))
    return report
