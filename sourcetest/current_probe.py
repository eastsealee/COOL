"""해양조사원 조류예보 API 확인용 (한 번씩 돌려 보는 것) — 결과는 probe-log 브랜치에 저장
인증키: 저장소 Secret DATA_GO_KR_KEY (공공데이터포털 일반 인증키)
1) 데이터셋 상세 페이지에서 요청 주소·변수 이름 찾기  2) 여러 조합으로 불러 보기  3) 원본 응답 저장(키는 가림)
"""
import json, os, re, datetime as dt
from pathlib import Path
from urllib.parse import unquote, quote, quote_plus
import requests

OUT = Path("probe-out"); OUT.mkdir(exist_ok=True)
KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
UA = {"User-Agent": "Mozilla/5.0 (COOL current probe)"}
KST = dt.timezone(dt.timedelta(hours=9)); TODAY = dt.datetime.now(KST).strftime("%Y%m%d")
log = []

def mask(t):
    t = str(t)
    for k in (KEY, quote(KEY, safe=""), quote_plus(KEY)):
        if k: t = t.replace(k, "***")
    return re.sub(r"(serviceKey=)[^&\s]+", r"\1***", t)

def say(s): print(s); log.append(mask(s))

DATASETS = {"15156024": "조류예보(시계열)", "15156025": "조류예보 최강창낙조 및 전류"}
found = {}
for ds, name in DATASETS.items():
    urls, params = set(), set()
    for page in (f"https://www.data.go.kr/data/{ds}/openapi.do", f"https://www.data.go.kr/en/data/{ds}/openapi.do",
                 f"https://www.data.go.kr/catalog/{ds}/openapi.json"):
        try:
            t = requests.get(page, headers=UA, timeout=30).text
        except Exception as e:
            say(f"{ds} page fail {page}: {e}"); continue
        (OUT / f"page_{ds}_{len(urls)}_{page.split('/')[-1]}.txt").write_text(t, encoding="utf-8")
        urls |= set(re.findall(r"https?://apis\.data\.go\.kr/1192136/[A-Za-z0-9_/]+", t))
        for base in re.findall(r"/1192136/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)?", t):
            urls.add("https://apis.data.go.kr" + base)
        params |= set(re.findall(r"\"name\"\s*:\s*\"([A-Za-z_][A-Za-z0-9_]*)\"", t))
        # 오퍼레이션/요청변수 표에 있는 영문 변수 이름 후보
        params |= set(re.findall(r">\s*([a-z][A-Za-z0-9]{2,20})\s*<", t)) & {"obsCode", "obsPostId", "reqDate", "date", "min", "type",
                                                                             "pageNo", "numOfRows", "lat", "lon", "crntPntCode", "obsvtrCode", "obsCd", "pointCode"}
    found[ds] = sorted(urls)
    say(f"[{name}] 주소 후보: {sorted(urls)}")
    say(f"[{name}] 변수 후보: {sorted(params)[:60]}")

# 불러 보기 — 지점코드를 모를 때 흔한 이름들로
def items_of(j):
    try:
        b = j.get("body") or j.get("response", {}).get("body") or {}
        it = b.get("items") or {}
        it = it.get("item", it) if isinstance(it, dict) else it
        return it if isinstance(it, list) else ([it] if it else [])
    except Exception:
        return []

tries = [
    {"type": "json", "pageNo": 1, "numOfRows": 20},
    {"type": "json", "pageNo": 1, "numOfRows": 20, "reqDate": TODAY},
    {"type": "json", "pageNo": 1, "numOfRows": 20, "reqDate": TODAY, "min": 10},
]
codes = ["", "16LTC03", "07KS-1", "23LTC01", "15LTC02", "DT_0025"]
for ds, urls in found.items():
    for u in urls:
        for code in codes:
            for v in tries:
                for ck in (["obsCode", "obsPostId", "crntPntCode"] if code else [None]):
                    p = {"serviceKey": KEY, **v}
                    if ck: p[ck] = code
                    try:
                        r = requests.get(u, params=p, headers=UA, timeout=30)
                    except Exception as e:
                        say(f"{u} 실패 {e}"); continue
                    its = items_of(r.json()) if r.headers.get("content-type", "").startswith("application/json") or r.text.strip().startswith("{") else []
                    head = mask(r.text[:400]).replace("\n", " ")
                    say(f"{u.split('1192136/')[-1]} {ck}={code} {list(v)} → {r.status_code} items={len(its)} | {head}")
                    if its:
                        (OUT / f"ok_{ds}_{ck}_{code}.json").write_text(mask(json.dumps(its[:50], ensure_ascii=False, indent=1)), encoding="utf-8")
                        break
(OUT / "log.txt").write_text("\n".join(log), encoding="utf-8")
