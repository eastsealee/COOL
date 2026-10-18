"""매일 7일치 예상을 저장하고, 실제 블로그 조과와 비교·보정하는 모듈

- GitHub Actions(lamar_daily.yml)가 매일 자정 lamar_update.py 다음에 실행합니다.
- 결과: data/lamar_forecasts.json  (예상한 날 · 대상 날짜 · 예상값)
- 처음 실행할 때(파일이 없을 때)는 2026-09-01 ~ 어제를 "그 전날까지의 기록만으로 예상했다면"으로 채웁니다(백테스트).

앱 페이지도 이 모듈의 WEIGHTS · GG26_FIXED · calibration() 을 같이 씁니다.
"""
import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

BASE = Path(__file__).resolve().parent
DAYS_FILE = BASE / "data" / "lamar_days.json"
FC_FILE = BASE / "data" / "lamar_forecasts.json"
KST = dt.timezone(dt.timedelta(hours=9))

# 월별 분위기 % 가중치: (조과, 본문 분위기, 날씨) — 앱과 공유
WEIGHTS = {9: (0.60, 0.30, 0.10), 10: (0.50, 0.30, 0.20), 11: (0.40, 0.40, 0.20), 12: (0.30, 0.50, 0.20)}
# 2026년 갑오징어 배율 (지정값). 9월은 데이터로 계산
GG26_FIXED = {10: 2.7, 11: 2.0, 12: 2.0}
TIDE_CYCLE = ["7물", "8물", "9물", "10물", "11물", "12물", "13물", "조금", "무시",
              "1물", "2물", "3물", "4물", "5물", "6물"]
CAL_WINDOW = 14          # 보정에 쓰는 최근 비교일 수
CAL_MIN = 3              # 보정을 시작하는 최소 비교일 수
CAL_CLIP = (0.5, 2.0)    # 보정 배율 한계


def _isnan(v):
    return v is None or (isinstance(v, float) and v != v)


def mood_score(r):
    if r.get("basis") == "제목만" or _isnan(r.get("sent")):
        return r.get("score")
    wc, wb, ww = WEIGHTS.get(int(r["date"][5:7]), (0.5, 0.3, 0.2))
    body = r["sent"] if _isnan(r.get("seg_avg")) else (r["sent"] + r["seg_avg"]) / 2
    if _isnan(r.get("catch_pct")):
        wb, ww = wb / (wb + ww), ww / (wb + ww)
        return round(wb * body + ww * r["weather"])
    return round(wc * r["catch_pct"] + wb * body + ww * r["weather"])


def gg26_factor(rows, month):
    if month in GG26_FIXED:
        return GG26_FIXED[month]
    a = [r["gg_med"] for r in rows if r.get("gg_med") is not None and r["date"][:4] == "2026" and int(r["date"][5:7]) == month]
    b = [r["gg_med"] for r in rows if r.get("gg_med") is not None and r["date"][:4] < "2026" and int(r["date"][5:7]) == month]
    if len(a) >= 5 and len(b) >= 5:
        return statistics.mean(a) / statistics.mean(b)
    a = [r["gg_med"] for r in rows if r.get("gg_med") is not None and r["date"][:4] == "2026"]
    ms = {r["date"][5:7] for r in rows if r.get("gg_med") is not None and r["date"][:4] == "2026"}
    b = [r["gg_med"] for r in rows if r.get("gg_med") is not None and r["date"][:4] < "2026" and r["date"][5:7] in ms]
    return statistics.mean(a) / statistics.mean(b) if len(a) >= 5 and b else 1.0


def lunar_mul(d):
    from korean_lunar_calendar import KoreanLunarCalendar
    c = KoreanLunarCalendar()
    c.setSolarDate(d.year, d.month, d.day)
    return TIDE_CYCLE[(c.lunarDay - 1) % 15]


def _wmean(items, key):
    v = [(r[key], w) for r, w in items if r.get(key) is not None and w > 0]
    sw = sum(w for _, w in v)
    return sum(x * w for x, w in v) / sw if v and sw > 0 else None


def predict_one(target, rows, tide):
    """앱의 예상 방식과 같게: 같은 달 기록 중 물세기가 비슷한 날(±12%p)의 가중 평균"""
    pct = (tide.get(target.isoformat()) or {}).get("pct")
    mul = (tide.get(target.isoformat()) or {}).get("mul") or lunar_mul(target)
    hist = [r for r in rows if int(r["date"][5:7]) == target.month]
    if pct is None:                                   # 물세기를 모르면 같은 달·같은 물때 과거 평균으로 추정
        same = [r["_pct"] for r in hist if r.get("_pct") is not None and r.get("_mul") == mul]
        pct = statistics.median(same) if same else None
    items = []
    for r in hist:
        dd = abs(int(r["date"][8:10]) - target.day)
        if pct is not None and r.get("_pct") is not None:
            dp = abs(r["_pct"] - pct)
            if dp <= 12:
                items.append((r, (1 - dd / 40) * (1 - dp / 15)))
        elif pct is None and r.get("_mul") == mul:
            items.append((r, 1 - dd / 40))
    if len(items) < 5:
        items = [(r, 1 - abs(int(r["date"][8:10]) - target.day) / 40) for r in hist]
    out = {k: _wmean(items, k) for k in ("score", "jj_med", "gg_med", "jj_max", "gg_max", "am", "pm")}
    if target.year == 2026:
        f = gg26_factor(rows, target.month)
        for k in ("gg_med", "gg_max"):
            if out[k] is not None:
                out[k] *= f
    out.update(mul=mul, pct=pct, n=len(items))
    return out


