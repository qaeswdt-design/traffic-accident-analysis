import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os
plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

# ========== 資料讀取(邏輯不變) ==========
db_path = "./data.db"
conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT * FROM tma2_data", conn)
conn.close()

location_col = "發生地點"
party_col = "當事者順位"
time_col = "發生時間"

# ========== 兩層篩選:第1當事人 + 北北基桃 ==========
df_first = df[df[party_col].astype(str).str.contains("1", na=False)]

city_pattern = "桃園市|新北市|臺北市|台北市|基隆市"
df_first = df_first[df_first[location_col].astype(str).str.contains(city_pattern, na=False)]

df_first = df_first.copy()
df_first["縣市"] = df_first[location_col].str.extract(f"({city_pattern})")
df_first["縣市"] = df_first["縣市"].replace({"台北市": "臺北市"})

# ========== 發生時間 → 小時 → 時段區間 ==========
# 原始格式為 HHMMSS(整數,無補零),需除以10000取小時
df_first["發生時段_小時"] = (df_first[time_col] // 10000)

def classify_period(hour):
    if pd.isna(hour):
        return None
    hour = int(hour)
    if 6 <= hour <= 8:
        return "早峰(06-08)"
    elif 9 <= hour <= 15:
        return "日間(09-15)"
    elif 16 <= hour <= 19:
        return "晚峰(16-19)"
    else:  # 20-23 或 0-5，跨午夜
        return "夜間(20-05)"

df_first["時段區間"] = df_first["發生時段_小時"].apply(classify_period)

# ========== 分母:機動車輛登記數(115年7月底,交通部公路局統計) ==========
vehicle_registration = {
    "新北市": 3_381_671,
    "桃園市": 2_328_640,
    "臺北市": 1_720_965,
    "基隆市": 302_691,
}

city_order = ["新北市", "桃園市", "臺北市", "基隆市"]
period_order = ["早峰(06-08)", "日間(09-15)", "晚峰(16-19)", "夜間(20-05)"]

# ========== 縣市 x 時段區間 交叉表 ==========
cross = pd.crosstab(df_first["時段區間"], df_first["縣市"])
cross = cross.loc[period_order, city_order]

# ========== 換算成「每十萬輛車事故件數」 ==========
cross_per_vehicle = cross.copy()
for city in city_order:
    cross_per_vehicle[city] = cross[city] / vehicle_registration[city] * 100_000

print("原始件數:")
print(cross)
print()
print("每十萬輛車事故率(車輛版標準化):")
print(cross_per_vehicle.round(2))

# ========== 分組橫向長條圖 ==========
periods = cross_per_vehicle.index.tolist()
counties = cross_per_vehicle.columns.tolist()

n_periods = len(periods)
n_counties = len(counties)
bar_height = 0.18
y_base = range(n_periods)

fig, ax = plt.subplots(figsize=(10, 6))
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
ax.set_yticklabels(periods)
ax.invert_yaxis()
ax.set_xlabel("每十萬輛車事故件數")
ax.set_title("北北基桃各時段事故率比較（車輛數權重後）", fontsize=15, pad=15)
ax.legend(title="縣市", loc="lower right")

fig.subplots_adjust(left=0.18, right=0.95, top=0.9, bottom=0.1)
os.makedirs("./outputs", exist_ok=True)
plt.savefig("./outputs/時段區間事故分析.png", dpi=300, transparent=True, bbox_inches="tight")

plt.show()