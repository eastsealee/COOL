"""해양조사원 조류예보 API 확인 — 결과는 probe-log 브랜치 (키는 가림)
- 시계열: https://apis.data.go.kr/1192136/crntFcstTime/GetCrntFcstTimeApiService (obsCode, reqDate, min)
- 최강창낙조: https://apis.data.go.kr/1192136/crntFcstFldEbb/GetCrntFcstFldEbbApiService (obsCode)
- 예보점 코드 목록이 따로 없어 'NNLTCmm' 형식을 차례로 불러 보며 살아 있는 코드를 모음
"""
import json, os, re, datetime as dt
from pathlib import Path
from urllib.parse import unquote, quote, quote_plus
from concurrent.futures import ThreadPoolExecutor
import requests

OUT = Path("probe-out"); OUT.mkdir(exist_ok=True)
KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
KST = dt.timezone(dt.timedelta(hours=9)); TODAY = dt.datetime.now(KST).strftime("%Y%m%d")
TIME = "https://apis.data.go.kr/1192136/crntFcstTime/GetCrntFcstTimeApiService"
FE = "https://apis.data.go.kr/1192136/crntFcstFldEbb/GetCrntFcstFldEbbApiService"
log = []

def mask(t):
    t = str(t)
    for k in (KEY, quote(KEY, safe=""), quote_plus(KEY)):
        if k: t = t.replace(k, "***")
    return re.sub(r"(serviceKey=)[^&\s]+", r"\1***", t)

def say(s): print(mask(s)); log.append(mask(s))

def items_of(j):
    b = j.get("body") or j.get("response", {}).get("body") or {}
    it = b.get("items") or {}
    it = it.get("item", it) if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])

def call(url, **p):
    r = requests.get(url, params={"serviceKey": KEY, "type": "json", "pageNo": 1, "numOfRows": 300, **p}, timeout=30)
    try:
        return r.status_code, r.text, items_of(r.json())
    except Exception:
        return r.status_code, r.text, []

# 1) 예시 지점 21LTC01
for name, url, extra in (("최강창낙조", FE, {}), ("시계열", TIME, {"reqDate": TODAY, "min": 30})):
    st, txt, its = call(url, obsCode="21LTC01", **extra)
    say(f"[{name}] 21LTC01 → {st} items={len(its)} | {txt[:300]!r}")
    (OUT / f"sample_{name}.json").write_text(mask(json.dumps(its[:80], ensure_ascii=False, indent=1) if its else txt[:5000]), encoding="utf-8")

# 2) 살아 있는 예보점 코드 찾기 (최강창낙조에 1건만 요청)
def probe(code):
    try:
        st, txt, its = call(FE, obsCode=code, numOfRows=1)
        return code, its[0] if its else None
    except Exception:
        return code, None
codes = [f"{a:02d}LTC{b:02d}" for a in range(1, 46) for b in range(1, 13)]
alive = {}
with ThreadPoolExecutor(6) as ex:
    for code, it in ex.map(probe, codes):
        if it: alive[code] = it
say(f"살아 있는 예보점 {len(alive)}곳: {sorted(alive)[:200]}")
(OUT / "stations.json").write_text(json.dumps(alive, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "log.txt").write_text("\n".join(log), encoding="utf-8")
