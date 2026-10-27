"""수온 비교 — 지금 앱(Open-Meteo 해양 모델) vs 국립해양조사원 조위관측소 실측 수온
GitHub Actions '수온 비교'에서 실행. 인증키 Secret DATA_GO_KR_KEY. 결과: out/sst_report.md, out/sst_raw.json
실측: https://apis.data.go.kr/1192136/dtRecent/GetDTRecentApiService (조위관측소 최신 관측데이터, wtem=수온)
"""
import datetime as dt, json, os, statistics, sys, time
from pathlib import Path
from urllib.parse import unquote
import requests

KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); OUT.mkdir(parents=True, exist_ok=True)
URL = "https://apis.data.go.kr/1192136/dtRecent/GetDTRecentApiService"
KST = dt.timezone(dt.timedelta(hours=9)); TODAY = dt.datetime.now(KST).date()
DAYS = [TODAY - dt.timedelta(days=k) for k in range(7, 0, -1)]
# 서해 중부 위주 + 남해·동해·제주 몇 곳 (코드가 틀리면 건너뜀)
CODES = ["DT_0025", "DT_0067", "DT_0017", "DT_0050", "DT_0001", "DT_0018", "DT_0007", "DT_0016", "DT_0005", "DT_0004", "DT_0006", "DT_0011"]
log = []


def items_of(j):
    b = j.get("body") or j.get("response", {}).get("body") or {}
    it = b.get("items") or {}
    it = it.get("item", it) if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def obs(code, day):
    for k in range(3):
        try:
            r = requests.get(URL, params={"serviceKey": KEY, "obsCode": code, "reqDate": day.strftime("%Y%m%d"), "min": 60,
                                          "type": "json", "pageNo": 1, "numOfRows": 300}, timeout=30)
            if r.status_code != 200 or not r.text.strip().startswith("{"):
                log.append(f"{code} {day} → HTTP {r.status_code} {r.text[:160]!r}")
                return []
            return items_of(r.json())
        except Exception as e:  # noqa: BLE001
            log.append(f"{code} {day} → {e}")
            time.sleep(2)
    return []


def model(lat, lon, start, end):
    r = requests.get("https://marine-api.open-meteo.com/v1/marine", params={
        "latitude": lat, "longitude": lon, "hourly": "sea_surface_temperature", "timezone": "Asia/Seoul",
        "start_date": start, "end_date": end}, timeout=30).json()
    h = r.get("hourly", {})
    return {t.replace("T", " "): v for t, v in zip(h.get("time", []), h.get("sea_surface_temperature", []))}, r.get("latitude"), r.get("longitude")


rows, raw = [], {}
for code in CODES:
    meas, name, la, lo = {}, code, None, None
    for d in DAYS:
        for it in obs(code, d):
            t = str(it.get("obsrvnDt", ""))[:16]
            try:
                w = float(it.get("wtem"))
            except (TypeError, ValueError):
                continue
            if -2 < w < 35 and t.endswith(":00"):
                meas[t] = w
            name = it.get("obsvtrNm", name)
            la, lo = la or it.get("lat"), lo or it.get("lot")
    if not meas or la is None:
        log.append(f"{code}: 실측 수온 없음")
        continue
    m, mla, mlo = model(float(la), float(lo), DAYS[0].isoformat(), DAYS[-1].isoformat())
    pairs = [(meas[t], m[t]) for t in meas if m.get(t) is not None]
    if not pairs:
        log.append(f"{code} {name}: 모델 값 없음 (해안이라 격자가 육지일 수 있음, 모델 격자 {mla},{mlo})")
        rows.append([name, code, len(meas), None, None, None, None, None])
        continue
    dif = [b - a for a, b in pairs]
    # 하루 평균끼리 (앱 화면은 하루 평균 수온을 보여줌)
    dm = {}
    for t in meas:
        if m.get(t) is not None:
            dm.setdefault(t[:10], []).append((meas[t], m[t]))
    ddif = [statistics.mean(b for _, b in v) - statistics.mean(a for a, _ in v) for v in dm.values()]
    rows.append([name, code, len(pairs), round(statistics.mean(a for a, _ in pairs), 1), round(statistics.mean(b for _, b in pairs), 1),
                 round(statistics.mean(abs(x) for x in dif), 2), round(statistics.mean(dif), 2), round(max(abs(x) for x in ddif), 2)])
    raw[code] = {"name": name, "lat": la, "lon": lo, "model_grid": [mla, mlo], "meas": meas, "model": {t: m.get(t) for t in meas}}

L = [f"# 수온 비교 — {dt.datetime.now(KST):%Y-%m-%d %H:%M} KST", "",
     f"기간: {DAYS[0]} ~ {DAYS[-1]} (7일, 1시간 간격) · 실측 = 해양조사원 조위관측소 · 모델 = Open-Meteo 해양(지금 앱)", "",
     "| 관측소 | 코드 | 비교 수 | 실측 평균 | 모델 평균 | 오차(평균) | 치우침(모델−실측) | 하루 평균 최대 차이 |", "|---|---|---|---|---|---|---|---|"]
for r in rows:
    L.append("| " + " | ".join("–" if v is None else (f"{v}°C" if i in (3, 4, 5, 6, 7) else str(v)) for i, v in enumerate(r)) + " |")
L += ["", "## 기록"] + [f"- {x}" for x in log[:60]]
(OUT / "sst_report.md").write_text("\n".join(L), encoding="utf-8")
(OUT / "sst_raw.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
print("\n".join(L))
