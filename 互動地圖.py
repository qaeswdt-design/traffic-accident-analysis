import sqlite3, os, io, zipfile
import pandas as pd
import geopandas as gpd
import requests
import urllib3
import folium
from folium.plugins import HeatMap, GroupedLayerControl

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
month_col = "month"

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

# ========== 發生時間 → 小時 → 時段區間(沿用「依時間區分.py」的分類邏輯) ==========
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

print(df_first["時段區間"].value_counts())
print(df_first[month_col].value_counts().sort_index())

# ========== 建立地圖(以北北基桃中心點為初始視角) ==========
center_lat = df_first[lat_col].mean()
center_lon = df_first[lon_col].mean()

m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="OpenStreetMap")

period_order = ["早峰(06-08)", "日間(09-15)", "晚峰(16-19)", "夜間(20-05)"]
month_order = sorted(df_first[month_col].dropna().unique().tolist())

# ========== 時段圖層(可複選疊圖比較) ==========
period_layers = []
for period in period_order:
    sub = df_first[df_first["時段區間"] == period]
    points = sub[[lat_col, lon_col]].values.tolist()

    fg = folium.FeatureGroup(name=f"{period}（{len(points):,} 件）", show=(period == period_order[0]))
    HeatMap(points, radius=8, blur=10, max_zoom=13).add_to(fg)
    fg.add_to(m)
    period_layers.append(fg)

# ========== 月份圖層(單選切換,一次只顯示一個月,為後續網站月份切換功能鋪路) ==========
# month_order 直接從資料庫實際存在的月份取得,之後資料庫新增月份(如115_09)、重新執行本腳本
# 就會自動多出一個對應的月份圖層,不需要修改程式碼。
month_layers = []

# 總計圖層放在1月之前,預設開啟(其餘月份預設關閉)
total_points = df_first[[lat_col, lon_col]].values.tolist()
total_fg = folium.FeatureGroup(name=f"總計（{len(total_points):,} 件）", show=True)
HeatMap(total_points, radius=8, blur=10, max_zoom=13).add_to(total_fg)
total_fg.add_to(m)
month_layers.append(total_fg)

for month in month_order:
    sub = df_first[df_first[month_col] == month]
    points = sub[[lat_col, lon_col]].values.tolist()

    fg = folium.FeatureGroup(name=f"{month}（{len(points):,} 件）", show=False)
    HeatMap(points, radius=8, blur=10, max_zoom=13).add_to(fg)
    fg.add_to(m)
    month_layers.append(fg)

# 時段:checkbox可複選;月份:radio單選(兩組互不影響,各自用獨立的GroupedLayerControl)
GroupedLayerControl(groups={"時段(可複選)": period_layers}, exclusive_groups=False, collapsed=False).add_to(m)
GroupedLayerControl(groups={"月份(單選切換)": month_layers}, exclusive_groups=True, collapsed=False).add_to(m)

os.makedirs("./outputs", exist_ok=True)
output_path = "./outputs/interactive_map.html"
m.save(output_path)
print(f"互動地圖已輸出: {output_path}")
