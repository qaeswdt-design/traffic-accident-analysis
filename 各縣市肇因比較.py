import matplotlib.pyplot as plt
import pandas as pd

import common

common.setup_matplotlib_font()

# ========== 資料讀取 ==========
df = common.load_table("tma2_data")

# ========== 肇因大類合併 ==========
df = common.merge_yield_categories(df)
col_name = "肇因大類"

# ========== 三層篩選:第1當事人 + 北北基桃 + 排除無效肇因 ==========
df_first = common.filter_first_party_four_cities(df)
df_filtered = common.exclude_invalid_cause(df_first, col_name)

overall_top5 = df_filtered[col_name].value_counts().head(5).index.tolist()

city_order = common.CITY_ORDER
cross = pd.crosstab(df_filtered[col_name], df_filtered["縣市"])
cross = cross.loc[overall_top5, city_order]

# ========== 換算成「每十萬輛車事故件數」 ==========
cross_per_vehicle = common.per_100k_vehicles(cross)

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
plt.savefig(common.output_path("北北基桃各縣市主要肇因比較（車輛數權重後）TOP 5.png"), dpi=300, transparent=True, bbox_inches="tight")

plt.show()
