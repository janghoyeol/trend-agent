"""정답셋 원인 적중률 (ADR 0003 채점, ADR 0004 에이전트). 실제 Claude + 네이버 뉴스 호출.

사용법: python scripts/eval_cause.py [--model claude-haiku-5-5] [--effort medium] [--only id1,id2]
결과: eval/results/<model>-<effort>.json  (사례별 원인·인용·검색어·토큰·비용)

- 탐지가 놓친 사례는 Claude를 부르지 않고 오답 처리 (end-to-end).
- cause_eval=false 사례(비상계엄)는 제외.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402

from trend_agent.agent import DEFAULT_MODEL, explain  # noqa: E402
from trend_agent.evaluate import _span, cause_hit, load_cases, run_detection  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--model", default=DEFAULT_MODEL)
ap.add_argument("--effort", default="medium")
ap.add_argument("--only", default="")
args = ap.parse_args()

only = set(filter(None, args.only.split(",")))
cases = [c for c in load_cases() if c.verified and c.cause_eval and (not only or c.id in only)]
client = anthropic.Anthropic()
rows, hits, detected, cost = [], 0, 0, 0.0
for c in cases:
    lo, hi = _span(c)
    spikes = [s for s in run_detection(c).spikes if s.start <= hi and s.end >= lo]
    if not spikes:
        rows.append({"id": c.id, "detected": False, "hit": False, "label": c.cause})
        print(f"- {c.id:16} 탐지 못함 → 오답", flush=True)
        continue
    detected += 1
    spike = min(spikes, key=lambda s: abs((s.start - c.event_start).days))
    exp = explain(c.keyword, spike, client, model=args.model, effort=args.effort)
    hit = exp.status == "found" and cause_hit(c, exp.cause, [a["date"] for a in exp.citations])
    hits += hit
    cost += exp.cost_usd
    rows.append({
        "id": c.id, "detected": True, "hit": hit, "status": exp.status, "cause": exp.cause,
        "label": c.cause, "citations": [{k: a[k] for k in ("title", "link", "pubDate")} for a in exp.citations],
        "rejected": exp.rejected, "searches": exp.searches, "note": exp.note,
        "input_tokens": exp.input_tokens, "output_tokens": exp.output_tokens, "cost_usd": round(exp.cost_usd, 5),
    })
    queries = " / ".join(s["query"] for s in exp.searches)
    print(f"{'O' if hit else 'X'} {c.id:16} [{exp.status}] {exp.cause[:60]}  (검색: {queries}) ${exp.cost_usd:.4f}",
          flush=True)

n = len(cases)
summary = {
    "model": args.model, "effort": args.effort, "cases": n, "detected": detected, "cause_hits": hits,
    "cause_hit_rate": round(hits / n, 3) if n else None,
    "cause_hit_rate_given_detected": round(hits / detected, 3) if detected else None,
    "total_cost_usd": round(cost, 4),
}
print(f"\n원인 적중 {hits}/{n}" + (f" = {hits / n:.0%}" if n else "")
      + f"  (탐지된 {detected}건 중 {hits}건)  비용 ${cost:.3f}")
out = ROOT / "eval" / "results" / f"{args.model}-{args.effort}.json"
if not only:
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {out.relative_to(ROOT)}")
