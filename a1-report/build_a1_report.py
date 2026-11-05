# -*- coding: utf-8 -*-
"""產生 A1(死亡事故)互動式 HTML 報告。

資料來源:專案根目錄的 data.db(由 資料塞入資料庫.py 建立)。
輸出:A1_死亡事故互動報告.html(單一檔案、完全離線可開,面試現場不需要網路)。

分工:
  - 本檔負責「資料整理」:篩選第 1 當事者、對齊 A1/A2 期間、分組、簡化地圖邊界,
    再把整理好的資料以 JSON 嵌進 a1_report_template.html。
  - a1_report_template.html 負責「呈現與互動」(純 JavaScript + SVG,不依賴外部套件)。

篩選規則全部沿用 common.py,不另寫一份。
"""
import argparse
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
# 本資料夾(a1-report/)位於專案根目錄底下;common.py、data.db 都在根目錄,
# 不另放複本,讓篩選規則與資料只有一份。Docker 內根目錄掛載在 /source(環境變數 TRAFFIC_SOURCE_DIR)。
ROOT_DIR = os.path.abspath(os.environ.get("TRAFFIC_SOURCE_DIR") or os.path.join(HERE, ".."))
sys.path.insert(0, ROOT_DIR)

import common  # noqa: E402  (在專案根目錄)

TEMPLATE = os.path.join(HERE, "a1_report_template.html")
DEFAULT_OUT = os.path.join(HERE, "A1_死亡事故互動報告.html")
GML_PATH = os.path.join(HERE, "geo_boundary", "COUNTY_MOI_1140318.gml")

COUNTY_RE = r"^(.{2}[縣市])"
COUNTY_FIX = {"台北市": "臺北市", "台中市": "臺中市", "台南市": "臺南市", "台東縣": "臺東縣"}
# 縣市顯示順序:北北基桃在前,其餘由北到南
COUNTY_ORDER = ["新北市", "桃園市", "臺北市", "基隆市",
                "新竹市", "新竹縣", "苗栗縣", "臺中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣",
                "臺南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣"]

VEH_ORDER = ["機車", "小客車", "小貨車", "大型貨車", "大客車", "慢車", "行人", "其他"]
VEH_MAP = {
    "機車": "機車", "小客車(含客、貨兩用)": "小客車", "小貨車": "小貨車",
    "大貨車": "大型貨車", "曳引車": "大型貨車", "半聯結車": "大型貨車", "全聯結車": "大型貨車",
    "大客車": "大客車", "慢車": "慢車", "人": "行人",
}
AGE_ORDER = ["未滿18", "18-29", "30-39", "40-49", "50-59", "60-69", "70以上", "年齡不詳"]
LIGHT_ORDER = ["有照明且開啟", "有照明未開啟或故障", "無照明", "不明"]
PERIOD_ORDER = common.PERIOD_ORDER
WEEKDAY = ["一", "二", "三", "四", "五", "六", "日"]


