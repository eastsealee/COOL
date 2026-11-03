"""남당항 일출·일몰 (NOAA 계산식, 한국 표준시). 추가 라이브러리 없음."""
import math
import datetime as dt

LAT, LON = 36.538, 126.463   # 남당항


def sun_times(d: dt.date, lat=LAT, lon=LON):
    """(일출, 일몰) datetime — 대기굴절 포함(-0.833°)"""
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    la = math.radians(lat)
    cos_h = math.cos(math.radians(90.833)) / (math.cos(la) * math.cos(decl)) - math.tan(la) * math.tan(decl)
    ha = math.degrees(math.acos(max(-1.0, min(1.0, cos_h))))
    noon = 720 - 4 * lon - eqt + 540          # 분, KST(UTC+9)
    base = dt.datetime.combine(d, dt.time())
    return base + dt.timedelta(minutes=noon - 4 * ha), base + dt.timedelta(minutes=noon + 4 * ha)


def fishing_window(d: dt.date):
    """낚시 시작 = 일출 5분 전, 종료 = 일몰 20분 전 → (시작, 종료, 일출, 일몰)"""
    rise, sett = sun_times(d)
    return rise - dt.timedelta(minutes=5), sett - dt.timedelta(minutes=20), rise, sett
