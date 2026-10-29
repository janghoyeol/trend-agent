"""실제 검색어트렌드로 급등 탐지를 돌려본다.

사용법: python scripts/detect_live.py 아이폰 날씨 ...
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_agent.detect import detect  # noqa: E402
from trend_agent.naver import fetch_trend  # noqa: E402

end = date.today() - timedelta(days=1)  # 데이터는 어제까지 (ADR 0001)
start = end - timedelta(days=89)

for kw in sys.argv[1:]:
    r = detect(fetch_trend(kw, start, end), start, end)
    print(f"\n[{kw}] {start}~{end} 관측 {r.observed_days}/{len(r.series)}일")
    if r.insufficient:
        print("  데이터 부족 — 탐지하지 않음")
    elif not r.spikes:
        print("  급등 없음")
    for s in r.spikes:
        ratio = f"{s.ratio:.1f}배" if s.ratio is not None else "기준선 0"
        span = f"{s.start}~{s.end}" if s.start != s.end else f"{s.start}"
        print(f"  {span} 대표일 {s.peak_date}: 상대지수 {s.peak_value:g} "
              f"(직전 28일 중앙값 {s.baseline_median:g}, {ratio}, z={s.z:.1f})")
