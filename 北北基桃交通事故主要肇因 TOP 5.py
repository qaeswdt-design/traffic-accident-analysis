
import sqlite3 ,os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# 設定中文字體，避免圖表中文顯示成方框
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

print(f"原始筆數: {df.shape[0]} → 第1當事人+北北基桃+排除無效肇因後: {df_filtered.shape[0]}")

# ========== 統計 TOP5(由大到小) ==========
top5 = df_filtered[col_name].value_counts().head(5).sort_values(ascending=True)
# 注意:sort_values(ascending=True) 是為了配合 barh 由下到上畫圖時，
# 最上面的長條才會是排名第一(數值最大)

total_valid = df_filtered[col_name].notna().sum()
top5_ratio = top5 / total_valid * 100

# Pareto 累積百分比(依原始排名順序，由大到小累加)
top5_sorted_desc = top5.sort_values(ascending=False)
cum_ratio = (top5_sorted_desc / total_valid * 100).cumsum()

print(top5_sorted_desc)
print(top5_ratio.round(2))
print("累積佔比:")
print(cum_ratio.round(2))

# %%


# ========== 橫向長條圖  ==========
fig, ax1 = plt.subplots(figsize=(10, 6))

bars = ax1.barh(
    top5.index.astype(str),
    top5.values,
    color="#88B0A4",
    height=0.55,
    
)

ax1.set_title("北北基桃交通事故主要肇因 TOP 5", fontsize=15, pad=15)
ax1.set_xlabel("事故件數")
ax1.set_ylabel("")  # 肇因類別文字已經在Y軸標籤上，不需要重複的軸標題
ax1.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

# 長條尾端標示「件數 + 佔比」
for bar, count, ratio in zip(bars, top5.values, top5_ratio.values):
    ax1.text(
        bar.get_width() + max(top5.values) * 0.01,  # 稍微往右偏移，避免貼字
        bar.get_y() + bar.get_height() / 2,
        f"{count:,} 件（{ratio:.1f}%）",
        va="center", ha="left", fontsize=10
    )

# 讓右側留一點空間放文字，避免被裁切
ax1.set_xlim(0, max(top5.values) * 1.25)


fig.subplots_adjust(left=0.28, right=0.85, top=0.85, bottom=0.1)
os.makedirs("./outputs", exist_ok=True)
plt.savefig("./outputs/橫條圖碧綠.png", dpi=300, transparent=True, bbox_inches="tight")

plt.show()

