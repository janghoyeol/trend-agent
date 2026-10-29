"""뉴스 검색 (ADR 0001). 날짜 필터가 없으므로 sort=sim으로 넓게 받고 pubDate로 거른다."""
import html
import re
from datetime import date
from email.utils import parsedate_to_datetime

from .naver import _call

PAGE = 100
PAGES = 5  # start 1~401, 500건 — ADR 0001 실측에서 맥락어와 함께 과거 도달 확인한 범위


def clean(s: str) -> str:
    return html.unescape(re.sub(r"</?b>", "", s))


def search_news(query: str, pages: int = PAGES) -> list[dict]:
    """[{title, description, link, pubDate, date}] — 관련도순 최대 pages×100건."""
    out = []
    for p in range(pages):
        items = _call("GET", "search/v1/news",
                      params={"query": query, "display": PAGE, "start": 1 + PAGE * p, "sort": "sim"})["items"]
        for i in items:
            out.append({
                "title": clean(i["title"]),
                "description": clean(i["description"]),
                "link": i["link"],
                "pubDate": i["pubDate"],
                "date": parsedate_to_datetime(i["pubDate"]).date(),
            })
        if len(items) < PAGE:
            break
    return out


def in_range(articles: list[dict], lo: date, hi: date) -> list[dict]:
    return [a for a in articles if lo <= a["date"] <= hi]
