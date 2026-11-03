"""자체 물때(독자 TideBED) 1년치 만들기 — Actions '자체 물때 1년치 만들기' (매일 새벽)
항구 물때 = 기준항(해양조사원 조석예보 지점)의 만조·간조를
   시간: 항구·기준항 M2 분조 위상차 ÷ 28.984°/시  만큼 옮기고
   높이: 평균해면 + (기준항 높이 − 기준항 평균해면) × (M2+S2 진폭비)
   (분조 상수: store/data/tb_constants.json, 해양조사원 TideBED에서 받음)
- 기준항 만조·간조는 store-tide 브랜치 ref_hl.json에 쌓아 두고, 빠진 날짜만 하루 최대 BUDGET번 받음
  (해양조사원은 다음 해 12월 31일까지 예보를 줌 → 오늘부터 그때까지 자동으로 채워짐, 해가 바뀌면 다음 해도)
- 결과(store-tide 브랜치): t/<항구id>.json (날짜별 만조·간조), cal.json (음력·물때), ports.json (항구 목록·기준항)
"""
import datetime as dt, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote
import requests
from korean_lunar_calendar import KoreanLunarCalendar

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); (OUT / "t").mkdir(parents=True, exist_ok=True)
HL = "https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService"
PREV = "https://raw.githubusercontent.com/eastsealee/COOL/store-tide/ref_hl.json"
KST = dt.timezone(dt.timedelta(hours=9)); TODAY = dt.datetime.now(KST).date()
START = TODAY - dt.timedelta(days=10)
END = min(TODAY + dt.timedelta(days=400), dt.date(TODAY.year + 1, 12, 31))
BUDGET = int(os.environ.get("BUDGET", "7500"))
M2W = 28.9841042
SIDO = {"서울특별시": "서울", "부산광역시": "부산", "인천광역시": "인천", "울산광역시": "울산", "경기도": "경기", "강원도": "강원",
        "강원특별자치도": "강원", "충청남도": "충남", "충청북도": "충북", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
        "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}
MUL7 = {1: "7물", 2: "8물", 3: "9물", 4: "10물", 5: "11물", 6: "12물", 7: "13물", 8: "조금", 9: "무시", 10: "1물",
        11: "2물", 12: "3물", 13: "4물", 14: "5물", 15: "6물"}


def items_of(j):
    b = j.get("body") or j.get("response", {}).get("body") or {}
    it = b.get("items") or {}
    it = it.get("item", it) if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def hl(code, d):
    for k in range(3):
        try:
            r = requests.get(HL, params={"serviceKey": KEY, "obsCode": code, "reqDate": d.strftime("%Y%m%d"), "type": "json", "pageNo": 1, "numOfRows": 10}, timeout=30)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                if "NODATA" in r.text[:200]:
                    return "nodata"
                return [[str(i["predcDt"])[:16], float(i["predcTdlvVl"]), 1 if str(i.get("extrSe")) in ("1", "3") else 0] for i in items_of(r.json()) if i.get("predcDt")]
            return None
        except Exception:  # noqa: BLE001
            time.sleep(2 * (k + 1))
    return None


def km(a, b, c, d):
    return 6371 * math.hypot(math.radians(d - b) * math.cos(math.radians((a + c) / 2)), math.radians(c - a))


def wrap(x):
    return (x + 180) % 360 - 180


def main():
    if not KEY:
        sys.exit("DATA_GO_KR_KEY 없음")
    C = json.loads((HERE / "tb_constants.json").read_text(encoding="utf-8"))
    refs = C["ref"]
    try:
        cache = requests.get(PREV, timeout=60).json()
    except Exception:  # noqa: BLE001
        cache = {}
    # 1) 기준항 만조·간조 채우기 (가까운 날짜부터)
    dates = [START + dt.timedelta(days=k) for k in range((END - START).days + 1)]
    todo = [(c, d) for d in dates for c in refs if d.isoformat() not in cache.get(c, {})][:BUDGET]
    with ThreadPoolExecutor(6) as ex:
        for (c, d), v in zip(todo, ex.map(lambda j: hl(*j), todo)):
            if isinstance(v, list) and v:
                cache.setdefault(c, {})[d.isoformat()] = v
    for c in cache:                     # 오래된 날짜 정리
        cache[c] = {k: v for k, v in cache[c].items() if k >= START.isoformat()}
    (OUT / "ref_hl.json").write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    left = sum(1 for d in dates for c in refs if d.isoformat() not in cache.get(c, {}))
    print(f"기준항 {len(refs)}곳 · 받은 날짜 {len(todo)}번 요청 · 아직 빈 칸 {left}", flush=True)
    # 2) 항구별 기준항·시간차·높이비
    ports = json.loads((ROOT / "personal/mulddae/data/ports.json").read_text(encoding="utf-8"))
    plist, keys = [], set()
    for p in ports:
        pc = C["ports"].get(str(p["id"]))
        if not pc:
            continue
        la, lo, m2a, m2g, s2a, s2g, msl = pc[1], pc[2], pc[3], pc[4], pc[5], pc[6], pc[7]
        near = sorted((km(la, lo, v[1], v[2]), c) for c, v in refs.items() if c in cache and v[3] > 0)
        if not near:
            continue
        if near[0][0] <= 30:
            rc = near[0][1]
        else:
            cand = [(abs(wrap(m2g - refs[c][4])) + dd / 20, c) for dd, c in near if dd < 120]
            rc = min(cand)[1] if cand else near[0][1]
        rv = refs[rc]
        lag = wrap(m2g - rv[4]) / M2W
        ratio = (m2a + s2a) / (rv[3] + rv[5]) if (rv[3] + rv[5]) > 0 else 1
        # 3) 항구 만조·간조
        ev = []
        for day in sorted(cache[rc]):
            for t, h, hi in cache[rc][day]:
                tt = dt.datetime.strptime(t, "%Y-%m-%d %H:%M") + dt.timedelta(hours=lag)
                ev.append((tt, msl + (h - rv[7]) * ratio, hi))
        ev.sort()
        days = {}
        for i, (tt, h, hi) in enumerate(ev):
            if tt.date() < START:
                continue
            diff = round(h - ev[i - 1][1]) if i else 0
            days.setdefault(tt.date().isoformat(), []).append([tt.strftime("%H:%M"), round(h), hi, diff])
        sido = SIDO.get(p.get("sido", ""), p.get("sido", ""))
        sg = p.get("sigungu", "")
        sg = (sg[:-1] if len(sg) > 2 and sg[-1] in "시군구" else sg) or sido
        key = f"{p['name']} ({sg})" if sg else p["name"]
        if key in keys:
            key = f"{p['name']} ({sg} {p['id']})"
        keys.add(key)
        (OUT / "t" / f"{p['id']}.json").write_text(json.dumps({"id": p["id"], "ref": rc, "lag": round(lag * 60, 1), "ratio": round(ratio, 3),
                                                              "borrow": pc[8], "days": days}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        plist.append([key, p.get("area", ""), sido, sg, round(p["lat"], 4), round(p["lon"], 4), p["id"], rc])
    # 4) 음력·물때
    cal = {}
    for d in dates:
        c = KoreanLunarCalendar(); c.setSolarDate(d.year, d.month, d.day)
        cal[d.isoformat()] = [f"{c.lunarMonth}.{c.lunarDay}", MUL7[((c.lunarDay - 1) % 15) + 1]]
    (OUT / "cal.json").write_text(json.dumps(cal, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "ports.json").write_text(json.dumps({"updated": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "range": [START.isoformat(), END.isoformat()],
                                               "refs": {c: v[0] for c, v in refs.items()}, "ports": plist}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"항구 {len(plist)}곳 · {START} ~ {END}")


if __name__ == "__main__":
    main()