def load_rows():
    rows = json.loads(DAYS_FILE.read_text(encoding="utf-8"))
    for r in rows:
        r["score"] = mood_score(r)
    return rows


def attach_tide(rows, tide):
    for r in rows:
        t = tide.get(r["date"]) or {}
        r["_pct"] = t.get("pct")
        r["_mul"] = t.get("mul") or r.get("mul")


def fetch_tide(dates):
    import lamar_badatime as bt
    days, errs = bt.fetch_many(bt.months_for(sorted({dt.date.fromisoformat(x) for x in dates})))
    for e in errs:
        print("물때표 오류:", e)
    return {d.isoformat(): v for d, v in days.items()}


def calibration(fc_rows, actual, before=None):
    """최근 비교일(보정 전 예상 vs 실제)로 주꾸미·갑오징어 보정 배율 계산 → {jj, gg, n}"""
    pairs = []
    for f in fc_rows:
        a = actual.get(f["target"])
        if not a or (before and f["target"] >= before):
            continue
        pairs.append((f["target"], f, a))
    pairs.sort(key=lambda x: x[0])
    out = {"n": 0}
    for key, pk, ak in (("jj", "jj_raw", "jj_med"), ("gg", "gg_raw", "gg_med")):
        v = [(f[pk], a[ak]) for _, f, a in pairs if f.get(pk) and a.get(ak) is not None][-CAL_WINDOW:]
        if len(v) >= CAL_MIN and sum(p for p, _ in v) > 0:
            out[key] = max(CAL_CLIP[0], min(CAL_CLIP[1], sum(x for _, x in v) / sum(p for p, _ in v)))
            out["n"] = max(out["n"], len(v))
        else:
            out[key] = 1.0
    return out


def best_per_target(fc_rows):
    """대상 날짜마다 가장 늦게(가까이) 만든 예상 하나"""
    best = {}
    for f in fc_rows:
        if f["target"] not in best or f["made"] > best[f["target"]]["made"]:
            best[f["target"]] = f
    return best


def make_record(made, target, p, cal, kind):
    jj, gg = p["jj_med"], p["gg_med"]
    return {"made": made.isoformat(), "target": target.isoformat(), "lead": (target - made).days, "kind": kind,
            "mul": p["mul"], "pct": None if p["pct"] is None else round(p["pct"]),
            "score": None if p["score"] is None else round(p["score"]),
            "jj_raw": None if jj is None else round(jj, 1), "gg_raw": None if gg is None else round(gg, 1),
            "jj": None if jj is None else round(jj * cal["jj"], 1), "gg": None if gg is None else round(gg * cal["gg"], 1),
            "jj_max": None if p["jj_max"] is None else round(p["jj_max"]),
            "gg_max": None if p["gg_max"] is None else round(p["gg_max"], 1),
            "am": None if p["am"] is None else round(p["am"]), "pm": None if p["pm"] is None else round(p["pm"]),
            "cal_jj": round(cal["jj"], 3), "cal_gg": round(cal["gg"], 3), "n": p["n"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="며칠치 예상을 만들지 (오늘 포함)")
    ap.add_argument("--backtest-from", default="2026-09-01", help="파일이 없을 때 백테스트 시작일")
    args = ap.parse_args()

    today = dt.datetime.now(KST).date()
    rows = load_rows()
    fc = json.loads(FC_FILE.read_text(encoding="utf-8")) if FC_FILE.exists() else []
    targets = [today + dt.timedelta(days=i) for i in range(args.days)]
    targets = [d for d in targets if d.month in WEIGHTS]
    bt_start = dt.date.fromisoformat(args.backtest_from)
    back = [] if fc else [bt_start + dt.timedelta(days=i) for i in range((today - bt_start).days) if
                          (bt_start + dt.timedelta(days=i)).month in WEIGHTS]
    if not targets and not back:
        print("예상할 날짜 없음 (9~12월만)")
        return 0
    tide = fetch_tide([r["date"] for r in rows] + [d.isoformat() for d in targets + back])
    attach_tide(rows, tide)
    actual = {r["date"]: r for r in rows}
    added = 0

    for d in back:                                     # 백테스트: 그 전날까지의 기록만 사용
        past = [r for r in rows if r["date"] < d.isoformat()]
        cal = calibration(fc, actual, before=d.isoformat())
        fc.append(make_record(d - dt.timedelta(days=1), d, predict_one(d, past, tide), cal, "백테스트"))
        added += 1

    cal = calibration(fc, actual)
    made = today.isoformat()
    fc = [f for f in fc if f["made"] != made]          # 같은 날 다시 돌리면 덮어씀
    for d in targets:
        fc.append(make_record(today, d, predict_one(d, rows, tide), cal, "예상"))
        added += 1

    fc.sort(key=lambda f: (f["target"], f["made"]))
    FC_FILE.write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"예상 {added}건 저장 (전체 {len(fc)}건) · 보정 배율 주꾸미 ×{cal['jj']:.2f} 갑오징어 ×{cal['gg']:.2f} "
          f"(비교 {cal['n']}일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
