# -*- coding: utf-8 -*-
"""
선상24 사전조회 (GitHub Actions에서 몇 시간마다 자동 실행)

1) 선상24 조황정보 게시판(app.sunsang24.com/ship/board)을 깊이 훑어 배 목록을 늘림
   - 이전에 찾은 배는 계속 유지(영구 누적)
2) 모든 배의 이번 달·다음 달 예약현황을 미리 받아 저장
결과: <출력폴더>/ss_ships.json, <출력폴더>/ss_sched.json.gz  → data 브랜치에 저장되고 웹앱이 읽어 씀

파싱 코드는 streamlit_app.py의 것을 그대로 가져와 씀(화면 부분 제외) — 한 곳만 고치면 둘 다 반영됨.
실행: python precrawl.py out
"""
import gzip
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import streamlit as _st                                   # 실제 streamlit을 쓰되, 캐시만 끔(배치 실행이라 필요 없음)

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
HERE = os.path.dirname(os.path.abspath(__file__))


def _passthru(*a, **k):
    if a and callable(a[0]) and not k:
        return a[0]
    return lambda f: f


_st.cache_data = _st.cache_resource = _passthru

# ---- streamlit_app.py의 수집·파싱 함수 불러오기 (화면 코드는 실행하지 않음)
_src = open(os.path.join(HERE, "streamlit_app.py"), encoding="utf-8").read()
_src = _src.split("# ================================================================ 화면")[0]
core = {"__name__": "precrawl_core"}
exec(_src, core)

KST = timezone(timedelta(hours=9))
SEAS = core["SEAS"]
DEEP_PAGES = {"west": 250, "south": 250, "east": 120, "jeju": 80}   # 처음(목록이 적을 때) 깊이
NORMAL_PAGES = 80                                                     # 평소 깊이(새 글 위주)
KEEP_DAYS = 45                                                        # 오늘부터 며칠치 일정 저장


def log(*a):
    print(*a, flush=True)


def crawl_sea(sea, max_pages, found_all):
    empty, new, page = 0, 0, 0
    for page in range(1, max_pages + 1):
        got = core["_ss_board_page"](sea, page)
        if got is None:
            time.sleep(3)
            continue
        for sid, name in got.items():
            k = str(sid)
            if k not in found_all:
                found_all[k] = {"name": name, "sea": sea}
                new += 1
            else:
                found_all[k]["name"] = name or found_all[k]["name"]
        empty = empty + 1 if not got else 0
        if empty >= 2:                                   # 게시판 끝
            break
        time.sleep(0.4)
    log(f"  [{SEAS[sea]}] {page}페이지까지 확인, 새 배 {new}척")


def main():
    os.makedirs(OUT, exist_ok=True)
    now = datetime.now(KST)
    ships_path = os.path.join(OUT, "ss_ships.json")
    try:
        prev = json.load(open(ships_path, encoding="utf-8"))
    except Exception:
        prev = {}
    log(f"이전 배 목록: {len(prev)}척")

    # 1) 배 목록 늘리기
    found = {}
    deep = len(prev) < 300
    with ThreadPoolExecutor(max_workers=2) as ex:
        for sea in SEAS:
            ex.submit(crawl_sea, sea, DEEP_PAGES[sea] if deep else NORMAL_PAGES, found)
    ships = dict(prev)
    for k, v in found.items():
        old = ships.get(k, {})
        ships[k] = {"name": v["name"], "sea": v["sea"],
                    "first_seen": old.get("first_seen", now.strftime("%Y-%m-%d")),
                    "last_seen": now.strftime("%Y-%m-%d")}
    log(f"배 목록: {len(ships)}척 (이번에 새로 {len(set(found) - set(prev))}척)")

    # 2) 예약현황 미리 받기 (이번 달 + 다음 달)
    months = [f"{now.year}{now.month:02d}"]
    nm = now.replace(day=28) + timedelta(days=4)
    months.append(f"{nm.year}{nm.month:02d}")
    today = now.date()
    last_day = today + timedelta(days=KEEP_DAYS)

    def one(item):
        sid, info = item
        sido, sgg, port = core["ss_locate"](info["name"], info["sea"])
        ship = {"site": "ss", "id": int(sid), "name": info["name"], "sea": info["sea"], "sido": sido,
                "sigungu": sgg, "port": port, "hint": ""}
        rows, ok = [], False
        for ym in months:
            try:
                res = core["ss_month"](tuple(sorted(ship.items())), ym)
                ok = ok or bool(res["rows"]) or not res["probe"]
                rows += res["rows"]
            except Exception:
                pass
        keep = []
        for r in rows:
            if today <= r["date"] <= last_day:
                keep.append([r["date"].isoformat(), r["tide"], r["boat"], r["species"], r["time"],
                             r["remain"], r["status"], (r["notice"] or "")[:80]])
        return sid, keep, ok

    sched, ok_n, t0 = {}, 0, time.time()
    with ThreadPoolExecutor(max_workers=3) as ex:
        for i, (sid, keep, ok) in enumerate(ex.map(one, list(ships.items())), 1):
            if keep:
                sched[sid] = keep
            ok_n += ok
            if i % 100 == 0:
                log(f"  예약현황 {i}/{len(ships)} ({time.time() - t0:.0f}초)")
    log(f"예약현황: {len(ships)}척 중 {ok_n}척 응답, 일정 있는 배 {len(sched)}척")

    json.dump(dict(sorted(ships.items(), key=lambda kv: int(kv[0]))), open(ships_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    with gzip.open(os.path.join(OUT, "ss_sched.json.gz"), "wt", encoding="utf-8") as f:
        json.dump({"generated": now.strftime("%Y-%m-%d %H:%M"), "ships": sched}, f, ensure_ascii=False,
                  separators=(",", ":"))
    log("저장 완료:", OUT)


if __name__ == "__main__":
    main()
