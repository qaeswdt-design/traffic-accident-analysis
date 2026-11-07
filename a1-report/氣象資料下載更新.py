# -*- coding: utf-8 -*-
"""下載中央氣象署(CWA)各縣市的逐日氣象觀測資料,存進 data.db,供報告分析「天氣 × 死亡事故」。

資料來源:中央氣象署「CODiS 氣象觀測資料查詢系統」(https://codis.cwa.gov.tw)。
  - 官方的「氣象資料開放平臺」API(opendata.cwa.gov.tw)需要免費申請授權碼,而且只提供最新資料,沒有歷史資料,
    所以歷史逐日資料改用 CODiS 網站使用的查詢介面。這個介面**沒有官方文件、也沒有穩定性保證**,日後可能變動;
    程式遇到格式不符會直接停下並顯示原因,不會寫入壞資料。
  - 使用政府資料開放授權條款。請保持禮貌的請求頻率(預設每次請求間隔 0.8 秒),不要把間隔調得太短。

做法:
  1. 取得全台測站清單,每個縣市挑最多 N 個「現役」測站(優先署屬有人站 cwb,其次自動站 auto,低海拔、分散在不同行政區)。
  2. 對每個測站、每個月份各要一次「該月逐日資料」,取出雨量、氣溫、濕度、風速、最大陣風。
  3. 寫入 data.db 的 weather_station / weather_daily / weather_fetch_log 三張表(不動事故資料的表)。
  4. 增量更新:已經完整抓過的過去月份不會重抓;最近一個月每次都會補到最新。

用法:
    python 氣象資料下載更新.py                  # 抓事故資料涵蓋期間(缺的才抓),會先問一次要不要開始
    python 氣象資料下載更新.py --yes             # 不詢問(自動化用)
    python 氣象資料下載更新.py --yes --if-needed 20   # 距離上次成功不到 20 小時就直接略過(排程/容器用)
    python 氣象資料下載更新.py --dry-run         # 只列出會發出多少請求,不連網下載資料
    python 氣象資料下載更新.py --start 2026-01-01 --end 2026-10-31 --per-county 2 --force
雨量特殊值:CODiS 以 -9.8 代表「微量(<0.1 mm)」,記為 0.05;其餘小於 -9 的值代表儀器故障或無資料,記為空值。
"""
import argparse
import calendar
import datetime as dt
import os
import re
import sqlite3
import sys
import time

import common

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

