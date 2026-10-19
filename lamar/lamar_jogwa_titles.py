# -*- coding: utf-8 -*-
"""
라마르피싱 블로그 '오늘의조과'(categoryNo=16) 제목 수집기
- 기간: 2018-01-01 ~ 2026-10-16
- 월: 9~12월만
- 결과: 화면 출력 + lamar_jogwa_9to12.csv (엑셀에서 바로 열림)

실행:  pip install requests   →   python lamar_jogwa_titles.py
"""
import csv
import json
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import unquote_plus

import requests

BLOG_ID = "lamarfishing"
CATEGORY_NO = 16
START = date(2018, 1, 1)
END = date(2026, 10, 16)
MONTHS = {9, 10, 11, 12}
PER_PAGE = 30
OUT_CSV = "lamar_jogwa_9to12.csv"

URL = "https://blog.naver.com/PostTitleListAsync.naver"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": f"https://blog.naver.com/PostList.naver?blogId={BLOG_ID}&categoryNo={CATEGORY_NO}",
}


def parse_date(s: str) -> date | None:
    """'2024. 10. 15.' 형식 또는 '3시간 전', '1일 전' 같은 상대 날짜 처리"""
    s = s.strip()
    m = re.match(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    today = datetime.now().date()
    m = re.match(r"(\d+)\s*일\s*전", s)
    if m:
        return today - timedelta(days=int(m.group(1)))
    if "전" in s:  # 분 전 / 시간 전
        return today
    return None


def fetch_page(page: int) -> dict:
    params = {
        "blogId": BLOG_ID,
        "viewdate": "",
        "currentPage": page,
        "categoryNo": CATEGORY_NO,
        "parentCategoryNo": "",
        "countPerPage": PER_PAGE,
    }
    r = requests.get(URL, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    text = r.text.replace("\\'", "'")  # 네이버 응답의 잘못된 이스케이프 보정
    return json.loads(text)


def main():
    rows = []
    page = 1
    while True:
        data = fetch_page(page)
        posts = data.get("postList", [])
        if not posts:
            break

        oldest_on_page = None
        for p in posts:
            title = unquote_plus(p.get("title", "")).strip()
            d = parse_date(p.get("addDate", ""))
            if d is None:
                continue
            oldest_on_page = d if oldest_on_page is None else min(oldest_on_page, d)
            if START <= d <= END and d.month in MONTHS:
                rows.append({
                    "날짜": d.isoformat(),
                    "제목": title,
                    "링크": f"https://blog.naver.com/{BLOG_ID}/{p.get('logNo')}",
                })

        total = int(data.get("totalCount", 0) or 0)
        print(f"  {page}페이지 처리 (가장 오래된 글: {oldest_on_page}, 누적 {len(rows)}건)")

        # 2018년 이전까지 내려갔거나 마지막 페이지면 종료
        if (oldest_on_page and oldest_on_page < START) or page * PER_PAGE >= total:
            break
        page += 1
        time.sleep(0.4)  # 서버 부담 줄이기

    rows.sort(key=lambda x: x["날짜"])

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["날짜", "제목", "링크"])
        w.writeheader()
        w.writerows(rows)

    print("\n=== 결과 ===")
    cur_year = None
    for r in rows:
        y = r["날짜"][:4]
        if y != cur_year:
            cur_year = y
            print(f"\n[{y}년]")
        print(f"{r['날짜']}  {r['제목']}")
    print(f"\n총 {len(rows)}건 → {OUT_CSV} 저장 완료")


if __name__ == "__main__":
    main()
