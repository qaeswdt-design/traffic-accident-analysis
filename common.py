# -*- coding: utf-8 -*-
"""
共用邏輯模組：北北基桃交通事故分析專案

把貫穿全部圖表的「資料讀取＋篩選」邏輯集中在這裡（對應簡報「核心程式邏輯」那頁），
之後新增圖表時 import 這個檔案就好，不用再複製貼上同一段篩選邏輯。
"""
import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

CITY_PATTERN = "桃園市|新北市|臺北市|台北市|基隆市"
CITY_ORDER = ["新北市", "桃園市", "臺北市", "基隆市"]

# 機動車輛登記數（115年7月底，交通部公路局統計）
# 資料來源: https://stat.thb.gov.tw（機動車輛登記數－按縣市別分）
VEHICLE_REGISTRATION = {
    "新北市": 3_381_671,
    "桃園市": 2_328_640,
    "臺北市": 1_720_965,
    "基隆市": 302_691,
}

# 「未依規定讓車」子類別合併清單（跨圖表共用的肇因大類合併邏輯）
YIELD_CATEGORIES = [
    "有號誌路口，轉彎車未讓直行車先行",
    "無號誌路口，轉彎車未讓直行車先行",
    "無號誌路口，支線道未讓幹線道先行",
    "無號誌路口，左方車未讓右方車先行",
    "無號誌路口，少線道未讓多線道先行",
    "車輛未依規定暫停讓行人先行",
    "行經圓環未依規定讓車",
    "峻狹坡路會車，下坡車未讓上坡車先行",
    "其他未依規定讓車",
]


def setup_matplotlib_font():
    """設定中文字體，避免圖表中文顯示成方框。所有繪圖腳本開頭都應呼叫一次。"""
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
    plt.rcParams["axes.unicode_minus"] = False


def load_table(table_name="tma2_data", db_path=None):
    """讀取指定資料表（預設 tma2_data，即 A1+A2 合併的全量資料）。"""
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        return pd.read_sql(f"SELECT * FROM {table_name}", conn)
    finally:
        conn.close()


def filter_first_party_four_cities(df, location_col="發生地點", party_col="當事者順位",
                                    add_city_column=True):
    """
    每個圖表都先套用同一套篩選：第1當事者 + 北北基桃四縣市
    （對應簡報「核心程式邏輯」頁展示的那段程式碼）。
    """
    df_first = df[df[party_col].astype(str).str.contains("1", na=False)]
    df_first = df_first[df_first[location_col].astype(str).str.contains(CITY_PATTERN, na=False)]
    df_first = df_first.copy()
    if add_city_column:
        df_first["縣市"] = df_first[location_col].str.extract(f"({CITY_PATTERN})")
        df_first["縣市"] = df_first["縣市"].replace({"台北市": "臺北市"})
    return df_first


def merge_yield_categories(df, raw_col="肇因研判子類別名稱-主要", new_col="肇因大類"):
    """把多種「未依規定讓車」子類別合併成單一大類，跨圖表共用。"""
    df = df.copy()
    df[new_col] = df[raw_col].apply(lambda x: "未依規定讓車" if x in YIELD_CATEGORIES else x)
    return df


def exclude_invalid_cause(df, col_name="肇因大類",
                           exclude_keywords=("尚未發現肇因", "未發現肇事因素")):
    """排除「尚未發現肇因」等無效肇因列。"""
    mask_exclude = df[col_name].astype(str).apply(lambda x: any(kw in x for kw in exclude_keywords))
    return df[~mask_exclude]


def weight_by_vehicle_registration(cross_count_df, city_order=None):
    """把縣市別的事故件數換算成「每十萬輛車事故件數」，消除縣市規模差異。"""
    city_order = city_order or CITY_ORDER
    result = cross_count_df.copy()
    for city in city_order:
        result[city] = cross_count_df[city] / VEHICLE_REGISTRATION[city] * 100_000
    return result


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


if __name__ == "__main__":
    print("common.py 是共用模組，不需要單獨執行；請執行 run_all.py。")
