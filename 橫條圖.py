import sqlite3 ,os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

# ========== 資料讀取(邏輯不變) ==========
db_path = "./data.db"
conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT * FROM tma2_data", conn)
conn.close()

# ========== 肇因大類合併(邏輯不變) ==========
raw_col = "肇因研判子類別名稱-主要"
yield_categories = [
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
df["肇因大類"] = df[raw_col].apply(
    lambda x: "未依規定讓車" if x in yield_categories else x
)

col_name = "肇因大類"
location_col = "發生地點"
party_col = "當事者順位"

# ========== 三層篩選(邏輯不變) ==========
df_first = df[df[party_col].astype(str).str.contains("1", na=False)]
city_pattern = "桃園市|新北市|臺北市|台北市|基隆市"
df_first = df_first[df_first[location_col].astype(str).str.contains(city_pattern, na=False)]

exclude_keywords = ["尚未發現肇因", "未發現肇事因素"]
mask_exclude = df_first[col_name].astype(str).apply(
    lambda x: any(kw in x for kw in exclude_keywords)
)
df_filtered = df_first[~mask_exclude]

# ========== 抽取縣市欄位 ==========
df_filtered = df_filtered.copy()
df_filtered["縣市"] = df_filtered[location_col].str.extract(f"({city_pattern})")
df_filtered["縣市"] = df_filtered["縣市"].replace({"台北市": "臺北市"})

# ========== 分母:機動車輛登記數(115年7月底,交通部公路局統計) ==========
# 資料來源: https://stat.thb.gov.tw (機動車輛登記數－按縣市別分)
vehicle_registration = {
    "新北市": 3_381_671,
    "桃園市": 2_328_640,
    "臺北市": 1_720_965,
    "基隆市": 302_691,
}

overall_top5 = df_filtered[col_name].value_counts().head(5).index.tolist()

city_order = ["新北市", "桃園市", "臺北市", "基隆市"]
cross = pd.crosstab(df_filtered[col_name], df_filtered["縣市"])
cross = cross.loc[overall_top5, city_order]

# ========== 換算成「每十萬輛車事故件數」 ==========
cross_per_vehicle = cross.copy()
for city in city_order:
    cross_per_vehicle[city] = cross[city] / vehicle_registration[city] * 100_000

print("原始件數:")
print(cross)
print()
print("每十萬輛車事故率(車輛版標準化):")
print(cross_per_vehicle.round(2))

# ========== 分組橫向長條圖(車輛版標準化) ==========
causes = cross_per_vehicle.index.tolist()
counties = cross_per_vehicle.columns.tolist()

n_causes = len(causes)
n_counties = len(counties)
bar_height = 0.18
y_base = range(n_causes)

fig, ax = plt.subplots(figsize=(10, 6.5))
colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]

for i, county in enumerate(counties):
    offset = (i - (n_counties - 1) / 2) * bar_height
    y_pos = [y + offset for y in y_base]
    ax.barh(
        y_pos,
        cross_per_vehicle[county].values,
        height=bar_height,
        label=county,
        color=colors[i],
    )

ax.set_yticks(list(y_base))
ax.set_yticklabels(causes)
ax.invert_yaxis()
ax.set_xlabel("每十萬輛車事故件數")
ax.set_title("北北基桃各縣市主要肇因比較（車輛數權重後）TOP 5", fontsize=15, pad=15)
ax.legend(title="縣市", loc="lower right")

fig.subplots_adjust(left=0.22, right=0.95, top=0.9, bottom=0.1)
os.makedirs("./outputs", exist_ok=True)
plt.savefig("./outputs/北北基桃各縣市主要肇因比較（車輛數權重後）TOP 5.png", dpi=300, transparent=True, bbox_inches="tight")



plt.show()