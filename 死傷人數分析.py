import matplotlib.pyplot as plt
import pandas as pd

import common

common.setup_matplotlib_font()

# ========== 資料讀取:A1(死亡)+ A2(受傷) ==========
df_a2 = common.load_table("tma2_data")
df_a1 = common.load_table("tma1_data")

# A1 是整份 JSON、A2 是逐月 CSV,期間可能不同;
# 死亡率的分子(死亡)與分母(死亡+受傷)必須落在同一段期間,所以把 A1 截到 A2 的最後一天。
df_a1 = common.restrict_a1_to_a2_period(df_a1, df_a2)

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

vtype_col = "當事者區分-類別-大類別名稱-車種"

# ========== 兩層篩選:第1當事人 + 北北基桃 ==========
# 死亡受傷人數是整起事故的合計,每起事故只能取一列(第1當事者)來加總,否則會重複計算
df_first = common.filter_first_party_four_cities(df_combined, add_city_column=False)

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
plt.savefig(common.output_path("07_死亡率_車種.png"), dpi=300, transparent=True, bbox_inches="tight")
plt.show()
