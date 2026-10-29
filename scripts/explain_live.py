"""키워드 하나를 끝까지 돌린다: 성인 게이트 → 90일 트렌드 → 급등 탐지 → Claude 원인 설명.

사용법: python scripts/explain_live.py 키워드 [--model claude-haiku-5-5]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_agent.agent import DEFAULT_MODEL, analyze, render  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("keyword")
ap.add_argument("--model", default=DEFAULT_MODEL)
args = ap.parse_args()

r = analyze(args.keyword, model=args.model)
print(f"[{r.keyword}] {r.start}~{r.end}")
if r.blocked:
    print("  성인 검색어로 판별되어 분석하지 않습니다.")
elif r.detection.insufficient:
    print(f"  판단 불가 ({r.detection.reason})")
elif not r.detection.spikes:
    print("  급등 없음")
for e in r.explanations:
    print(render(e))
    print(f"  검색: {' / '.join(f'{s['query']}({s['in_window']})' for s in e.searches)}"
          f"  토큰 {e.input_tokens}+{e.output_tokens} ${e.cost_usd:.4f}")
