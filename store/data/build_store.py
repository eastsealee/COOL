"""플레이스토어 버전 자료 만들기 — 공공 API만 씀 (GitHub Actions '스토어 자료 만들기', 매일 + 3시간마다 날씨)
- 물때: 해양조사원 조석예보(고·저조) tideFcstHghLw — 조석예보 지점(DT_xxxx)별
- 날씨·바람: 기상청 단기예보(3일, 동네예보 격자)
- 수온: 해양조사원 조위관측소 실측(sst 브랜치, 매시간) — 지점 가까운 관측소
- 조류: 해양조사원 조류예보(currents 브랜치) — 지점 가까운 예보점
- 음력·물때 이름: 한국 음력 + 서해 7물때식 / 일출·일몰: 계산
결과(out/, store-data 브랜치): index.json(지점 목록) + p/<코드>.json(그 지점의 날짜별 물때·시간별 날씨·조류·수온)
인증키: Secret DATA_GO_KR_KEY (화면·앱에는 키가 들어가지 않음)
"""
import datetime as dt, gzip, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote
import requests
from korean_lunar_calendar import KoreanLunarCalendar

ROOT = Path(__file__).resolve().parents[2]
KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); (OUT / "p").mkdir(parents=True, exist_ok=True)
KST = dt.timezone(dt.timedelta(hours=9)); NOW = dt.datetime.now(KST); TODAY = NOW.date()
DAYS = [TODAY + dt.timedelta(days=k) for k in range(-4, 31)]
HL = "https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService"
VIL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
RAW = "https://raw.githubusercontent.com/eastsealee/COOL"
log = []


def items_of(j):
    b = j.get("body") or j.get("response", {}).get("body") or {}
    it = b.get("items") or {}
    it = it.get("item", it) if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def call(url, params, tries=3):
    for k in range(tries):
        try:
            r = requests.get(url, params={"serviceKey": KEY, **params}, timeout=30)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return items_of(r.json())
            return []
        except Exception:  # noqa: BLE001
            time.sleep(2 * (k + 1))
    return []


def km(a, b, c, d):
    return 6371 * math.hypot(math.radians(d - b) * math.cos(math.radians((a + c) / 2)), math.radians(c - a))


# ---------- 음력·물때·일출일몰
MUL7 = {1: "7물", 2: "8물", 3: "9물", 4: "10물", 5: "11물", 6: "12물", 7: "13물", 8: "조금", 9: "무시", 10: "1물",
        11: "2물", 12: "3물", 13: "4물", 14: "5물", 15: "6물"}      # 서해 7물때식 (바다타임과 같음: 음력 1·16일 = 7물, 8·23일 = 조금)


def lunar(d):
    c = KoreanLunarCalendar(); c.setSolarDate(d.year, d.month, d.day)
    ld = c.lunarDay
    return f"{c.lunarMonth}.{ld}", MUL7[((ld - 1) % 15) + 1]


def sun(d, lat, lon):
    n = d.timetuple().tm_yday; g = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    la = math.radians(lat)
    ha = math.degrees(math.acos(max(-1, min(1, math.cos(math.radians(90.833)) / (math.cos(la) * math.cos(decl)) - math.tan(la) * math.tan(decl)))))
    noon = 720 - 4 * lon - eqt + 540
    f = lambda m: f"{int(m // 60):02d}:{int(m % 60):02d}"
    return f(noon - 4 * ha), f(noon + 4 * ha)


# ---------- 조류세기 (선상낚시 예약조회와 같은 계산: ▲▼ 변화량 하루 평균 → 불러온 기간 안 최약 0% ~ 최강 100%)
def add_flow(days):
    for d in days.values():
        ds = [abs(e["diff"]) for e in d["tides"]][:4]
        d["_f"] = sum(ds) / len(ds) if ds else None
    fs = [d["_f"] for d in days.values() if d["_f"] is not None]
    lo, hi = (min(fs), max(fs)) if fs else (0, 0)
    for d in days.values():
        f = d.pop("_f")
        d["flow"] = 0 if f is None or hi <= lo else max(0, min(100, round((f - lo) / (hi - lo) * 100)))


