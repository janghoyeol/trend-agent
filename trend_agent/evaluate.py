"""정답셋 로드와 채점 (ADR 0003)."""
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .detect import Spike, detect

TOLERANCE_DAYS = 3
EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


@dataclass
class Case:
    id: str
    keyword: str
    source: str  # "user" | "mined"
    verified: bool
    event_start: date
    event_end: date
    window_start: date  # 고정 90일 구간 — 지수가 구간에 따라 바뀌므로 재현용
    window_end: date
    cause: str
    cause_keywords: list[list[str]]
    evidence: list[dict] = field(default_factory=list)  # [{title, link, pubDate}]
    note: str = ""


def _span(case: Case) -> tuple[date, date]:
    tol = timedelta(days=TOLERANCE_DAYS)
    return case.event_start - tol, case.event_end + tol


def detection_hit(case: Case, spikes: list[Spike]) -> bool:
    lo, hi = _span(case)
    return any(s.start <= hi and s.end >= lo for s in spikes)


def _norm(text: str) -> str:
    return "".join(text.split()).lower()


def cause_hit(case: Case, explanation: str, cited_dates: list[date]) -> bool:
    text = _norm(explanation)
    if not all(any(_norm(w) in text for w in group) for group in case.cause_keywords):
        return False
    lo, hi = _span(case)
    return any(lo <= d <= hi for d in cited_dates)


def load_cases(path: Path = EVAL_DIR / "cases.json") -> list[Case]:
    cases = []
    for raw in json.loads(path.read_text(encoding="utf-8")):
        for k in ("event_start", "event_end", "window_start", "window_end"):
            raw[k] = date.fromisoformat(raw[k])
        cases.append(Case(**raw))
    return cases


def load_snapshot(case: Case) -> list[dict]:
    return json.loads((EVAL_DIR / "snapshots" / f"{case.id}.json").read_text(encoding="utf-8"))


def run_detection(case: Case):
    return detect(load_snapshot(case), case.window_start, case.window_end)
