"""독자 물때(자체 TideBED) 만들기 전 정확도 시험 — GitHub Actions '자체 물때 시험'
방법(부항 방식): 항구 물때 = 가까운 해양조사원 조석예보 지점(기준항)의 만조·간조를
   ① 시간: 두 곳 M2 분조 위상차 ÷ 28.984°/시  ② 높이: (M2+S2) 진폭비, 평균해면 차
   로 옮겨 계산. 항구·기준항의 분조 상수는 해양조사원 TideBED API(공공누리)에서 한 번 받음
비교: 우리 계산 vs 해양조사원 TideBED 예측(10분 간격) vs 바다타임 표 — 결과 out/tb_report.md
"""
import datetime as dt, json, math, os, re, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote
import requests

ROOT = Path(__file__).resolve().parents[2]
KEY = unquote(os.environ.get("DATA_GO_KR_KEY", "").strip())
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); OUT.mkdir(parents=True, exist_ok=True)
TB = "https://apis.data.go.kr/1192136/tidebed/GetTidebedApiService"
RAW = "https://raw.githubusercontent.com/eastsealee/COOL/store-data/"
KST = dt.timezone(dt.timedelta(hours=9)); TODAY = dt.datetime.now(KST).date()
DAYS = [TODAY + dt.timedelta(days=k) for k in range(0, 3)]
M2W = 28.9841042
log = []


def items_of(j):
    b = j.get("body") or j.get("response", {}).get("body") or {}
    it = b.get("items") or {}
    it = it.get("item", it) if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def tb(lat, lon, d):
    for k in range(3):
        try:
            r = requests.get(TB, params={"serviceKey": KEY, "lat": lat, "lot": lon, "reqDate": d.strftime("%Y%m%d"), "min": 10,
                                         "type": "json", "pageNo": 1, "numOfRows": 200}, timeout=40)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return items_of(r.json())
            log.append(f"TideBED {lat},{lon} {d} → {r.status_code} {r.text[:80]!r}")
            return []
        except Exception:  # noqa: BLE001
            time.sleep(3 * (k + 1))
    return []


def consts(it):
    f = lambda k: float(it.get(k) or 0)
    return {"m2a": f("m2TdlvAmp"), "m2g": f("m2TdlvTlag"), "s2a": f("s2TdlvAmp"), "s2g": f("s2TdlvTlag"),
            "k1a": f("k1TdlvAmp"), "k1g": f("k1TdlvTlag"), "o1a": f("o1TdlvAmp"), "o1g": f("o1TdlvTlag"), "msl": f("msl"),
            "name": it.get("obsvtrNm"), "lat": float(it.get("lat") or 0), "lon": float(it.get("lot") or 0),
            "jogo": it.get("jogo"), "josi": it.get("josi")}


def extremes(series):
    """[(datetime, h)] 10분 간격 → [(datetime, h, 'high'|'low')] (포물선으로 꼭짓점 보정)"""
    out = []
    for i in range(1, len(series) - 1):
        (t0, a), (t1, b), (t2, c) = series[i - 1], series[i], series[i + 1]
        if (b > a and b >= c) or (b < a and b <= c):
            den = a - 2 * b + c
            off = 0.5 * (a - c) / den if den else 0
            out.append((t1 + dt.timedelta(minutes=10 * off), b - 0.25 * (a - c) * off, "high" if b > a else "low"))
    clean = []
    for e in out:        # 작은 출렁임(30분 안 같은 종류) 정리
        if clean and e[2] == clean[-1][2]:
            if (e[2] == "high") == (e[1] > clean[-1][1]):
                clean[-1] = e
            continue
        clean.append(e)
    return clean


def km(a, b, c, d):
    return 6371 * math.hypot(math.radians(d - b) * math.cos(math.radians((a + c) / 2)), math.radians(c - a))


