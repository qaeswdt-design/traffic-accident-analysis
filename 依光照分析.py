import matplotlib.pyplot as plt
import pandas as pd

import common

common.setup_matplotlib_font()

# ========== 資料讀取(1-8月全部合併,來自 tma2_data) ==========
df = common.load_table("tma2_data")

light_col = "光線名稱"

# ========== 兩層篩選:第1當事人 + 北北基桃 ==========
df_first = common.filter_first_party_four_cities(df)

# ========== 排除光線缺值 ==========
df_first = df_first[df_first[light_col].notna()]

# ========== 縣市 x 光線 交叉表(用「列百分比」看組成差異) ==========
# 注意:光線名稱欄位實際只有這三種值,記錄的是「道路照明設施狀態」,不是自然光線,
# 而且涵蓋全部時段:日間事故多半被記成「有照明未開啟或故障」(白天路燈本來就沒開),
# 所以這一類佔比高不等於路燈壞掉。
city_order = common.CITY_ORDER
light_order = ["有照明且開啟", "有照明未開啟或故障", "無照明"]

cross_count = pd.crosstab(df_first["縣市"], df_first[light_col])
cross_count = cross_count.loc[city_order, light_order]

cross_pct = cross_count.div(cross_count.sum(axis=1), axis=0) * 100

print("原始件數:")
print(cross_count)
print()
print("各縣市內照明設施狀態組成佔比(%,含日間事故):")
print(cross_pct.round(1))

# ========== 分組橫向長條圖 ==========
lights = cross_pct.columns.tolist()
cities = cross_pct.index.tolist()

n_lights = len(lights)
n_cities = len(cities)
bar_height = 0.18
y_base = range(n_lights)

fig, ax = plt.subplots(figsize=(10, 6))
colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]

for i, city in enumerate(cities):
    offset = (i - (n_cities - 1) / 2) * bar_height
    y_pos = [y + offset for y in y_base]
    ax.barh(
        y_pos,
        cross_pct.loc[city].values,
        height=bar_height,
        label=city,
        color=colors[i],
    )

ax.set_yticks(list(y_base))
ax.set_yticklabels(lights)
ax.invert_yaxis()
ax.set_xlabel("該縣市內事故的照明設施狀態佔比（%，含日間事故）")
ax.set_title("北北基桃各縣市道路照明設施狀態組成比較（全時段事故）", fontsize=14, pad=15)
ax.legend(title="縣市", loc="lower right")

fig.subplots_adjust(left=0.24, right=0.95, top=0.9, bottom=0.1)
plt.savefig(common.output_path("依光線區分.png"), dpi=300, transparent=True, bbox_inches="tight")

plt.show()