# ---------- 欄位轉換 ----------
def age_group(a):
    if pd.isna(a) or a <= 0 or a > 100:
        return "年齡不詳"
    if a < 18:
        return "未滿18"
    if a >= 70:
        return "70以上"
    if a < 30:
        return "18-29"
    lo = int(a // 10) * 10
    return f"{lo}-{lo + 9}"


def speed_group(s):
    try:
        s = int(float(s))
    except (TypeError, ValueError):
        return "不明"
    if s <= 0:
        return "不明"
    if s <= 30:
        return "30以下"
    if s >= 70:
        return "70以上"
    return str(s)


CAUSE_RENAME = {
    "恍神、緊張、心不在焉分心駕駛": "分心駕駛(恍神、心不在焉)",
    "車輛未依規定暫停讓行人先行": "未暫停讓行人先行",
    "酒醉(後)駕駛": "酒後駕駛",
}
PEDESTRIAN_YIELD = "車輛未依規定暫停讓行人先行"


def cause_group(raw):
    """肇因子類別:沿用 common.YIELD_CATEGORIES 合併「未依規定讓車」,
    但「未暫停讓行人」在死亡事故中很關鍵,保留為獨立一項。"""
    if raw == PEDESTRIAN_YIELD:
        return CAUSE_RENAME[raw]
    if raw in common.YIELD_CATEGORIES:
        return "未依規定讓車(路口轉彎、支幹線等)"
    return CAUSE_RENAME.get(raw, raw)


def prep(df):
    """第 1 當事者 + 加上縣市、時段、分組欄位。A1 / A2 共用,確保分組一致。"""
    d = df[pd.to_numeric(df["當事者順位"], errors="coerce") == 1].copy()
    d["縣市"] = d["發生地點"].str.extract(COUNTY_RE)[0].replace(COUNTY_FIX)
    d = d[d["縣市"].isin(COUNTY_ORDER)].copy()
    hour = pd.to_numeric(d["發生時間"], errors="coerce") // 10000
    d["hour"] = hour
    d["時段"] = hour.apply(common.classify_period)
    d["車種組"] = d["當事者區分-類別-大類別名稱-車種"].map(VEH_MAP).fillna("其他")
    d["年齡組"] = pd.to_numeric(d["當事者事故發生時年齡"], errors="coerce").apply(age_group)
    d["照明"] = d["光線名稱"].where(d["光線名稱"].isin(LIGHT_ORDER[:3]), "不明")
    return d


# ---------- 地圖 ----------
def _dp(points, eps):
    """Douglas-Peucker 簡化(numpy 向量化距離,迭代版避免遞迴過深)。"""
    n = len(points)
    if n <= 3:
        return points
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        seg = points[i + 1:j]
        a, b = points[i], points[j]
        ab = b - a
        norm = math.hypot(ab[0], ab[1])
        if norm == 0:
            dist = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1])
        else:
            dist = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / norm
        k = int(np.argmax(dist))
        if dist[k] > eps:
            m = i + 1 + k
            keep[m] = True
            stack.append((i, m))
            stack.append((m, j))
    return points[keep]


def build_geo(cos_lat, eps_deg=0.0012, skip=("金門縣", "連江縣")):
    """讀內政部縣市界 GML → 每縣市一條 SVG path(座標為 經度*cos*1000, -緯度*1000 的整數)。"""
    ns = {"gml": "http://www.opengis.net/gml"}
    root = ET.parse(GML_PATH).getroot()
    out = {}
    for fm in root.iter("{http://www.opengis.net/gml}featureMember"):
        name = None
        for el in fm.iter():
            if el.tag.endswith("名稱") and el.text:
                name = el.text.strip()
                break
        if not name or name in skip:
            continue
        parts = []
        for coords in fm.iter("{http://www.opengis.net/gml}coordinates"):
            pts = np.array([[float(v) for v in p.split(",")[:2]] for p in coords.text.split()])
            if len(pts) < 4:
                continue
            # 高雄市的轄區含東沙、南沙群島,會讓地圖範圍變得極大;只保留台灣本島與澎湖一帶
            cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
            if not (118.0 <= cx <= 122.5 and 21.8 <= cy <= 25.5):
                continue
            pts = _dp(pts, eps_deg)
            if len(pts) < 4:
                continue
            xy = np.column_stack([np.round(pts[:, 0] * cos_lat * 1000), np.round(-pts[:, 1] * 1000)]).astype(int)
            # 去除連續重複點
            keep = np.ones(len(xy), bool)
            keep[1:] = np.any(xy[1:] != xy[:-1], axis=1)
            xy = xy[keep]
            if len(xy) < 4:
                continue
            parts.append("M" + "L".join(f"{x} {y}" for x, y in xy) + "Z")
        out[name] = "".join(parts)
    return out


