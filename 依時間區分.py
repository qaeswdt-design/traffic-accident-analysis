import sqlite3,os
import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

# ========== 資料讀取 ==========
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
road_type_col = "道路型態大類別名稱"
speed_col = "速限-第1當事者"

# ========== 兩層篩選:第1當事人 + 北北基桃(邏輯不變) ==========
df_first = df[df[party_col].astype(str).str.contains("1", na=False)]
city_pattern = "桃園市|新北市|臺北市|台北市|基隆市"
df_first = df_first[df_first[location_col].astype(str).str.contains(city_pattern, na=False)]

# ========== 排除無效肇因(邏輯不變) ==========
exclude_keywords = ["尚未發現肇因", "未發現肇事因素"]
mask_exclude = df_first[col_name].astype(str).apply(
    lambda x: any(kw in x for kw in exclude_keywords)
)
df_filtered = df_first[~mask_exclude].copy()

# ========== 新增:排除速限異常值(0與過小的非標準速限值) ==========
# 正常速限應為30/40/50/60/70/80/90/100/110等標準值，
# 0與個位數/十位數的零星小值判斷為資料缺失或標示異常，直接排除
abnormal_speed_values = [0, 1, 2, 3, 4, 5, 10, 15, 20, 25]
before_n = df_filtered.shape[0]
df_filtered = df_filtered[~df_filtered[speed_col].isin(abnormal_speed_values)]
after_n = df_filtered.shape[0]
print(f"排除速限異常值: {before_n} → {after_n}（排除{before_n - after_n}筆）")

# ========== 只保留交岔路/單路部分/圓環廣場(排除樣本過少的平交道n=2、定義不清的其他) ==========
valid_road_types = ["交岔路", "單路部分", "圓環廣場"]
df_filtered = df_filtered[df_filtered[road_type_col].isin(valid_road_types)]

# ========== 整體TOP5肇因(當作比較基準) ==========
overall_top5 = df_filtered[col_name].value_counts().head(5).index.tolist()
df_top5 = df_filtered[df_filtered[col_name].isin(overall_top5)]

# ========== 道路型態 x 肇因 交叉表(用「列百分比」看組成差異，而非絕對件數) ==========
cross_count = pd.crosstab(df_top5[road_type_col], df_top5[col_name])
cross_count = cross_count[overall_top5]  # 固定欄位順序
cross_count = cross_count.loc[valid_road_types]  # 固定列順序

cross_pct = cross_count.div(cross_count.sum(axis=1), axis=0) * 100

print("原始件數:")
print(cross_count)
print()
print("各道路型態內的肇因組成佔比(%):")
print(cross_pct.round(1))

# ========== 分組橫向長條圖(用組成佔比,呈現「形狀」差異) ==========
causes = cross_pct.columns.tolist()
road_types = cross_pct.index.tolist()

n_causes = len(causes)
n_types = len(road_types)
bar_height = 0.22
y_base = range(n_causes)

fig, ax = plt.subplots(figsize=(10, 6.5))
colors = ["#4C72B0", "#DD8452", "#55A868"]

for i, rtype in enumerate(road_types):
    offset = (i - (n_types - 1) / 2) * bar_height
    y_pos = [y + offset for y in y_base]
    ax.barh(
        y_pos,
        cross_pct.loc[rtype].values,
        height=bar_height,
        label=rtype,
        color=colors[i],
    )

ax.set_yticks(list(y_base))
ax.set_yticklabels(causes)
ax.invert_yaxis()
ax.set_xlabel("該道路型態內的肇因佔比（%）")
ax.set_title("道路型態 × 主要肇因組成比較（路口 vs 路段 vs 圓環）", fontsize=14, pad=15)
ax.legend(title="道路型態", loc="lower right")


os.makedirs("./outputs", exist_ok=True)
plt.savefig("./outputs/道路型態內的肇因.png", dpi=300, transparent=True, bbox_inches="tight")

fig.subplots_adjust(left=0.24, right=0.95, top=0.9, bottom=0.1)
plt.show()