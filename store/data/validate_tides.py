"""자체 물때(store-tide) vs 바다타임 대조 — 이번 달·다음 달, 서해 낚시 항구 위주 → out/validate.md"""
import datetime as dt, json, re, statistics, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tidebed_probe import badatime, match, stat   # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out"); OUT.mkdir(parents=True, exist_ok=True)
RAW = "https://raw.githubusercontent.com/eastsealee/COOL/store-tide/"
KST = dt.timezone(dt.timedelta(hours=9)); T = dt.datetime.now(KST).date()
idx = requests.get(RAW + "ports.json", timeout=60).json()
want = ["남당항", "오천항", "대천항", "무창포항", "홍원항", "마검포항", "영목항", "안흥항", "신진도", "모항항", "백사장항", "궁평항", "전곡항",
        "영흥도", "선재도", "격포항", "곰소항", "비응항", "야미도", "삼길포항", "학암포", "만리포항", "연포", "어청도", "외연도", "녹동항", "여수", "통영", "주문진항", "제주항"]
rows, alls = [], ([], [])
months = [(T.year, T.month), ((T.replace(day=28) + dt.timedelta(days=5)).year, (T.replace(day=28) + dt.timedelta(days=5)).month)]
for w in want:
    cand = [p for p in idx["ports"] if p[0].startswith(w)]
    if not cand:
        continue
    key, area, sido, sgg, la, lo, pid, ref = cand[0]
    t = requests.get(RAW + f"t/{pid}.json", timeout=30).json()
    ours = [(dt.datetime.strptime(f"{d} {e[0]}", "%Y-%m-%d %H:%M"), e[1], "high" if e[2] else "low") for d, ev in t["days"].items() for e in ev]
    bada = []
    for y, m in months:
        try:
            bada += badatime(pid, y, m)
        except Exception:  # noqa: BLE001
            pass
    lo_d, hi_d = T, T + dt.timedelta(days=40)
    a = [e for e in ours if lo_d <= e[0].date() <= hi_d]; b = [e for e in bada if lo_d <= e[0].date() <= hi_d]
    dts, dhs = match(a, b); alls[0].extend(dts); alls[1].extend(dhs)
    rows.append([key, idx["refs"].get(ref, ref), f"{t['lag']:+.0f}분", t["ratio"], "빌림" if t.get("borrow") else "", *stat(dts, dhs)])
L = [f"# 자체 물때 vs 바다타임 — {dt.datetime.now(KST):%Y-%m-%d %H:%M}", "", f"기간 {T} ~ {T + dt.timedelta(days=40)} (40일)", "",
     "| 항구 | 기준항 | 시간차 | 높이비 | 상수 | 시간 오차(평균) | 최대 | 높이 오차 | 높이 치우침 | 비교 수 |", "|" + "---|" * 10]
L += ["| " + " | ".join(map(str, r)) + " |" for r in rows]
if alls[0]:
    L += ["", f"**전체** 시간 오차 평균 {statistics.mean(abs(x) for x in alls[0]):.1f}분 · 중앙값 {statistics.median(abs(x) for x in alls[0]):.0f}분 · 10분 안 {sum(1 for x in alls[0] if abs(x) <= 10) / len(alls[0]) * 100:.0f}% · 비교 {len(alls[0])}번"]
(OUT / "validate.md").write_text("\n".join(L), encoding="utf-8"); print("\n".join(L))