def match(a, b):
    """같은 종류끼리 3시간 안에서 가장 가까운 것 → 시간차(분)·높이차(cm)"""
    dts, dhs = [], []
    for t, h, k in a:
        c = [(abs((t - t2).total_seconds()), t2, h2) for t2, h2, k2 in b if k2 == k and abs((t - t2).total_seconds()) < 3 * 3600]
        if c:
            _, t2, h2 = min(c)
            dts.append((t - t2).total_seconds() / 60); dhs.append(h - h2)
    return dts, dhs


def stat(dts, dhs):
    if not dts:
        return "–", "–", "–", "–", 0
    bias = statistics.mean(dhs)
    return (f"{statistics.mean(abs(x) for x in dts):.0f}분", f"{max(abs(x) for x in dts):.0f}분",
            f"{statistics.mean(abs(x - bias) for x in dhs):.0f}cm", f"{bias:+.0f}cm", len(dts))


ROW_RE = re.compile(r"(?<![가-힣\w])([일월화수목금토])\s+(\d{1,2})\s+(\d{1,2})\.(\d{1,2})\s+(무시|조금|\d{1,2}\s*물)")
TIDE_RE = re.compile(r"(\d{1,2}:\d{2})\s*\(\s*(-?\d+)\s*\)\s*([▲▼])\s*([+-]?\d+)")


