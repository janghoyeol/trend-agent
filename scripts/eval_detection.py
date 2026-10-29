"""정답셋 탐지 적중률 (스냅샷으로 오프라인 실행, ADR 0003).

사용법: python scripts/eval_detection.py [--all]   (--all: 미검수 사례 포함)
"""
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_agent.evaluate import cause_hit, detection_hit, load_cases, run_detection  # noqa: E402

cases = [c for c in load_cases() if c.verified or "--all" in sys.argv]
hits = 0
for c in cases:
    r = run_detection(c)
    hit = detection_hit(c, r.spikes)
    hits += hit
    near = [f"{s.start}~{s.end}" for s in r.spikes]
    # 라벨 점검: 근거 기사만으로 원인 적중이 되어야 핵심어가 현실적이다
    titles = " ".join(e["title"] for e in c.evidence)
    dates = [parsedate_to_datetime(e["pubDate"]).date() for e in c.evidence]
    label_ok = cause_hit(c, titles, dates)
    print(f"{'O' if hit else 'X'} {c.id:16} {c.event_start}~{c.event_end}  급등 {near or r.reason or '없음'}"
          f"{'' if label_ok else '  [라벨: 근거 기사에 핵심어 없음]'}")
print(f"\n탐지 적중 {hits}/{len(cases)}" + (f" = {hits / len(cases):.0%}" if cases else ""))
