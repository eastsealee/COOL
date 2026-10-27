"""조위관측소 실측 수온 받기 — GitHub Actions '실측 수온 받기'에서 매시간 실행
- 해양조사원 '조위관측소 최신 관측데이터'(dtRecent, wtem=수온), 인증키 Secret DATA_GO_KR_KEY
- 결과: out/sst.json (sst 브랜치) — 관측소 위치 + 최근 8일 1시간 간격 수온
  물때 시계는 가까운 관측소 실측으로 지난·오늘 수온을 쓰고, 앞날은 Open-Meteo 예측에 최근 차이를 더해 보정
"""
import datetime as dt, json, os, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote
import requests

KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); OUT.mkdir(parents=True, exist_ok=True)
URL = "https://apis.data.go.kr/1192136/dtRecent/GetDTRecentApiService"
PREV = "https://raw.githubusercontent.com/eastsealee/COOL/sst/sst.json"
KST = dt.timezone(dt.timedelta(hours=9)); NOW = dt.datetime.now(KST); TODAY = NOW.date()
KEEP = 8


def items_of(j):
    b = j.get("body") or j.get("response", {}).get("body") or {}
    it = b.get("items") or {}
    it = it.get("item", it) if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def get(code, day):
    for k in range(3):
        try:
            r = requests.get(URL, params={"serviceKey": KEY, "obsCode": code, "reqDate": day.strftime("%Y%m%d"), "min": 60,
                                          "type": "json", "pageNo": 1, "numOfRows": 300}, timeout=30)
            if r.status_code != 200 or not r.text.lstrip().startswith("{"):
                return code, []
            return code, items_of(r.json())
        except Exception:  # noqa: BLE001
            time.sleep(2 * (k + 1))
    return code, []


def clean(series):
    """고장 값 빼기: 0 근처 값, 하루 내내 같은 값"""
    out = {}
    by_day = {}
    for t, v in series.items():
        by_day.setdefault(t[:10], []).append((t, v))
    for d, tv in by_day.items():
        vals = [v for _, v in tv]
        if len(vals) >= 6 and (max(vals) - min(vals) < 0.01):
            continue
        for t, v in tv:
            if 1.0 < v < 35:
                out[t] = v
    return out


def main():
    if not KEY:
        sys.exit("DATA_GO_KR_KEY 없음")
    try:
        prev = requests.get(PREV, timeout=20).json()
    except Exception:  # noqa: BLE001
        prev = {}
    st = prev.get("st", {})
    obs = prev.get("obs", {})
    full = not st or NOW.hour == 3 or os.environ.get("FULL") == "1"   # 하루 한 번(03시) 관측소 목록·8일치 다시
    codes = [f"DT_{n:04d}" for n in range(1, 100)] if full else list(st)
    days = [TODAY - dt.timedelta(days=k) for k in range(KEEP - 1, -1, -1)] if full else [TODAY - dt.timedelta(days=1), TODAY]
    jobs = [(c, d) for c in codes for d in days] if full else [(c, d) for c in codes for d in days]
    if full:      # 목록 찾기는 오늘 하루만 먼저 훑어서 살아 있는 관측소만 8일치
        with ThreadPoolExecutor(6) as ex:
            alive = [c for c, its in ex.map(lambda c: get(c, TODAY), codes) if its]
        jobs = [(c, d) for c in alive for d in days]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda j: get(*j), jobs))
    for code, its in res:
        s = obs.setdefault(code, {})
        for it in its:
            t = str(it.get("obsrvnDt", ""))[:16]
            try:
                w = float(it.get("wtem"))
            except (TypeError, ValueError):
                continue
            if t.endswith(":00"):
                s[t] = round(w, 2)
            if it.get("lat") and code not in st or (it.get("lat") and full):
                st[code] = [it.get("obsvtrNm", code), float(it["lat"]), float(it["lot"])]
    lo = (TODAY - dt.timedelta(days=KEEP - 1)).isoformat()
    obs = {c: clean({t: v for t, v in s.items() if t[:10] >= lo}) for c, s in obs.items()}
    obs = {c: s for c, s in obs.items() if s and c in st}
    data = {"updated": NOW.strftime("%Y-%m-%d %H:%M"), "unit": "°C", "st": {c: st[c] for c in obs}, "obs": obs}
    (OUT / "sst.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"관측소 {len(obs)}곳, 값 {sum(len(s) for s in obs.values())}개 (full={full})")
    if len(obs) < 5:
        sys.exit("관측소가 너무 적음")


if __name__ == "__main__":
    main()
