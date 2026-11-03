"""해양조사원 조류예보(시계열)를 매일 받아 앱이 쓰기 좋게 저장 — GitHub Actions '조류예보 받기'에서 실행
- 인증키: 저장소 Secret DATA_GO_KR_KEY (공공데이터포털 일반 인증키)
- 예보점 목록: mulddae/data/current_stations.json (코드·이름·위도·경도) — 없거나 오래되면 코드를 훑어 새로 만듦
- 결과: out/currents.json.gz (currents 브랜치) — 어제부터 10일 뒤까지, 30분 간격 유속(cm/s)·유향(16방위 번호)
"""
import gzip, json, os, re, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote
import requests

KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); OUT.mkdir(parents=True, exist_ok=True)
ST_FILE = Path(__file__).parent / "data" / "current_stations.json"
TIME = "https://apis.data.go.kr/1192136/crntFcstTime/GetCrntFcstTimeApiService"
FE = "https://apis.data.go.kr/1192136/crntFcstFldEbb/GetCrntFcstFldEbbApiService"
KST = dt.timezone(dt.timedelta(hours=9)); TODAY = dt.datetime.now(KST).date()
DAYS = [TODAY + dt.timedelta(days=k) for k in range(-1, 11)]
DIRS = ["북", "북북동", "북동", "동북동", "동", "동남동", "남동", "남남동", "남", "남남서", "남서", "서남서", "서", "서북서", "북서", "북북서"]


def items_of(j):
    b = j.get("body") or j.get("response", {}).get("body") or {}
    it = b.get("items") or {}
    it = it.get("item", it) if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def call(url, tries=3, **p):
    for k in range(tries):
        try:
            r = requests.get(url, params={"serviceKey": KEY, "type": "json", "pageNo": 1, "numOfRows": 300, **p}, timeout=30)
            return items_of(r.json())
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (k + 1))
    return []


def scan_stations():
    """예보점 코드(예: 16LTC03)를 차례로 불러 살아 있는 것만 모음"""
    codes = [f"{a:02d}LTC{b:02d}" for a in range(1, 61) for b in range(1, 41)]
    found = {}
    def one(c):
        its = call(FE, obsCode=c, numOfRows=1)
        return c, its[0] if its else None
    with ThreadPoolExecutor(6) as ex:
        for c, it in ex.map(one, codes):
            if it:
                found[c] = {"name": it.get("obsvtrNm", c), "lat": float(it["lat"]), "lon": float(it["lot"])}
    return found


def main():
    if not KEY:
        sys.exit("DATA_GO_KR_KEY Secret이 없습니다")
    st = json.loads(ST_FILE.read_text(encoding="utf-8")) if ST_FILE.exists() else {}
    if len(st) < 50 or os.environ.get("RESCAN") == "1":
        st = scan_stations()
        ST_FILE.parent.mkdir(parents=True, exist_ok=True)
        ST_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"예보점 다시 찾음: {len(st)}곳")
    sp, dr = {}, {}

    def one(job):
        code, day = job
        its = call(TIME, obsCode=code, reqDate=day.strftime("%Y%m%d"), min=30)
        s, d = [None] * 48, [None] * 48
        for it in its:
            m = re.search(r"(\d{2}):(\d{2})$", str(it.get("predcDt", "")))
            if not m or not str(it.get("predcDt", "")).startswith(day.isoformat()):
                continue
            i = (int(m.group(1)) * 60 + int(m.group(2))) // 30
            if 0 <= i < 48:
                try:
                    s[i] = round(float(it.get("crsp")), 1)
                except (TypeError, ValueError):
                    pass
                dn = str(it.get("crdir", "")).strip()
                d[i] = DIRS.index(dn) if dn in DIRS else None
        return code, day.isoformat(), s, d

    jobs = [(c, d) for c in st for d in DAYS]
    with ThreadPoolExecutor(6) as ex:
        for n, (code, day, s, d) in enumerate(ex.map(one, jobs), 1):
            if any(v is not None for v in s):
                sp.setdefault(code, {})[day] = s
                dr.setdefault(code, {})[day] = d
            if n % 200 == 0:
                print(f"  {n}/{len(jobs)}", flush=True)
    data = {"updated": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "unit": "cm/s", "step_min": 30,
            "dirs": DIRS, "days": [d.isoformat() for d in DAYS],
            "st": {c: [v["name"], v["lat"], v["lon"]] for c, v in st.items()}, "sp": sp, "dr": dr}
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    (OUT / "currents.json.gz").write_bytes(gzip.compress(raw, 9))
    print(f"완료: 예보점 {len(sp)}/{len(st)}곳 · {len(DAYS)}일 · {len(raw)//1024}KB(압축 전)")
    if len(sp) < len(st) * 0.5:
        sys.exit("받은 예보점이 너무 적습니다")


if __name__ == "__main__":
    main()