# ---------- 資料來源 ----------
def resolve_source_dir(cli_value=None):
    """決定 data.db 在哪:命令列 --source-dir > 專案根目錄(環境變數 TRAFFIC_SOURCE_DIR 或上一層)。
    專案根目錄是下載與匯入資料的地方,直接讀它,就不會有過期的複本。"""
    for cand in (cli_value, ROOT_DIR):
        if cand and os.path.isfile(os.path.join(cand, "data.db")):
            return os.path.abspath(cand)
    raise SystemExit("找不到 data.db。請用 --source-dir 指定,或設定環境變數 TRAFFIC_SOURCE_DIR。")


def db_token(db_path):
    """資料庫指紋(修改時間 + 大小),用來判斷資料有沒有更新。"""
    st = os.stat(db_path)
    return f"{int(st.st_mtime)}-{st.st_size}"


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser(description="產生 A1 死亡事故互動式 HTML 報告")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--source-dir", default=None,
                    help="data.db 與 last_update.json 所在資料夾(預設:環境變數 TRAFFIC_SOURCE_DIR,"
                         "否則是本資料夾的上一層,也就是專案根目錄)")
    ap.add_argument("--version-json", default=None,
                    help="另外輸出 version.json(資料指紋),網頁會定時檢查它,有新資料時提示重新整理")
    args = ap.parse_args()
    if args.output is None:
        args.output = DEFAULT_OUT

    source_dir = resolve_source_dir(args.source_dir)
    common.DB_PATH = os.path.join(source_dir, "data.db")
    token = db_token(common.DB_PATH)
    print(f"資料庫:{common.DB_PATH}")

    a1_raw = common.load_table("tma1_data")
    a2_raw = common.load_table("tma2_data")
    a1_raw = common.restrict_a1_to_a2_period(a1_raw, a2_raw)

    a1 = prep(a1_raw)
    a2 = prep(a2_raw)
    cos_lat = 0.916  # cos(23.7°),地圖等角投影用

    # --- A1 事故明細(每起事故一列) ---
    dd = a1["死亡受傷人數"].str.extract(r"死亡(\d+);受傷(\d+)").astype(int)
    rows = []
    for (_, r), (dead, hurt) in zip(a1.iterrows(), dd.values):
        date = pd.Timestamp(str(r["發生日期"]))
        rows.append({
            "d": date.strftime("%Y-%m-%d"),
            "m": date.month,
            "dow": WEEKDAY[date.day_of_week],
            "h": int(r["hour"]),
            "per": r["時段"],
            "c": r["縣市"],
            "p": r["發生地點"],
            "x": round(float(r["經度"]), 5),
            "y": round(float(r["緯度"]), 5),
            "dead": int(dead),
            "hurt": int(hurt),
            "veh": r["車種組"],
            "vs": r["當事者區分-類別-子類別名稱-車種"],
            "age": None if r["年齡組"] == "年齡不詳" else int(float(r["當事者事故發生時年齡"])),
            "ag": r["年齡組"],
            "sex": r["當事者屬-性-別名稱"],
            "cs": cause_group(r["肇因研判子類別名稱-主要"]),
            "cc": r["肇因研判大類別名稱-主要"],
            "at": r["事故類型及型態大類別名稱"],
            "as": r["事故類型及型態子類別名稱"],
            "l": r["照明"],
            "w": r["天候名稱"],
            "rc": r["道路類別-第1當事者-名稱"],
            "sh": r["道路型態大類別名稱"],
            "sg": r["號誌-號誌種類名稱"],
            "sp": speed_group(r["速限-第1當事者"]),
            "hr": r["肇事逃逸類別名稱-是否肇逃"],
        })

    # --- A2 聯合分組計數(縣市 × 車種 × 時段 × 年齡 × 照明):當「每千件傷亡事故中的死亡事故」的分母 ---
    g = a2.groupby(["縣市", "車種組", "時段", "年齡組", "照明"]).size().reset_index(name="n")
    idx = {
        "c": {v: i for i, v in enumerate(COUNTY_ORDER)},
        "veh": {v: i for i, v in enumerate(VEH_ORDER)},
        "per": {v: i for i, v in enumerate(PERIOD_ORDER)},
        "ag": {v: i for i, v in enumerate(AGE_ORDER)},
        "l": {v: i for i, v in enumerate(LIGHT_ORDER)},
    }
    a2_rows = []
    for _, r in g.iterrows():
        if r["時段"] not in idx["per"]:
            continue
        a2_rows.append([idx["c"][r["縣市"]], idx["veh"][r["車種組"]], idx["per"][r["時段"]],
                        idx["ag"][r["年齡組"]], idx["l"][r["照明"]], int(r["n"])])

    cutoff = str(int(pd.to_numeric(a2_raw["發生日期"], errors="coerce").max()))
    first = str(int(pd.to_numeric(a1_raw["發生日期"], errors="coerce").min()))
    updated = ""
    try:
        with open(os.path.join(source_dir, "last_update.json"), encoding="utf-8") as f:
            lu = json.load(f)
        updated = "A1 " + lu.get("13139", "?") + "、A2 " + lu.get("57023", "?")
    except (OSError, ValueError):
        pass
    data = {
        "meta": {
            "updated": updated,
            "token": token,
            "period": [f"{first[:4]}-{first[4:6]}-{first[6:]}", f"{cutoff[:4]}-{cutoff[4:6]}-{cutoff[6:]}"],
            "a1_party_rows": int(len(a1_raw)),
            "a1_accidents_all": int(len(prep(a1_raw))),
            "a2_first_party_all": int(len(a2)),
            "cosLat": cos_lat,
            "vehicleReg": common.VEHICLE_REGISTRATION,
            "fourCities": common.CITY_ORDER,
            "periodHours": common.PERIOD_HOURS,
        },
        "dims": {"county": COUNTY_ORDER, "veh": VEH_ORDER, "per": PERIOD_ORDER, "ag": AGE_ORDER, "l": LIGHT_ORDER},
        "rows": rows,
        "a2": a2_rows,
        "geo": build_geo(cos_lat),
    }

    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")  # 避免資料內出現 </script>
    html = html.replace("/*__DATA__*/null", payload)
    # 樣板內寫死在文字裡的數字(起數、期間…)也由資料算出,資料更新後不會過期
    four_rows = [r for r in rows if r["c"] in common.CITY_ORDER]
    drunk = sum(1 for r in four_rows if r["cs"] == "酒後駕駛")
    d0, d1 = pd.Timestamp(first), pd.Timestamp(cutoff)
    placeholders = {
        "{{N4}}": str(len(four_rows)),
        "{{N_KEELUNG}}": str(sum(1 for r in four_rows if r["c"] == "基隆市")),
        "{{DRUNK_PCT}}": f"{drunk / len(four_rows) * 100:.0f}" if four_rows else "0",
        "{{PERIOD_SLASH}}": f"{d0.year}/{d0.month}/{d0.day}–{d1.month}/{d1.day}",
        "{{PERIOD_ZH}}": f"{d0.year} 年 {d0.month} 月 {d0.day} 日到 {d1.month} 月 {d1.day} 日",
        "{{END_MONTH}}": str(d1.month),
        "{{END_DAY}}": str(d1.day),
    }
    for k, v in placeholders.items():
        html = html.replace(k, v)
    assert "{{" not in html, "樣板仍有未替換的佔位符"
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    if args.version_json:
        with open(args.version_json, "w", encoding="utf-8") as f:
            json.dump({"token": token, "builtAt": pd.Timestamp.now().isoformat(timespec="seconds")}, f)
    size = os.path.getsize(args.output) / 1024
    four = sum(1 for r in rows if r["c"] in common.CITY_ORDER)
    print(f"已輸出 {args.output} ({size:,.0f} KB)")
    print(f"A1 事故 {len(rows)} 起(全台),北北基桃 {four} 起;A2 分母列 {len(a2_rows)} 組")


if __name__ == "__main__":
    main()
