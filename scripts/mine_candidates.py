"""정답셋 후보 수집 (ADR 0003). 키워드별 급등을 찾고 급등 기간 기사 제목을 붙인다.

사용법: python scripts/mine_candidates.py  → eval/candidates.json
"""
import html
import json
import re
import sys
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trend_agent.detect import detect  # noqa: E402
from trend_agent.naver import _call, fetch_trend  # noqa: E402

KEYWORDS = {
    "재난·사고": ["지진", "산불", "정전", "폭우", "폭염", "태풍", "미세먼지", "싱크홀"],
    "연예·문화": ["넷플릭스", "오징어게임", "흑백요리사", "노벨상", "블랙핑크", "BTS", "뉴진스", "아이유"],
    "제품·테크": ["아이폰", "갤럭시", "닌텐도", "챗GPT", "GTA6", "테슬라"],
    "스포츠": ["손흥민", "월드컵", "한국시리즈", "이강인", "김연경"],
    "경제": ["비트코인", "금값", "코스피", "삼성전자", "전기요금"],
    "사회": ["수능", "최저임금", "의대", "파업"],
    "사용자 제공": ["두쫀쿠", "암살자들"],
}
START = date(2026, 1, 1)
END = date.today() - timedelta(days=1)


def clean(s):
    return html.unescape(re.sub(r"</?b>", "", s))


def sim_news(keyword, pages=10):
    """sort=sim으로 최대 1,000건 (ADR 0001: 키워드만으로는 과거 도달이 제한적)."""
    out = []
    for p in range(pages):
        items = _call("GET", "search/v1/news",
                      params={"query": keyword, "display": 100, "start": 1 + 100 * p, "sort": "sim"})["items"]
        out += [{"title": clean(i["title"]), "link": i["link"], "pubDate": i["pubDate"],
                 "date": parsedate_to_datetime(i["pubDate"]).date()} for i in items]
        if len(items) < 100:
            break
    return out


def news_in(articles, lo, hi):
    return [{k: a[k] for k in ("title", "link", "pubDate")} for a in articles if lo <= a["date"] <= hi]


def main():
    out = []
    for category, kws in KEYWORDS.items():
        for kw in kws:
            r = detect(fetch_trend(kw, START, END), START, END)
            print(f"[{kw}] {r.reason or ''} 급등 {len(r.spikes)}건", flush=True)
            articles = sim_news(kw) if r.spikes else []
            for s in r.spikes:
                arts = news_in(articles, s.start - timedelta(days=1), s.end + timedelta(days=1))
                out.append({
                    "category": category, "keyword": kw,
                    "start": s.start.isoformat(), "end": s.end.isoformat(), "peak": s.peak_date.isoformat(),
                    "peak_value": s.peak_value, "baseline": s.baseline_median, "ratio": s.ratio,
                    "n_articles": len(arts), "articles": arts[:5],
                })

    (ROOT / "eval").mkdir(exist_ok=True)
    (ROOT / "eval" / "candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n후보 {len(out)}건, 기사 있는 후보 {sum(1 for c in out if c['n_articles'])}건")


if __name__ == "__main__":
    main()