def badatime(pid, y, m):
    from bs4 import BeautifulSoup
    r = requests.get(f"https://www.badatime.com/{pid}-{y}-{m:02d}-01.html", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.badatime.com/"}, timeout=30)
    r.encoding = r.apparent_encoding
    s = BeautifulSoup(r.text, "html.parser")
    for x in s(["script", "style"]):
        x.decompose()
    text = re.sub(r"\s+", " ", s.get_text(" "))
    ms = list(ROW_RE.finditer(text)); ev = []
    for i, mm in enumerate(ms):
        day = int(mm.group(2)); chunk = text[mm.end(): ms[i + 1].start() if i + 1 < len(ms) else mm.end() + 400]
        for t in TIDE_RE.finditer(chunk):
            hh, mi = map(int, t.group(1).split(":"))
            try:
                ev.append((dt.datetime(y, m, day, hh, mi), int(t.group(2)), "high" if t.group(3) == "▲" else "low"))
            except ValueError:
                pass
    return sorted(set(ev))


def main():
    idx = requests.get(RAW + "index.json", timeout=30).json()
    st = {p[6]: {"key": p[0], "lat": p[4], "lon": p[5]} for p in idx["ports"]}
    # 기준항 분조 상수 (그 지점 좌표에서 TideBED)
    with ThreadPoolExecutor(6) as ex:
        for code, its in zip(st, ex.map(lambda c: tb(st[c]["lat"], st[c]["lon"], TODAY), list(st))):
            if its:
                st[code]["c"] = consts(its[0])
    st = {c: v for c, v in st.items() if "c" in v}
    print(f"기준항 {len(st)}곳 상수", flush=True)
    ports = json.loads((ROOT / "personal/mulddae/data/ports.json").read_text(encoding="utf-8"))
    want = ["남당항", "오천항", "대천항", "무창포항", "홍원항", "마검포항", "영목항", "구매항", "안흥항", "신진도항", "모항항", "백사장항",
            "궁평항", "전곡항", "영흥도", "선재도", "격포항", "곰소항", "비응항", "야미도", "삼길포항", "학암포", "만리포", "연포",
            "녹동항", "여수항", "통영항", "삼천포항", "강구항", "주문진항", "속초항", "제주항", "성산포항", "도두항"]
    sample = []
    for w in want:
        c = [p for p in ports if p["name"].startswith(w)]
        if c:
            sample.append(c[0])
    rows, detail = [], {}
    for p in sample:
        la, lo = p["lat"], p["lon"]
        series = []
        for d in DAYS:
            its = tb(la, lo, d)
            for it in its:
                try:
                    series.append((dt.datetime.strptime(str(it["obsrvnDt"])[:16], "%Y-%m-%d %H:%M"), float(it["obsrvnHgt"])))
                except (KeyError, ValueError):
                    pass
            if its and "pc" not in p:
                p["pc"] = consts(its[0])
        if not series or "pc" not in p:
            log.append(f"{p['name']}: TideBED 없음"); continue
        truth = extremes(sorted(set(series)))
        pc = p["pc"]
        # 기준항: 같은 바다(100km 안)에서 M2 위상이 가장 가까운 곳 (거리도 조금 반영)
        cands = [(abs(((pc["m2g"] - v["c"]["m2g"]) + 180) % 360 - 180) + km(la, lo, v["lat"], v["lon"]) / 20, c) for c, v in st.items()
                 if km(la, lo, v["lat"], v["lon"]) < 120 and v["c"]["m2a"] > 0]
        if not cands:
            log.append(f"{p['name']}: 기준항 없음"); continue
        _, rc = min(cands); rv = st[rc]["c"]
        lag = (((pc["m2g"] - rv["m2g"]) + 180) % 360 - 180) / M2W                 # 시간
        ratio = (pc["m2a"] + pc["s2a"]) / (rv["m2a"] + rv["s2a"])
        ref = requests.get(RAW + f"p/{rc}.json", timeout=30).json()
        ours = []
        for d in DAYS:
            for e in ref["days"].get(d.isoformat(), {}).get("tides", []):
                t = dt.datetime.strptime(f"{d} {e['t']}", "%Y-%m-%d %H:%M") + dt.timedelta(hours=lag)
                ours.append((t, pc["msl"] + (e["h"] - rv["msl"]) * ratio, e["type"]))
        bada = []
        try:
            b = badatime(p["id"], TODAY.year, TODAY.month)
            bada = [e for e in b if DAYS[0] <= e[0].date() <= DAYS[-1]]
        except Exception as e:  # noqa: BLE001
            log.append(f"{p['name']} 바다타임 실패: {e}")
        truth_in = [e for e in truth if DAYS[0] <= e[0].date() <= DAYS[-1]]
        r1 = stat(*match(ours, truth_in)); r2 = stat(*match(ours, bada)); r3 = stat(*match(truth_in, bada))
        rows.append([p["name"], st[rc]["key"], f"{lag * 60:+.0f}분", f"{ratio:.2f}", *r1, *r2, *r3])
        detail[p["name"]] = {"ref": rc, "lag_min": round(lag * 60, 1), "ratio": round(ratio, 3), "pc": pc, "rc": rv,
                             "ours": [(t.strftime("%m-%d %H:%M"), round(h), k) for t, h, k in ours],
                             "tidebed": [(t.strftime("%m-%d %H:%M"), round(h), k) for t, h, k in truth_in],
                             "badatime": [(t.strftime("%m-%d %H:%M"), h, k) for t, h, k in bada]}
        time.sleep(0.5)
    L = [f"# 자체 물때 시험 — {dt.datetime.now(KST):%Y-%m-%d %H:%M}", "", f"기간 {DAYS[0]} ~ {DAYS[-1]} · 항구 {len(rows)}곳", "",
         "| 항구 | 기준항 | 시간차 | 높이비 | 우리−TideBED 시간(평균) | 최대 | 높이(치우침 뺀) | 치우침 | 수 | 우리−바다타임 시간 | 최대 | 높이 | 치우침 | 수 | TideBED−바다타임 시간 | 최대 | 높이 | 치우침 | 수 |",
         "|" + "---|" * 19]
    L += ["| " + " | ".join(map(str, r)) + " |" for r in rows]
    L += ["", "## 기록"] + [f"- {x}" for x in log[:50]]
    (OUT / "tb_report.md").write_text("\n".join(L), encoding="utf-8")
    (OUT / "tb_detail.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:  # noqa: BLE001
        (OUT / "tb_report.md").write_text("# 실패\n```\n" + traceback.format_exc() + "\n```\n" + "\n".join(log[:50]), encoding="utf-8")
        print(traceback.format_exc())
