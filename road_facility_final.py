import sqlite3, os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "data.db")
OUT = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUT, exist_ok=True)

conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT * FROM tma2_data", conn)
conn.close()

location_col = "發生地點"
party_col = "當事者順位"
signal_col = "號誌-號誌種類名稱"
lane_col = "車道劃分設施-分向設施大類別名稱"

# ========== 兩層篩選:第1當事人 + 北北基桃(與其他頁一致) ==========
df_first = df[df[party_col].astype(str).str.contains("1", na=False)]
city_pattern = "桃園市|新北市|臺北市|台北市|基隆市"
df_first = df_first[df_first[location_col].astype(str).str.contains(city_pattern, na=False)]
df_first = df_first.copy()
df_first["縣市"] = df_first[location_col].str.extract(f"({city_pattern})")
df_first["縣市"] = df_first["縣市"].replace({"台北市": "臺北市"})

# ========== 圖1：號誌種類分布 TOP5 (橫條圖，比照肇因TOP5的風格) ==========
df_signal = df_first[df_first[signal_col].notna()]
top_signal = df_signal[signal_col].value_counts().head(5).sort_values(ascending=True)
total_signal = df_signal[signal_col].notna().sum()
signal_ratio = top_signal / total_signal * 100

fig, ax1 = plt.subplots(figsize=(10, 5.2))
bars = ax1.barh(top_signal.index.astype(str), top_signal.values, color="#88B0A4", height=0.55)
ax1.set_title("北北基桃事故現場號誌類型分布", fontsize=15, pad=15)
ax1.set_xlabel("事故件數")
ax1.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
for bar, count, ratio in zip(bars, top_signal.values, signal_ratio.values):
    ax1.text(bar.get_width() + max(top_signal.values) * 0.01, bar.get_y() + bar.get_height() / 2,
              f"{count:,} 件（{ratio:.1f}%）", va="center", ha="left", fontsize=10)
ax1.set_xlim(0, max(top_signal.values) * 1.3)
fig.subplots_adjust(left=0.32, right=0.85, top=0.85, bottom=0.12)
plt.savefig(os.path.join(OUT, "號誌類型分布.png"), dpi=300, transparent=True, bbox_inches="tight")
plt.close(fig)

print("號誌類型 TOP5:")
print(top_signal.sort_values(ascending=False))
print((signal_ratio.sort_values(ascending=False)).round(2))
print()

# ========== 圖2：車道劃分設施(標線) 各縣市組成比較 (比照光線分析的分組橫條圖風格) ==========
df_lane = df_first[df_first[lane_col].notna()]
city_order = ["新北市", "桃園市", "臺北市", "基隆市"]
lane_order = df_lane[lane_col].value_counts().head(4).index.tolist()

cross_count = pd.crosstab(df_lane["縣市"], df_lane[lane_col])
cross_count = cross_count.loc[city_order, [c for c in lane_order if c in cross_count.columns]]
cross_pct = cross_count.div(cross_count.sum(axis=1), axis=0) * 100

print("車道劃分設施 縣市x類別 件數:")
print(cross_count)
print("佔比(%):")
print(cross_pct.round(1))

lanes = cross_pct.columns.tolist()
cities = cross_pct.index.tolist()
n_lanes = len(lanes)
n_cities = len(cities)
bar_height = 0.18
y_base = range(n_lanes)

fig, ax = plt.subplots(figsize=(10, 5.2))
colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]
for i, city in enumerate(cities):
    offset = (i - (n_cities - 1) / 2) * bar_height
    y_pos = [y + offset for y in y_base]
    ax.barh(y_pos, cross_pct.loc[city].values, height=bar_height, label=city, color=colors[i])
ax.set_yticks(list(y_base))
ax.set_yticklabels(lanes)
ax.invert_yaxis()
ax.set_xlabel("該縣市內事故的車道劃分設施佔比（%）")
ax.set_title("北北基桃各縣市車道劃分設施（標線）組成比較", fontsize=14, pad=15)
ax.legend(title="縣市", loc="lower right")
fig.subplots_adjust(left=0.28, right=0.95, top=0.9, bottom=0.1)
plt.savefig(os.path.join(OUT, "車道劃分設施分布.png"), dpi=300, transparent=True, bbox_inches="tight")
plt.close(fig)

print("done, saved to", OUT)
