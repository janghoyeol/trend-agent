"""NAVER API HUB 클라이언트 (표준 라이브러리만). 스펙은 ADR 0001."""
import json
import os
import urllib.parse
import urllib.request
from datetime import date

BASE = "https://naverapihub.apigw.ntruss.com"


def _call(method, path, params=None, body=None):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_CLIENT_ID"],
        "X-NCP-APIGW-API-KEY": os.environ["NAVER_CLIENT_SECRET"],
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fetch_trend(keyword: str, start: date, end: date) -> list[dict]:
    """키워드 1개의 일별 상대지수. 그룹을 섞으면 스케일이 눌리므로 1개씩만 (ADR 0001)."""
    payload = _call("POST", "search-trend/v1/search", body={
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "timeUnit": "date",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}],
    })
    return payload["results"][0]["data"]


def is_adult(query: str) -> bool:
    return _call("GET", "search/v1/adult", params={"query": query})["adult"] == "1"
