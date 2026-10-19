import matplotlib.pyplot as plt
import pandas as pd

import common

common.setup_matplotlib_font()

# ========== 資料讀取 ==========
df = common.load_table("tma2_data")

# ========== 兩層篩選:第1當事人 + 北北基桃 ==========
df_first = common.filter_first_party_four_cities(df)

# ========== 發生時間 → 小時 → 時段區間 ==========
df_first = common.add_period_column(df_first, "發生時間")

city_order = common.CITY_ORDER
period_order = common.PERIOD_ORDER

# ========== 縣市 x 時段區間 交叉表 ==========
cross = pd.crosstab(df_first["時段區間"], df_first["縣市"])
cross = cross.loc[period_order, city_order]

# ========== 換算成「每十萬輛車事故件數」,再除以時段小時數 ==========
# 時段長短不同(早峰3小時、日間7小時、晚峰4小時、夜間10小時),
# 直接比件數會讓長時段看起來比較危險,所以換成「每小時」再比較。
cross_per_vehicle = common.per_100k_vehicles(cross)
hours = pd.Series(common.PERIOD_HOURS)[period_order]
cross_per_vehicle_hour = cross_per_vehicle.div(hours, axis=0)

print("原始件數:")
print(cross)
print()
print("每十萬輛車事故件數(整個時段合計):")
print(cross_per_vehicle.round(2))
print()
print("每十萬輛車、每小時事故件數(時段長度標準化後):")
print(cross_per_vehicle_hour.round(2))

# ========== 分組橫向長條圖 ==========
periods = cross_per_vehicle_hour.index.tolist()
counties = cross_per_vehicle_hour.columns.tolist()

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
        cross_per_vehicle_hour[county].values,
        height=bar_height,
        label=county,
        color=colors[i],
    )

ax.set_yticks(list(y_base))
ax.set_yticklabels(periods)
ax.invert_yaxis()
ax.set_xlabel("每十萬輛車、每小時事故件數")
ax.set_title("北北基桃各時段事故率比較（車輛數權重後、每小時平均）", fontsize=15, pad=15)
ax.legend(title="縣市", loc="lower right")

fig.subplots_adjust(left=0.18, right=0.95, top=0.9, bottom=0.1)
plt.savefig(common.output_path("時段區間事故分析.png"), dpi=300, transparent=True, bbox_inches="tight")

plt.show()
