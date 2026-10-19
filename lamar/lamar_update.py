"""라마르호 블로그 새 '오늘의 조과' 글을 가져와 data/lamar_days.json 에 추가

GitHub Actions(.github/workflows/lamar_daily.yml)가 매일 1번 실행합니다.
직접 실행:  python lamar_update.py            (최근 글 확인)
            python lamar_update.py --days 60  (최근 60일 글까지 다시 확인)
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote_plus

import requests
from bs4 import BeautifulSoup

import lamar_analyze as la

BLOG_ID = "lamarfishing"
DATA = Path(__file__).resolve().parent / "data" / "lamar_days.json"
MONTHS = {9, 10, 11, 12}                     # 분석 대상 달 (기존 데이터와 같게 9~12월)
KST = dt.timezone(dt.timedelta(hours=9))
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": f"https://blog.naver.com/{BLOG_ID}",
}
TITLE_DATE = re.compile(r"^(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.")


def get(url, params=None, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if r.status_code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 * (i + 1))
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def posted_date(s, today):
    s = (s or "").strip()
    m = re.match(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", s)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d+)\s*일\s*전", s)
    if m:
        return today - dt.timedelta(days=int(m.group(1)))
    if "전" in s or "방금" in s:
        return today
    return None


def list_posts(since, today, max_pages=40):
    """블로그 전체 글 목록에서 since 이후 게시된 글 (최신순)"""
    out, seen = [], set()
    for page in range(1, max_pages + 1):
        txt = get("https://blog.naver.com/PostTitleListAsync.naver",
                  {"blogId": BLOG_ID, "viewdate": "", "currentPage": page, "categoryNo": 0,
                   "parentCategoryNo": "", "countPerPage": 30})
        data = json.loads(txt.replace("\\'", "'"))
        posts = data.get("postList") or []
        if not posts:
            break
        newest = None
        for p in posts:
            pd_ = posted_date(p.get("addDate"), today)
            if pd_ is None:
                continue
            newest = pd_ if newest is None or pd_ > newest else newest
            if pd_ < since or p["logNo"] in seen:
                continue
            seen.add(p["logNo"])
            out.append({"logNo": p["logNo"], "posted": pd_,
                        "title": unquote_plus(p.get("title") or "").strip()})
        if newest is not None and newest < since:
            break
        if page * 30 >= int(data.get("totalCount") or 0):
            break
        time.sleep(0.3)
    return out


def read_post(log_no):
    """글 본문 (처음 데이터를 모을 때 쓴 브라우저 코드와 같은 방식으로 문단을 읽음)"""
    html = get("https://blog.naver.com/PostView.naver", {"blogId": BLOG_ID, "logNo": log_no})
    soup = BeautifulSoup(html, "html.parser")
    t = soup.select_one(".se-title-text, .pcol1, .htitle")
    box = soup.select_one(".se-main-container") or soup.select_one("#postViewArea") or soup.select_one(".post-view")
    body = ""
    if box:
        paras = box.select(".se-text-paragraph, p, div.se-module-text")
        if paras:
            body = "\n".join(x for x in (p.get_text().strip() for p in paras) if x)
        else:
            body = box.get_text()
    body = re.sub(r"\n{3,}", "\n\n", body.replace("​", "")).strip()
    return (t.get_text().strip() if t else ""), body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10, help="최근 며칠 동안 게시된 글을 확인할지")
    args = ap.parse_args()

    rows = json.loads(DATA.read_text(encoding="utf-8"))
    known = {r["link"] for r in rows}
    today = dt.datetime.now(KST).date()
    since = today - dt.timedelta(days=args.days)

    added = []
    for p in list_posts(since, today):
        link = f"https://blog.naver.com/{BLOG_ID}/{p['logNo']}"
        if link in known:
            continue
        title = p["title"]
        if title and not TITLE_DATE.match(title):
            continue                                   # 조과 글(제목이 날짜로 시작)만
        page_title, body = read_post(p["logNo"])
        title = title or page_title
        m = TITLE_DATE.match(title or "")
        if not m:
            continue
        fish = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if fish.month not in MONTHS or fish > today:
            continue
        rows.append(la.analyze_post(fish.isoformat(), title, link, body))
        known.add(link)
        added.append(f"{fish} {title} ({len(body)}자)")
        time.sleep(0.5)

    if not added:
        print("새 조과 글 없음")
        return 0
    rows = la.finalize(sorted(rows, key=lambda r: (r["date"], r["link"])))
    DATA.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(added)}개 추가 (전체 {len(rows)}일)")
    for a in added:
        print(" +", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
