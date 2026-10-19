import sqlite3,os
import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

# ========== 資料讀取(1-8月全部合併,來自 tma2_data) ==========
db_path = "./data.db"
conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT * FROM tma2_data", conn)
conn.close()

location_col = "發生地點"
party_col = "當事者順位"
light_col = "光線名稱"

# ========== 兩層篩選:第1當事人 + 北北基桃(邏輯不變) ==========
df_first = df[df[party_col].astype(str).str.contains("1", na=False)]

city_pattern = "桃園市|新北市|臺北市|台北市|基隆市"
df_first = df_first[df_first[location_col].astype(str).str.contains(city_pattern, na=False)]

df_first = df_first.copy()
df_first["縣市"] = df_first[location_col].str.extract(f"({city_pattern})")
df_first["縣市"] = df_first["縣市"].replace({"台北市": "臺北市"})

# ========== 排除光線缺值 ==========
df_first = df_first[df_first[light_col].notna()]

# ========== 縣市 x 光線 交叉表(用「列百分比」看組成差異) ==========
city_order = ["新北市", "桃園市", "臺北市", "基隆市"]
light_order = ["有照明且開啟", "有照明未開啟或故障", "無照明"]

cross_count = pd.crosstab(df_first["縣市"], df_first[light_col])
cross_count = cross_count.loc[city_order, light_order]

cross_pct = cross_count.div(cross_count.sum(axis=1), axis=0) * 100

print("原始件數:")
print(cross_count)
print()
print("各縣市內光線組成佔比(%):")
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
ax.set_xlabel("該縣市內事故的光線狀態佔比（%）")
ax.set_title("北北基桃各縣市光線狀態組成比較", fontsize=14, pad=15)
ax.legend(title="縣市", loc="lower right")

fig.subplots_adjust(left=0.24, right=0.95, top=0.9, bottom=0.1)
os.makedirs("./outputs", exist_ok=True)
plt.savefig("./outputs/依光線區分.png", dpi=300, transparent=True, bbox_inches="tight")

plt.show()