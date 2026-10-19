import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import os

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

os.makedirs("./outputs", exist_ok=True)

# ========== 資料讀取(1-8月全部合併) ==========
db_path = "./data.db"
conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT * FROM tma2_data", conn)
conn.close()

location_col = "發生地點"
party_col = "當事者順位"
vtype_col = "當事者區分-類別-大類別名稱-車種"
gender_col = "當事者屬-性-別名稱"
age_col = "當事者事故發生時年齡"

# ========== 兩層篩選:第1當事人 + 北北基桃 ==========
df_first = df[df[party_col].astype(str).str.contains("1", na=False)]
city_pattern = "桃園市|新北市|臺北市|台北市|基隆市"
df_first = df_first[df_first[location_col].astype(str).str.contains(city_pattern, na=False)].copy()

df_first["縣市"] = df_first[location_col].str.extract(f"({city_pattern})")
df_first["縣市"] = df_first["縣市"].replace({"台北市": "臺北市"})

# ========== 清理1:車種排除「人」(行人) ==========

df_clean = df_first[df_first[vtype_col] != "人"]

# ========== 清理2:性別只保留男/女 ==========
df_clean = df_clean[df_clean[gender_col].isin(["男", "女"])]

# ========== 清理3:年齡排除 <=0 與 >100 ==========
df_clean = df_clean[(df_clean[age_col] > 17) & (df_clean[age_col] <= 100)]

print(f"原始(第1當事人+北北基桃): {df_first.shape[0]} → 三項清理後: {df_clean.shape[0]}")

# =========================================================
# 圖1:年齡分布,拆男女比較(箱型圖)— 維持性別設計,不變
# =========================================================
fig1, ax1 = plt.subplots(figsize=(7, 6))

male_age = df_clean[df_clean[gender_col] == "男"][age_col]
female_age = df_clean[df_clean[gender_col] == "女"][age_col]

bp = ax1.boxplot(
    [male_age, female_age],
    tick_labels=["男", "女"],
    patch_artist=True,
    widths=0.4,
)
colors_box = ["#4C72B0", "#DD8452"]
for patch, color in zip(bp["boxes"], colors_box):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

ax1.set_title("事故當事者年齡分布（男 vs 女）", fontsize=14, pad=15)
ax1.set_ylabel("年齡")

for i, age_series in enumerate([male_age, female_age], start=1):
    median_val = age_series.median()
    ax1.text(i, median_val, f" 中位數:{median_val:.0f}", va="center", fontsize=9)

plt.tight_layout()
plt.savefig("./outputs/06_年齡分布_性別.png", dpi=300, transparent=True, bbox_inches="tight")
plt.show()

print("\n年齡統計(依性別):")
print(df_clean.groupby(gender_col)[age_col].describe()[["count", "mean", "50%", "min", "max"]])

# =========================================================
# 圖2:車種 x 縣市 事故率比較（車輛數權重後）— 改成縣市角度
# =========================================================
main_vtypes = ["機車", "小客車(含客、貨兩用)", "慢車", "小貨車", "大貨車", "大客車"]
df_vtype = df_clean[df_clean[vtype_col].isin(main_vtypes)]

vehicle_registration = {
    "新北市": 3_381_671,
    "桃園市": 2_328_640,
    "臺北市": 1_720_965,
    "基隆市": 302_691,
}
city_order = ["新北市", "桃園市", "臺北市", "基隆市"]

cross_vtype = pd.crosstab(df_vtype["縣市"], df_vtype[vtype_col])
cross_vtype = cross_vtype.loc[city_order, main_vtypes]

cross_vtype_weighted = cross_vtype.astype(float)
for city in city_order:
    cross_vtype_weighted.loc[city] = cross_vtype.loc[city] / vehicle_registration[city] * 100_000

print("\n車種 x 縣市 原始件數:")
print(cross_vtype)
print("\n每十萬輛車事故率(車種 x 縣市,車輛數權重後):")
print(cross_vtype_weighted.round(2))

fig2, ax2 = plt.subplots(figsize=(10, 6.5))
vtypes = cross_vtype_weighted.columns.tolist()
cities = cross_vtype_weighted.index.tolist()

bar_height = 0.18
y_base = range(len(vtypes))
colors_city = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]

for i, city in enumerate(cities):
    offset = (i - (len(cities) - 1) / 2) * bar_height
    y_pos = [y + offset for y in y_base]
    ax2.barh(
        y_pos,
        cross_vtype_weighted.loc[city].values,
        height=bar_height,
        label=city,
        color=colors_city[i],
    )

ax2.set_yticks(list(y_base))
ax2.set_yticklabels(vtypes)
ax2.invert_yaxis()
ax2.set_xlabel("每十萬輛車事故件數")
ax2.set_title("車種 × 縣市 事故率比較（車輛數權重後）", fontsize=14, pad=15)
ax2.legend(title="縣市", loc="lower right")

fig2.subplots_adjust(left=0.24, right=0.95, top=0.9, bottom=0.1)
plt.savefig("./outputs/06_車種_縣市_權重.png", dpi=300, transparent=True, bbox_inches="tight")
plt.show()

# =========================================================
# 圖3:年齡分組(十年一段) x 車種 交叉 — 維持原設計,不變
# =========================================================
age_bins = list(range(0, 110, 10))
age_labels = [f"{age_bins[i]}-{age_bins[i+1]-1}" for i in range(len(age_bins)-1)]
df_vtype = df_vtype.copy()
df_vtype["年齡分組"] = pd.cut(df_vtype[age_col], bins=age_bins, labels=age_labels, right=False)

cross_age_vtype = pd.crosstab(df_vtype["年齡分組"], df_vtype[vtype_col])
cross_age_vtype = cross_age_vtype[main_vtypes]
cross_age_vtype = cross_age_vtype[cross_age_vtype.sum(axis=1) > 0]

print("\n年齡分組 x 車種 原始件數:")
print(cross_age_vtype)

fig3, ax3 = plt.subplots(figsize=(10, 7))
age_groups = cross_age_vtype.index.tolist()

colors_vtype = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2", "#CCB974"]
for vtype, color in zip(main_vtypes, colors_vtype):
    ax3.plot(age_groups, cross_age_vtype[vtype].values, marker="o", label=vtype, color=color)

ax3.set_xlabel("年齡分組")
ax3.set_ylabel("事故件數")
ax3.set_title("各年齡層事故車種分布", fontsize=14, pad=15)
ax3.legend(title="車種", loc="upper right", fontsize=8)
plt.xticks(rotation=30, ha="right")

plt.tight_layout()
plt.savefig("./outputs/06_年齡分組_車種.png", dpi=300, transparent=True, bbox_inches="tight")
plt.show()