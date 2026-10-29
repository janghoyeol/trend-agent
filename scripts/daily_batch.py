"""하루 1회: 감시 키워드의 최근 급등을 탐지하고 원인을 설명해 data/daily.json에 쓴다 (ADR 0005).

GitHub Actions(.github/workflows/daily.yml)가 실행하고 결과를 data 브랜치에 올린다.
사용법: python scripts/daily_batch.py [--budget 0.04] [--out data/daily.json]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trend_agent.agent import DEFAULT_MODEL, make_client  # noqa: E402
from trend_agent.budget import DailyBudget  # noqa: E402
from trend_agent.service import Service  # noqa: E402

WATCHLIST = [
    # 재난·날씨
    "지진", "산불", "정전", "폭우", "폭염", "태풍", "미세먼지", "싱크홀", "한파", "폭설",
    # 연예·문화
    "넷플릭스", "블랙핑크", "BTS", "뉴진스", "아이유", "노벨상", "영화",
    # 제품·테크
    "아이폰", "갤럭시", "닌텐도", "챗GPT", "테슬라", "카카오톡",
    # 스포츠
    "손흥민", "이강인", "김연경", "야구", "축구",
    # 경제·사회
    "비트코인", "금값", "코스피", "환율", "삼성전자", "부동산", "수능", "최저임금", "파업", "관세",
]
RECENT_DAYS = 3
KST = timezone(timedelta(hours=9))

ap = argparse.ArgumentParser()
ap.add_argument("--budget", type=float, default=float(os.environ.get("BATCH_BUDGET_USD", "0.04")))
ap.add_argument("--model", default=os.environ.get("TREND_MODEL", DEFAULT_MODEL))
ap.add_argument("--out", default=str(ROOT / "data" / "daily.json"))
args = ap.parse_args()


svc = Service(DailyBudget(args.budget), make_client, model=args.model)
items = []
for kw in WATCHLIST:
    r = svc.analyze(kw, recent_days=RECENT_DAYS)
    for s in r.get("spikes", []):
        if s["explain_state"] == "not_requested":
            continue  # 오래된 급등
        items.append({"keyword": kw, "spike": s, "explanation": s.pop("explanation"),
                      "explain_state": s.pop("explain_state")})
        print(f"[{kw}] {s['start']}~{s['end']} {items[-1]['explain_state']}", flush=True)

items.sort(key=lambda it: it["spike"]["peak_date"], reverse=True)
out = {
    "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
    "watchlist_size": len(WATCHLIST), "recent_days": RECENT_DAYS, "model": args.model,
    "spent_usd": round(svc.budget.spent, 4), "items": items,
}
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"급등 {len(items)}건, 비용 ${svc.budget.spent:.4f} → {args.out}")