# ---------- 기상청 단기예보 → 시간별 날씨 (앱 화면 형식: temp, wspd, wdir, wcode(WMO 비슷하게), precip, is_day)
def kma_grid(lat, lon):
    RE, GRID, S1, S2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    D = math.pi / 180; re_ = RE / GRID; s1, s2, ol, oa = S1 * D, S2 * D, OLON * D, OLAT * D
    sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(math.tan(math.pi / 4 + s2 / 2) / math.tan(math.pi / 4 + s1 / 2))
    sf = math.tan(math.pi / 4 + s1 / 2) ** sn * math.cos(s1) / sn
    ro = re_ * sf / math.tan(math.pi / 4 + oa / 2) ** sn; ra = re_ * sf / math.tan(math.pi / 4 + lat * D / 2) ** sn
    th = lon * D - ol; th = (th + 2 * math.pi) % (2 * math.pi); th = th - 2 * math.pi if th > math.pi else th; th *= sn
    return int(ra * math.sin(th) + XO + .5), int(ro - ra * math.cos(th) + YO + .5)


def kma_base():
    t = NOW - dt.timedelta(minutes=20)
    for k in range(30):
        c = t - dt.timedelta(hours=k)
        if c.hour in (2, 5, 8, 11, 14, 17, 20, 23):
            return c.replace(minute=0)


def wmo(sky, pty, pcp):
    pty = str(pty or "0")
    if pty in ("1", "5"): return 65 if pcp >= 3 else 61
    if pty in ("2", "6"): return 66
    if pty in ("3", "7"): return 71
    if pty == "4": return 80
    return {"1": 0, "3": 2, "4": 3}.get(str(sky or "1"), 1)


def kma_weather(lat, lon, sr_ss):
    nx, ny = kma_grid(lat, lon); base = kma_base()
    its = call(VIL, {"pageNo": 1, "numOfRows": 1500, "dataType": "JSON", "base_date": base.strftime("%Y%m%d"),
                     "base_time": base.strftime("%H00"), "nx": nx, "ny": ny})
    rows = {}
    for it in its:
        rows.setdefault(f"{it['fcstDate']}{it['fcstTime']}", {})[it["category"]] = it["fcstValue"]
    out = []
    for k in sorted(rows):
        r = rows[k]
        try:
            t = f"{k[:4]}-{k[4:6]}-{k[6:8]}T{k[8:10]}:00"
            pcp = r.get("PCP", "0"); pcp = 0.0 if pcp in ("강수없음", None) else float(str(pcp).replace("mm", "").split("~")[0].replace("미만", "").strip() or 0)
            sr, ss = sr_ss.get(t[:10], ("06:30", "18:00"))
            out.append({"time": t, "temp": float(r["TMP"]) if "TMP" in r else None, "hum": float(r.get("REH", 0) or 0),
                        "wspd": float(r["WSD"]) if "WSD" in r else None, "wdir": float(r["VEC"]) if "VEC" in r else None,
                        "wcode": wmo(r.get("SKY"), r.get("PTY"), pcp), "precip": pcp, "wave": float(r["WAV"]) if r.get("WAV") not in (None, "") else None,
                        "is_day": 1 if sr <= t[11:16] < ss else 0, "sst": None, "src": "kma"})
        except (ValueError, KeyError):
            continue
    return out


# ---------- 지점 목록: 조석예보가 나오는 곳
def stations():
    def one(code):
        its = call(HL, {"obsCode": code, "reqDate": TODAY.strftime("%Y%m%d"), "type": "json", "pageNo": 1, "numOfRows": 10})
        return (code, its[0]) if its else None
    codes = [f"DT_{n:04d}" for n in range(1, 100)]
    with ThreadPoolExecutor(6) as ex:
        found = [x for x in ex.map(one, codes) if x]
    return {c: {"name": it.get("obsvtrNm", c), "lat": float(it["lat"]), "lon": float(it["lot"])} for c, it in found}


def tides_for(code):
    ev = []
    for d in [DAYS[0] - dt.timedelta(days=1)] + DAYS:
        for it in call(HL, {"obsCode": code, "reqDate": d.strftime("%Y%m%d"), "type": "json", "pageNo": 1, "numOfRows": 10}):
            try:
                ev.append((str(it["predcDt"])[:16], float(it["predcTdlvVl"]), str(it.get("extrSe", ""))))
            except (KeyError, ValueError):
                pass
    ev = sorted(set(ev))
    days = {}
    for i, (t, h, se) in enumerate(ev):
        prev = ev[i - 1][1] if i else None
        typ = "high" if se in ("1", "3") else "low"
        if t[:10] < DAYS[0].isoformat():
            continue
        days.setdefault(t[:10], []).append({"t": t[11:16], "h": int(round(h)), "type": typ, "diff": int(round(h - prev)) if prev is not None else 0})
    return days