API = "https://codis.cwa.gov.tw/api"
UA = "Mozilla/5.0 (traffic-a1-report; personal analysis; polite crawler)"
REPORT_COUNTIES = ["新北市", "桃園市", "臺北市", "基隆市", "新竹市", "新竹縣", "苗栗縣", "臺中市", "彰化縣", "南投縣", "雲林縣",
                   "嘉義市", "嘉義縣", "臺南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS weather_station (
    station_id TEXT PRIMARY KEY, name TEXT, county TEXT, district TEXT, attr TEXT,
    lon REAL, lat REAL, altitude REAL, selected INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS weather_daily (
    station_id TEXT, county TEXT, date TEXT, precip_mm REAL, precip_hours REAL,
    temp_mean REAL, temp_max REAL, temp_min REAL, rh_mean REAL, wind_mean REAL, gust_max REAL,
    PRIMARY KEY (station_id, date));
CREATE TABLE IF NOT EXISTS weather_fetch_log (
    station_id TEXT, month TEXT, n_days INTEGER, fetched_at TEXT, PRIMARY KEY (station_id, month));
"""


# ---------- 小工具 ----------
def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def clean(v):
    """CODiS 的特殊值(例如 -9.5、-9.7、-9.99)代表無資料或儀器故障 → 空值。"""
    v = num(v)
    return None if v is None or v <= -9 else v


def precip(v):
    v = num(v)
    if v is None:
        return None
    if v == -9.8:        # 微量
        return 0.05
    return None if v < 0 else v


def district_of(address):
    m = re.search(r"([^\d\s縣市]{1,3}[區鄉鎮市])", address or "")
    return m.group(1) if m else ""


def get_json(session, method, url, **kw):
    last = None
    for i in range(4):
        try:
            r = session.request(method, url, timeout=60, **kw)
            if r.status_code == 200:
                j = r.json()
                if j.get("code") == 200:
                    return j
                last = f"code={j.get('code')} {j.get('message')}"
            else:
                last = f"HTTP {r.status_code}"
        except Exception as e:            # 連線中斷、逾時、非 JSON…
            last = repr(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url} 失敗:{last}")


# ---------- 測站 ----------
def pick_stations(station_json, start, per_county):
    """每個縣市挑最多 per_county 個現役測站:署屬有人站優先,其次自動站(低海拔、行政區分散)。"""
    groups = {g["stationAttribute"]: g["item"] for g in station_json["data"]}
    chosen = {}
    for county in REPORT_COUNTIES:
        def active(i):
            end = i.get("stationEndDate") or ""
            return i.get("countryName") == county and (not end or end >= start.isoformat())
        picks = []
        for i in sorted([i for i in groups.get("cwb", []) if active(i)], key=lambda i: i.get("altitude") or 0):
            picks.append(("cwb", i))
        used = {district_of(i.get("address")) for _, i in picks}
        autos = sorted([i for i in groups.get("auto", []) if active(i) and (i.get("altitude") or 0) <= 300],
                       key=lambda i: (i.get("altitude") or 0))
        for i in autos:
            if len(picks) >= per_county:
                break
            d = district_of(i.get("address"))
            if d and d in used:
                continue
            picks.append(("auto", i))
            used.add(d)
        for attr, i in picks[:per_county]:
            chosen[i["stationID"]] = {"attr": attr, "item": i, "county": county}
    return chosen


# ---------- 下載與寫入 ----------
def stn_type(attr, station_id):
    """CODiS 的測站類型參數:署屬站 cwb、自動站 auto_C0 / auto_C1(依站碼前兩碼)、農業站 agr。"""
    return f"auto_{station_id[:2]}" if attr == "auto" else attr


def fetch_month(session, station_id, attr, year, month):
    last = calendar.monthrange(year, month)[1]
    form = {"date": f"{year}-{month:02d}-01T00:00:00.000+08:00", "type": "report_month", "stn_ID": station_id, "stn_type": stn_type(attr, station_id),
            "more": "", "start": f"{year}-{month:02d}-01T00:00:00", "end": f"{year}-{month:02d}-{last}T23:59:59", "item": ""}
    j = get_json(session, "POST", f"{API}/station", data=form)
    data = j.get("data") or []
    if not data or "dts" not in data[0]:
        raise RuntimeError(f"{station_id} {year}-{month:02d}:回傳格式不符(沒有 dts),CODiS 介面可能已變動")
    out = []
    for d in data[0]["dts"]:
        date = (d.get("DataDate") or "")[:10]
        if not date:
            continue
        g = lambda k, f: (d.get(k) or {}).get(f)
        out.append((date, precip(g("Precipitation", "Accumulation")), clean(g("PrecipitationDuration", "Total")),
                    clean(g("AirTemperature", "Mean")), clean(g("AirTemperature", "Maximum")), clean(g("AirTemperature", "Minimum")),
                    clean(g("RelativeHumidity", "Mean")), clean(g("WindSpeed", "Mean")), clean(g("PeakGust", "Maximum"))))
    return out


def months_between(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def data_period(conn):
    """預設期間 = 事故資料(A2)涵蓋的日期範圍。"""
    try:
        lo, hi = conn.execute("SELECT MIN(CAST(發生日期 AS INTEGER)), MAX(CAST(發生日期 AS INTEGER)) FROM tma2_data").fetchone()
        if lo and hi:
            f = lambda n: dt.date(n // 10000, n // 100 % 100, n % 100)
            return f(lo), f(hi)
    except sqlite3.Error:
        pass
    today = dt.date.today()
    return dt.date(today.year, 1, 1), today - dt.timedelta(days=1)


def main():
    ap = argparse.ArgumentParser(description="下載各縣市逐日氣象資料到 data.db(中央氣象署 CODiS)")
    ap.add_argument("--start", help="起始日 YYYY-MM-DD(預設:事故資料的第一天)")
    ap.add_argument("--end", help="結束日 YYYY-MM-DD(預設:事故資料的最後一天,且不超過昨天)")
    ap.add_argument("--per-county", type=int, default=3, help="每縣市最多用幾個測站(預設 3)")
    ap.add_argument("--delay", type=float, default=0.8, help="每次請求間隔秒數(預設 0.8,請勿調得太短)")
    ap.add_argument("--force", action="store_true", help="已抓過的月份也重抓")
    ap.add_argument("--yes", action="store_true", help="不詢問,直接下載")
    ap.add_argument("--dry-run", action="store_true", help="只列出要發出的請求數,不下載")
    ap.add_argument("--if-needed", type=float, metavar="HOURS", help="距離上次成功不到 HOURS 小時就略過(排程用)")
    ap.add_argument("--db", default=common.DB_PATH)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    lo, hi = data_period(conn)
    start = dt.date.fromisoformat(args.start) if args.start else lo
    end = min(dt.date.fromisoformat(args.end) if args.end else hi, dt.date.today() - dt.timedelta(days=1))  # CODiS 當天資料隔天才有
    if args.if_needed is not None:
        last = conn.execute("SELECT MAX(fetched_at) FROM weather_fetch_log").fetchone()[0]
        if last and (dt.datetime.now() - dt.datetime.fromisoformat(last)).total_seconds() < args.if_needed * 3600 and not args.force:
            print(f"氣象資料 {last} 才更新過(不到 {args.if_needed:g} 小時),略過。")
            return

    session = common.make_http_session()
    session.headers["User-Agent"] = UA
    print("取得測站清單…")
    stations = pick_stations(get_json(session, "GET", f"{API}/station_list"), start, args.per_county)
    missing = [c for c in REPORT_COUNTIES if not any(s["county"] == c for s in stations.values())]
    if missing:
        print("⚠ 這些縣市找不到可用測站:", "、".join(missing))
    months = list(months_between(start, end))
    today = dt.date.today()
    done = {(r[0], r[1]): (r[2], r[3]) for r in conn.execute("SELECT station_id, month, n_days, fetched_at FROM weather_fetch_log")}
    todo = []
    for sid, s in stations.items():
        for y, m in months:
            key = f"{y}-{m:02d}"
            days_in = calendar.monthrange(y, m)[1]
            past_complete = (y, m) < (end.year, end.month) or end >= dt.date(y, m, days_in)
            got = done.get((sid, key))
            if not args.force and got and got[0] >= (days_in if past_complete else (end.day if (y, m) == (end.year, end.month) else days_in)):
                continue
            todo.append((sid, y, m))
    print(f"期間 {start} ~ {end};測站 {len(stations)} 個(涵蓋 {len(REPORT_COUNTIES) - len(missing)} 個縣市);需要下載 {len(todo)} 個「測站 × 月份」。")
    if args.dry_run or not todo:
        if not todo:
            print("資料已是最新,不需要下載。")
        return
    if not args.yes:
        est = len(todo) * (args.delay + 0.5) / 60
        if input(f"預估約 {est:.0f} 分鐘,是否開始?(y/N) ").strip().lower() != "y":
            print("已取消。")
            return

    for sid, s in stations.items():
        i = s["item"]
        conn.execute("INSERT OR REPLACE INTO weather_station VALUES (?,?,?,?,?,?,?,?,1)",
                     (sid, i.get("stationName"), s["county"], district_of(i.get("address")), s["attr"], i.get("longitude"), i.get("latitude"), i.get("altitude")))
    conn.commit()
    ok = fail = 0
    t0 = time.time()
    for n, (sid, y, m) in enumerate(todo, 1):
        s = stations[sid]
        try:
            rows = fetch_month(session, sid, s["attr"], y, m)
        except Exception as e:
            fail += 1
            print(f"  ✗ {s['county']} {s['item'].get('stationName')}({sid}) {y}-{m:02d}:{e}")
            if fail >= 8 and ok == 0:
                raise SystemExit("連續失敗,CODiS 介面可能已變動或暫時無法連線,已停止。")
            time.sleep(args.delay)
            continue
        rows = [r for r in rows if start.isoformat() <= r[0] <= end.isoformat()]
        conn.executemany("INSERT OR REPLACE INTO weather_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)", [(sid, s["county"], *r) for r in rows])
        conn.execute("INSERT OR REPLACE INTO weather_fetch_log VALUES (?,?,?,?)", (sid, f"{y}-{m:02d}", len(rows), dt.datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        ok += 1
        if n % 20 == 0 or n == len(todo):
            print(f"  進度 {n}/{len(todo)}(成功 {ok}、失敗 {fail}),已用 {time.time() - t0:.0f} 秒")
        time.sleep(args.delay)

    print(f"完成:成功 {ok} 個、失敗 {fail} 個(失敗的下次執行會自動補抓)。")
    cov = conn.execute("SELECT county, COUNT(DISTINCT station_id), COUNT(DISTINCT date), ROUND(SUM(precip_mm)/COUNT(DISTINCT station_id),0) "
                       "FROM weather_daily GROUP BY county ORDER BY county").fetchall()
    print("縣市 | 測站數 | 有資料的天數 | 平均每站總雨量(mm)")
    for c in cov:
        print(" | ".join(str(x) for x in c))
    conn.close()


if __name__ == "__main__":
    main()
