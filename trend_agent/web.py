"""웹 앱 (ADR 0005). 실행: uvicorn trend_agent.web:app"""
import json
import os
import time
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agent import DEFAULT_MODEL, make_client
from .budget import DailyBudget
from .service import MAX_KEYWORD_LEN, Service

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
MODEL = os.environ.get("TREND_MODEL", DEFAULT_MODEL)
LIVE_BUDGET_USD = float(os.environ.get("LIVE_BUDGET_USD", "0.06"))  # 일일 배치 0.04 + 실시간 0.06 = 0.1
DAILY_URL = os.environ.get("DAILY_URL",
                           "https://raw.githubusercontent.com/janghoyeol/trend-agent/data/daily.json")
DAILY_TTL = 600


service = Service(DailyBudget(LIVE_BUDGET_USD), make_client, model=MODEL)
app = FastAPI(title="trend-agent")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_daily = {"at": 0.0, "data": None}


def load_daily() -> dict | None:
    """일일 배치 결과. data 브랜치에서 읽어 재배포 없이 갱신 (없으면 로컬 파일)."""
    if _daily["data"] is not None and time.time() - _daily["at"] < DAILY_TTL:
        return _daily["data"]
    data = None
    try:
        with urllib.request.urlopen(DAILY_URL, timeout=5) as r:
            data = json.loads(r.read())
    except Exception:
        local = ROOT / "data" / "daily.json"
        if local.exists():
            data = json.loads(local.read_text(encoding="utf-8"))
    if data is not None:
        for item in data.get("items", []):
            if item.get("explanation"):
                service.seed(item["keyword"], item["spike"], item["explanation"])
        _daily.update(at=time.time(), data=data)
    return _daily["data"]


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/eval")
def eval_page():
    return FileResponse(STATIC / "eval.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/status")
def status():
    return {"model": MODEL, "live_budget_usd": LIVE_BUDGET_USD,
            "remaining_usd": round(service.budget.remaining, 4)}


@app.get("/api/daily")
def daily():
    return load_daily() or {"items": [], "generated_at": None}


@app.get("/api/analyze")
def analyze(request: Request, q: str = Query(..., min_length=1, max_length=MAX_KEYWORD_LEN)):
    load_daily()
    try:
        return service.analyze(q, ip=_ip(request))
    except OSError as e:  # 네이버 API 장애
        raise HTTPException(502, f"네이버 API 호출 실패: {type(e).__name__}")


@app.get("/api/eval")
def eval_results():
    out = []
    for p in sorted((ROOT / "eval" / "results").glob("*.json")):
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return {"results": out}
