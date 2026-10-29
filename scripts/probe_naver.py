"""NAVER API HUB 라이브 스펙 확인용 스크립트 (trend-agent 0단계).

사용법:
    export NAVER_CLIENT_ID=...
    export NAVER_CLIENT_SECRET=...
    python scripts/probe_naver.py

표준 라이브러리만 사용 (설치 불필요). 응답 원문을 그대로 출력해서
문서가 아니라 실제 응답 기준으로 스펙을 확정하는 게 목적.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "https://naverapihub.apigw.ntruss.com"
HEADERS = {
    "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_CLIENT_ID"],
    "X-NCP-APIGW-API-KEY": os.environ["NAVER_CLIENT_SECRET"],
}


def call(method, path, params=None, body=None):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    headers = dict(HEADERS)
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def show(title, result):
    status, payload = result
    print(f"\n===== {title} [HTTP {status}] =====")
    text = json.dumps(payload, ensure_ascii=False, indent=2) if not isinstance(payload, str) else payload
    print(text[:3000])


today = date.today()

# 1) 검색어트렌드 — 일 단위, 최근 90일, 키워드 그룹 2개
show("검색어트렌드 (date, 90일)", call("POST", "search-trend/v1/search", body={
    "startDate": (today - timedelta(days=90)).isoformat(),
    "endDate": today.isoformat(),
    "timeUnit": "date",
    "keywordGroups": [
        {"groupName": "아이폰", "keywords": ["아이폰", "iphone"]},
        {"groupName": "갤럭시", "keywords": ["갤럭시", "galaxy"]},
    ],
}))

# 2) 검색어트렌드 — 가장 오래된 시작일 확인 (예전 문서 기준 2016-01-01)
show("검색어트렌드 (month, 2016~)", call("POST", "search-trend/v1/search", body={
    "startDate": "2016-01-01",
    "endDate": today.isoformat(),
    "timeUnit": "month",
    "keywordGroups": [{"groupName": "마스크", "keywords": ["마스크"]}],
}))

# 3) 성인 검색어 판별
for q in ["날씨", "성인"]:
    show(f"성인 검색어 판별: {q}", call("GET", "search/v1/adult", params={"query": q}))

# 4) 뉴스 — pubDate 형식과 start 상한 근처 동작 확인 (급등일 매칭에 필요)
show("뉴스 sort=date", call("GET", "search/v1/news", params={"query": "아이폰", "display": 3, "sort": "date"}))
show("뉴스 start=1000", call("GET", "search/v1/news", params={"query": "아이폰", "display": 100, "start": 1000, "sort": "date"}))
