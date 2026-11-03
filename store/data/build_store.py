"""플레이스토어 버전 자료 만들기 — 공공 API만 씀 (GitHub Actions '스토어 자료 만들기', 매일 + 3시간마다 날씨)
- 물때: 자체 물때(build_tides.py, 해양조사원 조석예보 + TideBED 상수) — 여기서는 만들지 않음
- 날씨·바람: 기상청 단기예보(3일, 동네예보 격자)
- 수온: 해양조사원 조위관측소 실측(sst 브랜치, 매시간) — 지점 가까운 관측소
- 조류: 해양조사원 조류예보(currents 브랜치) — 지점 가까운 예보점
- 음력·물때 이름: 한국 음력 + 서해 7물때식 / 일출·일몰: 계산
결과(out/, store-data 브랜치): index.json(1,394곳 항구 목록·각 항구의 기준항·날씨 묶음·수온 관측소·조류 예보점 + 라마르 입질 예상)
  + w/<격자>.json(기상청 단기예보, 10km 묶음) + c/<예보점>.json(조류예보)
  물때는 store-tide 브랜치(자체 물때 1년치, build_tides.py), 수온은 sst 브랜치를 앱이 직접 읽음
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
DAYS = [TODAY + dt.timedelta(days=k) for k in range(-4, 31)]   # 입질 확률 예상 날짜
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


def kma_weather(nx, ny):
    """기상청 단기예보 (격자 nx, ny) → 시간별 [시각, 기온, 습도, 풍속, 풍향, 날씨코드, 강수, 파고]"""
    base = kma_base()
    its = call(VIL, {"pageNo": 1, "numOfRows": 1500, "dataType": "JSON", "base_date": base.strftime("%Y%m%d"),
                     "base_time": base.strftime("%H00"), "nx": nx, "ny": ny})
    rows = {}
    for it in its:
        rows.setdefault(f"{it['fcstDate']}{it['fcstTime']}", {})[it["category"]] = it["fcstValue"]
    out = []
    for k in sorted(rows):
        r = rows[k]
        try:
            pcp = r.get("PCP", "0"); pcp = 0.0 if pcp in ("강수없음", None) else float(str(pcp).replace("mm", "").split("~")[0].replace("미만", "").strip() or 0)
            fl = lambda x: float(r[x]) if r.get(x) not in (None, "") else None
            out.append([f"{k[:4]}-{k[4:6]}-{k[6:8]}T{k[8:10]}:00", fl("TMP"), fl("REH"), fl("WSD"), fl("VEC"), wmo(r.get("SKY"), r.get("PTY"), pcp), pcp, fl("WAV")])
        except (ValueError, KeyError):
            continue
    return out


def lamar_pred(st):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lamar_bite as lb
    code = "DT_0025"                     # 보령 — 남당항(라마르호 출항지)과 가장 가까운 조석예보 지점
    recs = json.loads(lb.RECORDS.read_text(encoding="utf-8"))
    months = {d.month for d in DAYS}
    need = sorted({dt.date.fromisoformat(r["date"]) for r in recs if int(r["date"][5:7]) in months} | set(DAYS))
    need = sorted({x for d in need for x in (d - dt.timedelta(days=1), d)})
    try:
        cache = requests.get(f"{RAW}/store-data/lamar_tides.json", timeout=30).json()
    except Exception:  # noqa: BLE001
        cache = {}
    todo = [d for d in need if d.isoformat() not in cache or d >= TODAY - dt.timedelta(days=1)]

    def one(d):
        its = call(HL, {"obsCode": code, "reqDate": d.strftime("%Y%m%d"), "type": "json", "pageNo": 1, "numOfRows": 10})
        return d, [[str(i["predcDt"])[:16], float(i["predcTdlvVl"]), str(i.get("extrSe", ""))] for i in its if i.get("predcDt")]
    with ThreadPoolExecutor(6) as ex:
        for d, v in ex.map(one, todo):
            if v:
                cache[d.isoformat()] = v
    (OUT / "lamar_tides.json").write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    flat = sorted({(t, h, se) for v in cache.values() for t, h, se in v})
    exd = {}
    for i, (t, h, se) in enumerate(flat):
        prev = flat[i - 1][1] if i else None
        tt = dt.datetime.strptime(t, "%Y-%m-%d %H:%M")
        exd.setdefault(tt.date(), []).append((tt, h, "high" if se in ("1", "3") else "low", (h - prev) if prev is not None else 0))
    return lb.predictions(list(DAYS), exd, lambda d: lunar(d)[1])


def main():
    if not KEY:
        sys.exit("DATA_GO_KR_KEY 없음")
    T = requests.get(f"{RAW}/store-tide/ports.json", timeout=60).json()      # 자체 물때(1년치)의 항구 목록
    try:
        cur = json.loads(gzip.decompress(requests.get(f"{RAW}/currents/currents.json.gz", timeout=30).content))
    except Exception:  # noqa: BLE001
        cur = None
    try:
        sst = requests.get(f"{RAW}/sst/sst.json", timeout=30).json()
    except Exception:  # noqa: BLE001
        sst = None
    (OUT / "w").mkdir(exist_ok=True); (OUT / "c").mkdir(exist_ok=True)
    rows, groups = [], {}
    for key, area, sido, sgg, la, lo, pid, ref in T["ports"]:
        nx, ny = kma_grid(la, lo)
        g = f"{nx // 2 * 2}_{ny // 2 * 2}"                 # 10km 묶음 (호출 수 줄이기)
        groups.setdefault(g, (nx, ny))
        sc = None
        if sst:
            b = min(((km(la, lo, v[1], v[2]), c) for c, v in sst.get("st", {}).items() if sst["obs"].get(c)), default=None)
            sc = b[1] if b and b[0] <= 35 else None
        cc = None
        if cur:
            b = min(((km(la, lo, v[1], v[2]), c) for c, v in cur.get("st", {}).items() if c in cur.get("sp", {})), default=None)
            cc = b[1] if b and b[0] <= 40 else None
        rows.append([key, area, sido, sgg, la, lo, pid, ref, g, sc, cc])
    print(f"항구 {len(rows)}곳 · 날씨 묶음 {len(groups)}개", flush=True)
    with ThreadPoolExecutor(6) as ex:
        for g, w in zip(groups, ex.map(lambda xy: kma_weather(*xy), groups.values())):
            if w:
                (OUT / "w" / f"{g}.json").write_text(json.dumps(w, separators=(",", ":")), encoding="utf-8")
    if cur:
        for c in {r[10] for r in rows if r[10]}:
            n, la, lo = cur["st"][c]
            (OUT / "c" / f"{c}.json").write_text(json.dumps({"code": c, "name": n, "lat": la, "lon": lo, "updated": cur.get("updated"), "dirs": cur.get("dirs"),
                                                             "sp": cur["sp"][c], "dr": cur.get("dr", {}).get(c, {})}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    bite = {}
    try:
        bite = lamar_pred(None)
    except Exception as e:  # noqa: BLE001
        log.append(f"라마르 예상 실패: {e}")
    (OUT / "index.json").write_text(json.dumps({"updated": NOW.strftime("%Y-%m-%d %H:%M"), "range": T.get("range"), "refs": T.get("refs"),
                                                "fields": ["항구", "권역", "시도", "시군", "위도", "경도", "id", "기준항", "날씨묶음", "수온관측소", "조류예보점"],
                                                "ports": rows, "bite": bite}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"완료 · {NOW:%F %H:%M}", *log, sep="\n")


if __name__ == "__main__":
    import traceback
    try:
        main()
    except BaseException:  # noqa: BLE001  실패 원인을 파일로 남김 (Actions 기록은 밖에서 못 읽음)
        (OUT / "error.txt").write_text(traceback.format_exc() + "\n" + "\n".join(log[:80]), encoding="utf-8")
        raise
