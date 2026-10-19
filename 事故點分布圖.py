import sqlite3, os, io, zipfile
import matplotlib
matplotlib.use("Agg")  # 無圖形介面環境下也能存檔(不呼叫plt.show()時可省略,保留以防萬一)
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import geopandas as gpd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

# ========== 背景縣市界線(北北基桃):優先讀本機快取,沒有才向內政部(TGOS)下載 ==========
BOUNDARY_CACHE = "./geo_boundary/北北基桃縣市界.geojson"
BOUNDARY_ZIP_URL = "https://www.tgos.tw/tgos/VirtualDir/Product/85bc9c19-a076-4d83-8955-eeecf2ebdae8/COUNTY_MOI_1140318_.zip"

def load_city_boundary():
    if os.path.exists(BOUNDARY_CACHE):
        return gpd.read_file(BOUNDARY_CACHE)

    print("本機找不到縣市界線快取,正在向內政部(TGOS)下載全國縣市界線資料...")
    os.makedirs(os.path.dirname(BOUNDARY_CACHE), exist_ok=True)
    resp = requests.get(BOUNDARY_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, verify=False)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        gml_name = [n for n in z.namelist() if n.endswith(".gml")][0]
        z.extract(gml_name, os.path.dirname(BOUNDARY_CACHE))

    gdf_all = gpd.read_file(os.path.join(os.path.dirname(BOUNDARY_CACHE), gml_name))
    gdf_all = gdf_all.set_crs(epsg=4326)  # 原始GML未內含CRS,座標本身即為WGS84經緯度

    target_cities = ["臺北市", "新北市", "基隆市", "桃園市"]
    gdf_target = gdf_all[gdf_all["名稱"].isin(target_cities)][["名稱", "geometry"]].copy()
    gdf_target.to_file(BOUNDARY_CACHE, driver="GeoJSON")
    print(f"縣市界線已快取: {BOUNDARY_CACHE}")
    return gdf_target

city_boundary = load_city_boundary()
city_union = city_boundary.union_all()

# ========== 資料讀取 ==========
db_path = "./data.db"
conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT * FROM tma2_data", conn)
conn.close()

location_col = "發生地點"
party_col = "當事者順位"
time_col = "發生時間"
lon_col = "經度"
lat_col = "緯度"

# ========== 兩層篩選:第1當事人 + 北北基桃(邏輯與其他分析腳本一致) ==========
df_first = df[df[party_col].astype(str).str.contains("1", na=False)]

city_pattern = "桃園市|新北市|臺北市|台北市|基隆市"
df_first = df_first[df_first[location_col].astype(str).str.contains(city_pattern, na=False)].copy()

# ========== 排除座標異常值:改用「是否落在北北基桃行政區界線內」做精確過濾 ==========
# (取代粗略的經緯度矩形框,可一併排除外海離島座標誤植的離群點)
points_geom = gpd.points_from_xy(df_first[lon_col], df_first[lat_col])
within_mask = gpd.GeoSeries(points_geom, index=df_first.index).within(city_union)
before_n = df_first.shape[0]
df_first = df_first[within_mask]
print(f"界線內過濾: {before_n} → {df_first.shape[0]}（排除{before_n - df_first.shape[0]}筆座標落在界線外的離群點）")

# ========== 發生時間 → 小時 → 時段區間 ==========
df_first["發生時段_小時"] = (df_first[time_col] // 10000)

def classify_period(hour):
    if pd.isna(hour):
        return None
    hour = int(hour)
    if 6 <= hour <= 8:
        return "早峰(06-08)"
    elif 9 <= hour <= 15:
        return "日間(09-15)"
    elif 16 <= hour <= 19:
        return "晚峰(16-19)"
    else:
        return "夜間(20-05)"

df_first["時段區間"] = df_first["發生時段_小時"].apply(classify_period)

period_order = ["早峰(06-08)", "日間(09-15)", "晚峰(16-19)", "夜間(20-05)"]

# ========== 顯示範圍:依實際事故點分布抓範圍,避免外島界線把畫面拉遠 ==========
pad = 0.03
xlim = (df_first[lon_col].min() - pad, df_first[lon_col].max() + pad)
ylim = (df_first[lat_col].min() - pad, df_first[lat_col].max() + pad)

# ========== 密度配色:沿用現有圖表的蒔色系(#8B3A3A深蒔),淺→深表示密度低→高 ==========
density_cmap = LinearSegmentedColormap.from_list("蒔色密度", ["#F2F2F2", "#DDA9A9", "#C44E52", "#8B3A3A"])

# ========== 色階上限:用百分位數截斷,避免「地址轉座標失敗時的行政區代表點」
# (少數座標被大量不同地址共用,屬於資料誤植而非真實熱點)把色階拉爆、蓋掉其他真實熱點差異 ==========
import numpy as np
gridsize = 60
all_counts = []
for period in period_order:
    sub = df_first[df_first["時段區間"] == period]
    hb_tmp = plt.hexbin(sub[lon_col], sub[lat_col], gridsize=gridsize, mincnt=1,
                         extent=(xlim[0], xlim[1], ylim[0], ylim[1]))
    all_counts.append(hb_tmp.get_array())
    plt.close()
vmax = np.percentile(np.concatenate(all_counts), 98)
print(f"色階上限(98百分位): {vmax:.0f}件/格(原始最大值: {max(c.max() for c in all_counts):.0f}件/格)")

# ========== 2x2 四張時段密度圖(hexbin,背景疊上北北基桃縣市界線) ==========
fig, axes = plt.subplots(2, 2, figsize=(12, 12), sharex=True, sharey=True)

for ax, period in zip(axes.flat, period_order):
    sub = df_first[df_first["時段區間"] == period]

    city_boundary.plot(ax=ax, facecolor="#F2F2F2", edgecolor="#999999", linewidth=0.8, zorder=0)
    hb = ax.hexbin(
        sub[lon_col], sub[lat_col],
        gridsize=gridsize, mincnt=1, cmap=density_cmap, vmin=0, vmax=vmax,
        extent=(xlim[0], xlim[1], ylim[0], ylim[1]),
        zorder=1,
    )

    ax.set_title(f"{period}（{len(sub):,} 件）", fontsize=13)
    ax.set_aspect("equal")
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_xlabel("經度")
    ax.set_ylabel("緯度")
    fig.colorbar(hb, ax=ax, label=f"事故件數(上限{vmax:.0f}+)", shrink=0.75, extend="max")

fig.suptitle("北北基桃交通事故密度分布（依時段）", fontsize=16, y=0.98)
fig.tight_layout(rect=[0, 0, 1, 0.96])

os.makedirs("./outputs", exist_ok=True)
plt.savefig("./outputs/scatter_各時段.png", dpi=300, transparent=True, bbox_inches="tight")
print("靜態密度圖已輸出: ./outputs/scatter_各時段.png")
