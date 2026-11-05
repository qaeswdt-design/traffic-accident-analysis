# -*- coding: utf-8 -*-
"""共用邏輯：所有分析腳本都 import 這個檔案，篩選條件與常數只在這裡維護一份。"""
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

# 「未依規定讓車」子類別，合併成單一大類
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

# 時段區間與各區間的小時數（時段長短不同，比較前要除以小時數）
PERIOD_ORDER = ["早峰(06-08)", "日間(09-15)", "晚峰(16-19)", "夜間(20-05)"]
PERIOD_HOURS = {"早峰(06-08)": 3, "日間(09-15)": 7, "晚峰(16-19)": 4, "夜間(20-05)": 10}

# 中文字型依序嘗試：Windows → macOS → Linux
CJK_FONTS = [
    "Microsoft JhengHei", "PingFang TC", "Heiti TC",
    "Noto Sans CJK TC", "Noto Sans TC", "WenQuanYi Zen Hei", "DejaVu Sans",
]

def make_http_session(verify=True):
    """建立下載用的 requests Session，預設完整驗證 SSL 憑證。

    內政部下載網址（opdadm.moi.gov.tw）的政府憑證鏈缺少 Subject Key Identifier，
    Python 3.13+ 的 X.509 嚴格模式會因此拒絕連線。這裡只關掉「嚴格模式」這一項，
    憑證鏈、有效期、網域比對都照常驗證。verify=False 只留給使用者明確傳 --insecure 時用。
    """
    import ssl
    import certifi
    import requests
    from requests.adapters import HTTPAdapter

    class _RelaxedStrictAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            ctx = ssl.create_default_context(cafile=certifi.where())
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
            kwargs["ssl_context"] = ctx
            super().init_poolmanager(*args, **kwargs)

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    if verify:
        session.mount("https://", _RelaxedStrictAdapter())
    else:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session.verify = False
    return session


def setup_matplotlib_font():
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = CJK_FONTS
    plt.rcParams["axes.unicode_minus"] = False


def load_table(table_name="tma2_data", db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        return pd.read_sql(f"SELECT * FROM {table_name}", conn)
    finally:
        conn.close()


def filter_first_party_four_cities(df, location_col="發生地點", party_col="當事者順位",
                                   add_city_column=True):
    """只留第 1 當事者 + 北北基桃。

    順位必須「數值等於 1」；用字串 contains("1") 會把 10、11、21… 也算進來而重複計數。
    A1 的順位欄是字串、A2 是浮點數，所以先統一轉成數字再比較。
    """
    is_first = pd.to_numeric(df[party_col], errors="coerce") == 1
    in_cities = df[location_col].astype(str).str.contains(CITY_PATTERN, na=False)
    df_first = df[is_first & in_cities].copy()
    if add_city_column:
        df_first["縣市"] = df_first[location_col].str.extract(f"({CITY_PATTERN})")
        df_first["縣市"] = df_first["縣市"].replace({"台北市": "臺北市"})
    return df_first


def restrict_a1_to_a2_period(df_a1, df_a2, date_col="發生日期"):
    """A1（整份 JSON）常比 A2（逐月 CSV）多出較晚的日期，這裡把 A1 截到 A2 的最後一天，
    讓死亡數與受傷數落在同一段期間。"""
    cutoff = pd.to_numeric(df_a2[date_col], errors="coerce").max()
    a1_dates = pd.to_numeric(df_a1[date_col], errors="coerce")
    kept = df_a1[a1_dates <= cutoff].copy()
    print(f"A1 截到 A2 最後日期 {int(cutoff)}: {len(df_a1)} → {len(kept)} 筆（排除 {len(df_a1) - len(kept)} 筆較晚的資料）")
    return kept


def add_period_column(df, time_col="發生時間"):
    """發生時間是不補零的 HHMMSS 整數，除以 10000 取小時，再歸入時段區間。"""
    df = df.copy()
    df["發生時段_小時"] = df[time_col] // 10000
    df["時段區間"] = df["發生時段_小時"].apply(classify_period)
    return df


def classify_period(hour):
    if pd.isna(hour):
        return None
    hour = int(hour)
    if 6 <= hour <= 8:
        return "早峰(06-08)"
    if 9 <= hour <= 15:
        return "日間(09-15)"
    if 16 <= hour <= 19:
        return "晚峰(16-19)"
    return "夜間(20-05)"


def merge_yield_categories(df, raw_col="肇因研判子類別名稱-主要", new_col="肇因大類"):
    df = df.copy()
    df[new_col] = df[raw_col].apply(lambda x: "未依規定讓車" if x in YIELD_CATEGORIES else x)
    return df


def exclude_invalid_cause(df, col_name="肇因大類",
                          exclude_keywords=("尚未發現肇因", "未發現肇事因素")):
    mask_exclude = df[col_name].astype(str).apply(lambda x: any(kw in x for kw in exclude_keywords))
    return df[~mask_exclude]


def per_100k_vehicles(count_df, city_order=None):
    """欄為縣市的件數表 → 每十萬輛車事故件數。"""
    city_order = city_order or CITY_ORDER
    result = count_df.astype(float)
    for city in city_order:
        result[city] = count_df[city] / VEHICLE_REGISTRATION[city] * 100_000
    return result


def output_path(filename):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, filename)


if __name__ == "__main__":
    print("common.py 是共用模組，不需要單獨執行；請執行 run_all.py。")
