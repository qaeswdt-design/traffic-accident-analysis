import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

import common

common.setup_matplotlib_font()

# ========== 資料讀取 ==========
df = common.load_table("tma2_data")

# ========== 肇因大類合併 ==========
df = common.merge_yield_categories(df)
col_name = "肇因大類"

# ========== 三層篩選:第1當事人 + 北北基桃 + 排除無效肇因 ==========
df_first = common.filter_first_party_four_cities(df, add_city_column=False)
df_filtered = common.exclude_invalid_cause(df_first, col_name)

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
plt.savefig(common.output_path("橫條圖碧綠.png"), dpi=300, transparent=True, bbox_inches="tight")

plt.show()