def main():
    if not KEY:
        sys.exit("DATA_GO_KR_KEY 없음")
    st = stations(); print(f"조석예보 지점 {len(st)}곳", flush=True)
    ports = json.loads((ROOT / "personal" / "mulddae" / "data" / "ports.json").read_text(encoding="utf-8"))
    SH = {"충청남도": "충남", "충청북도": "충북", "전라남도": "전남", "전라북도": "전북", "전북특별자치도": "전북", "경상남도": "경남",
          "경상북도": "경북", "제주특별자치도": "제주", "강원특별자치도": "강원", "강원도": "강원", "경기도": "경기", "인천광역시": "인천",
          "부산광역시": "부산", "울산광역시": "울산"}
    try:
        cur = json.loads(gzip.decompress(requests.get(f"{RAW}/currents/currents.json.gz", timeout=30).content))
    except Exception:  # noqa: BLE001
        cur = None
    try:
        sst = requests.get(f"{RAW}/sst/sst.json", timeout=30).json()
    except Exception:  # noqa: BLE001
        sst = None
    index = []

    def build(code):
        s = st[code]; la, lo = s["lat"], s["lon"]
        near = min(ports, key=lambda p: km(la, lo, p["lat"], p["lon"]))
        area, sido = near.get("area", ""), SH.get(near.get("sido", ""), near.get("sido", ""))
        sgg = (near.get("sigungu") or "").split()[0].rstrip("시군구") if near.get("sigungu") else sido
        tid = tides_for(code)
        days, srss = {}, {}
        for d in DAYS:
            k = d.isoformat()
            if k not in tid:
                continue
            lu, mul = lunar(d); sr, ss = sun(d, la, lo); srss[k] = (sr, ss)
            days[k] = {"lunar": lu, "mul": mul, "tides": tid[k], "sunrise": sr, "sunset": ss}
        add_flow(days)
        weather = kma_weather(la, lo, srss)
        # 수온: 가까운 관측소 실측 (35km 안), 앞날은 없음
        sinfo = None
        if sst:
            best = min(((c, km(la, lo, v[1], v[2])) for c, v in sst.get("st", {}).items() if sst["obs"].get(c)), key=lambda x: x[1], default=None)
            if best and best[1] <= 35:
                obs = sst["obs"][best[0]]
                have = {w["time"] for w in weather}
                for t, v in obs.items():
                    tt = t.replace(" ", "T")
                    if tt not in have and tt[:10] >= DAYS[0].isoformat():
                        weather.append({"time": tt, "sst": v, "so": 1, "src": "obs"})
                for w in weather:
                    v = obs.get(w["time"].replace("T", " "))
                    if v is not None:
                        w["sst"], w["so"] = v, 1
                weather.sort(key=lambda w: w["time"])
                sinfo = {"name": sst["st"][best[0]][0], "km": round(best[1], 1), "bias": None, "updated": sst.get("updated")}
        # 조류: 가까운 예보점 (40km 안)
        cinfo = None
        if cur:
            best = min(((c, km(la, lo, v[1], v[2]), v[0]) for c, v in cur.get("st", {}).items() if c in cur.get("sp", {})), key=lambda x: x[1], default=None)
            if best and best[1] <= 40:
                c = best[0]
                cinfo = {"name": best[2], "km": round(best[1], 1), "dirs": cur.get("dirs"), "sp": cur["sp"][c], "dr": cur.get("dr", {}).get(c, {})}
        key = f"{s['name']} ({sgg})" if sgg else s["name"]
        data = {"code": code, "key": key, "name": s["name"], "lat": la, "lon": lo, "area": area, "sido": sido, "sgg": sgg,
                "updated": NOW.strftime("%Y-%m-%d %H:%M"), "days": days, "weather": weather, "cur": cinfo, "sstInfo": sinfo}
        (OUT / "p" / f"{code}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return [key, area, sido, sgg, round(la, 4), round(lo, 4), code, len(days)]

    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(build, sorted(st)):
            if r[7] >= 7:
                index.append(r[:7])
            else:
                log.append(f"{r[6]} {r[0]}: 물때 {r[7]}일뿐이라 뺌")
    index.sort(key=lambda r: (r[1], r[2], r[0]))
    (OUT / "index.json").write_text(json.dumps({"updated": NOW.strftime("%Y-%m-%d %H:%M"), "days": [DAYS[0].isoformat(), DAYS[-1].isoformat()],
                                                "ports": index}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"완료: 지점 {len(index)}곳 · {DAYS[0]}~{DAYS[-1]}", *log, sep="\n")
    if len(index) < 10:
        sys.exit("지점이 너무 적음")


if __name__ == "__main__":
    main()
