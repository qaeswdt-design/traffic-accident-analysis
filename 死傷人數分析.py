import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import os

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

os.makedirs("./outputs", exist_ok=True)

# ========== 資料讀取:A1(死亡)+ A2(受傷) ==========
db_path = "./data.db"
conn = sqlite3.connect(db_path)
df_a2 = pd.read_sql("SELECT * FROM tma2_data", conn)
df_a1 = pd.read_sql("SELECT * FROM tma1_data", conn)
conn.close()

casualty_col = "死亡受傷人數"

def parse_casualty(text):
    if pd.isna(text):
        return pd.Series([None, None])
    try:
        parts = str(text).split(";")
        死亡數 = int(parts[0].replace("死亡", ""))
        受傷數 = int(parts[1].replace("受傷", ""))
        return pd.Series([死亡數, 受傷數])
    except (IndexError, ValueError):
        return pd.Series([None, None])

df_a2[["死亡數", "受傷數"]] = df_a2[casualty_col].apply(parse_casualty)
df_a1[["死亡數", "受傷數"]] = df_a1[casualty_col].apply(parse_casualty)

df_a2["資料來源"] = "A2"
df_a1["資料來源"] = "A1"

common_cols = list(set(df_a1.columns) & set(df_a2.columns))
df_combined = pd.concat([df_a1[common_cols], df_a2[common_cols]], ignore_index=True)

location_col = "發生地點"
party_col = "當事者順位"
vtype_col = "當事者區分-類別-大類別名稱-車種"

# ========== 兩層篩選:第1當事人 + 北北基桃 ==========
df_first = df_combined[df_combined[party_col].astype(str).str.contains("1", na=False)]
city_pattern = "桃園市|新北市|臺北市|台北市|基隆市"
df_first = df_first[df_first[location_col].astype(str).str.contains(city_pattern, na=False)].copy()

# ========== 主要車種(保留「人」) ==========
main_vtypes_with_pedestrian = ["機車", "小客車(含客、貨兩用)", "人", "慢車", "小貨車", "大貨車", "大客車"]
df_vtype = df_first[df_first[vtype_col].isin(main_vtypes_with_pedestrian)]

# ========== 依車種加總死亡數/受傷數 ==========
casualty_by_vtype = df_vtype.groupby(vtype_col)[["死亡數", "受傷數"]].sum()
casualty_by_vtype = casualty_by_vtype.loc[main_vtypes_with_pedestrian]

# ========== 核心指標:死亡率(Case Fatality Rate) ==========
casualty_by_vtype["死亡率"] = (
    casualty_by_vtype["死亡數"]
    / (casualty_by_vtype["死亡數"] + casualty_by_vtype["受傷數"])
    * 100
)

# 依死亡率排序(由大到小),由上到下呈現(barh邏輯,由小到大畫,最大放最上面)
casualty_sorted = casualty_by_vtype.sort_values("死亡率", ascending=True)

print("各車種死亡率排名(由高到低):")
print(casualty_by_vtype.sort_values("死亡率", ascending=False).round(2))
# %%


# ========== 單一張圖:死亡率排名 ==========
fig, ax = plt.subplots(figsize=(9, 6))

bars = ax.barh(casualty_sorted.index, casualty_sorted["死亡率"], color="#8B3A3A")

ax.set_title("北北基桃各車種死亡率比較（死亡人數 ÷ 死亡+受傷人數）", fontsize=14, pad=15)
ax.set_xlabel("死亡率（%）")

for bar, rate, death, injury in zip(
    bars, casualty_sorted["死亡率"], casualty_sorted["死亡數"], casualty_sorted["受傷數"]
):
    ax.text(
        bar.get_width() + 0.02,
        bar.get_y() + bar.get_height() / 2,
        f"{rate:.2f}%（死{int(death)}／傷{int(injury):,}）",
        va="center", fontsize=9
    )

fig.subplots_adjust(left=0.2, right=0.97, top=0.9, bottom=0.12)
plt.savefig("./outputs/07_死亡率_車種.png", dpi=300, transparent=True, bbox_inches="tight")
plt.show()