"""바다타임 전국 지점 목록 만들기 → mulddae/data/ports.json  (GitHub Actions에서 가끔 한 번 실행)

1) 권역별 대표 페이지(서해 356 · 남해 41 · 동해 195 · 제주 67)의 지역 메뉴에서 지점 번호·이름을 모음
2) 지점 페이지마다 머리글의 주소(시·도, 시·군·구)와 '동경 127:46 북위 34:45' 좌표를 읽음
글자 깨짐 대비: UTF-8로 읽고 깨진 바이트만 버림
"""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT = Path(__file__).parent / "data" / "ports.json"
SEEDS = {"서해": 356, "남해": 41, "동해": 195, "제주": 67}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://www.badatime.com/"}
LINK_RE = re.compile(r"^(?:https?://(?:www\.)?badatime\.com)?/?(\d{1,5})\.html$")
COORD_RE = re.compile(r"동경\s*(\d{2,3})\s*[:：]\s*(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?\s*북위\s*(\d{2})\s*[:：]\s*(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?")
SIDO_RE = re.compile(r"(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|강원도|"
                     r"충청북도|충청남도|전북특별자치도|전라북도|전라남도|경상북도|경상남도|제주특별자치도)\s+([가-힣]+(?:시|군|구))?")
SKIP_NAME = re.compile(r"통합검색|물때|날씨|달력|수온|바다|^\s*$")


def get(url: str, tries: int = 3) -> str:
    last = None
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.raise_for_status()
            return r.content.decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"{url}: {last}")


def menu_links(html: str) -> list[tuple[int, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        m = LINK_RE.match(a["href"].strip())
        name = a.get_text(" ", strip=True)
        if m and name and not SKIP_NAME.search(name) and len(name) <= 15 and re.search(r"[가-힣]", name):
            out.append((int(m.group(1)), name))
    return out


def station(pid: int) -> dict:
    text = re.sub(r"\s+", " ", BeautifulSoup(get(f"https://www.badatime.com/{pid}.html"), "html.parser").get_text(" "))
    info: dict = {"id": pid}
    c = COORD_RE.search(text)
    if c:
        lon = int(c.group(1)) + int(c.group(2)) / 60 + int(c.group(3) or 0) / 3600
        lat = int(c.group(4)) + int(c.group(5)) / 60 + int(c.group(6) or 0) / 3600
        info.update(lat=round(lat, 4), lon=round(lon, 4))
        head = text[max(0, c.start() - 250): c.start()]
        addr = list(SIDO_RE.finditer(head))
        if addr:
            info.update(sido=addr[-1].group(1), sigungu=addr[-1].group(2) or "")
    return info


def main() -> None:
    found: dict[int, dict] = {}
    for area, seed in SEEDS.items():
        links = menu_links(get(f"https://www.badatime.com/{seed}.html"))
        print(f"[{area}] 메뉴 링크 {len(links)}개", flush=True)
        for pid, name in links:
            found.setdefault(pid, {"id": pid, "name": name, "area": area})
        time.sleep(1)
    print(f"지점 {len(found)}곳 — 위치 읽는 중", flush=True)

    def work(pid: int) -> dict:
        time.sleep(0.3)
        try:
            return station(pid)
        except Exception as e:  # noqa: BLE001
            print("실패", pid, e, flush=True)
            return {"id": pid}

    with ThreadPoolExecutor(4) as ex:
        for i, info in enumerate(ex.map(work, sorted(found)), 1):
            found[info["id"]].update(info)
            if i % 100 == 0:
                print(f"  {i}/{len(found)}", flush=True)

    ports = [p for p in found.values() if "lat" in p]
    miss = [p for p in found.values() if "lat" not in p]
    ports.sort(key=lambda p: (list(SEEDS).index(p["area"]), p.get("sido", ""), p.get("sigungu", ""), p["name"]))
    print(f"완료: 위치 있는 지점 {len(ports)}곳, 위치 못 읽은 지점 {len(miss)}곳", flush=True)
    for p in miss[:20]:
        print("  위치 없음:", p["id"], p["name"], flush=True)
    for p in ports[:5] + ports[-5:]:
        print("  예:", p, flush=True)
    if len(ports) < 500:
        sys.exit("지점이 너무 적습니다 — 페이지 구조가 바뀌었는지 확인 필요")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ports, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
