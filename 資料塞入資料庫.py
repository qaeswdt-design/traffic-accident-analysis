# ========== 套件載入,定義資料庫 ==========
import os
import re
import glob
import zipfile
import json
import pandas as pd
import sqlite3

# 用程式檔案自身所在資料夾組路徑,換電腦/換隨身碟代號都不受影響
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

db_path = os.path.join(BASE_DIR, "data.db")
download_dir = os.path.join(BASE_DIR, "downloads")

conn = sqlite3.connect(db_path)

# %%

# ========== A2 資料(CSV,來源:NPA_TMA2)—— 自動掃描月份 ==========

# 找出 downloads 資料夾裡所有符合 115_NPA_TMA2_0X.zip / 115_NPA_TMA2_1X.zip 命名規則的檔案
pattern = os.path.join(download_dir, "115_NPA_TMA2_*.zip")
zip_files = sorted(glob.glob(pattern))

if not zip_files:
    print(f"[A2] 警告: 在 {download_dir} 找不到任何符合 115_NPA_TMA2_*.zip 的檔案")

for zip_path in zip_files:
    filename = os.path.basename(zip_path)

    # 從檔名擷取月份數字,例如 115_NPA_TMA2_01.zip -> 01, 115_NPA_TMA2_12.zip -> 12
    match = re.search(r"115_NPA_TMA2_(\d+)\.zip$", filename)
    if not match:
        print(f"[A2] 略過: 檔名不符合月份命名規則 -> {filename}")
        continue

    month_num = int(match.group(1))
    month_id = f"115_{month_num:02d}"

    # zip 內的 csv 檔名對應規則(依你原本的命名: NPA_TMA2_{x}.csv,不補零)
    csv_name_in_zip = f"NPA_TMA2_{month_num}.csv"

    with zipfile.ZipFile(zip_path, "r") as z:
        with z.open(csv_name_in_zip) as f:
            dfs = pd.read_csv(f, encoding="utf-8-sig")

    dfs["month"] = month_id
    dfs = dfs.dropna(subset=["發生年度"])
    dfs = dfs[~dfs.iloc[:, 0].astype(str).str.contains("資料提供|事故類", na=False)]

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tma2_data'"
    )
    if cur.fetchone() is not None:
        conn.execute("DELETE FROM tma2_data WHERE month = ?", (month_id,))
        conn.commit()

    dfs.to_sql("tma2_data", conn, if_exists="append", index=False)
    print(f"[A2] 完成: {month_id}(來源: {filename}),共 {dfs.shape[0]} 筆")

# %%

# ========== A1 資料(JSON,獨立表,總體資料不分月份) ==========
json_path = os.path.join(download_dir, "NPA_TMA1_JSON.json")  # 檔名請依實際調整

with open(json_path, "r", encoding="utf-8-sig") as f:
    raw_data = json.load(f)

records = raw_data["result"]["records"]
df_a1 = pd.DataFrame(records)
df_a1 = df_a1.dropna(subset=["發生年度"])

# A1 是總體資料,整份表直接覆蓋重建,不需要用 month 篩選刪除
cur = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='tma1_data'"
)
if cur.fetchone() is not None:
    conn.execute("DELETE FROM tma1_data")
    conn.commit()

df_a1.to_sql("tma1_data", conn, if_exists="append", index=False)
print(f"[A1] 完成(總體資料),共 {df_a1.shape[0]} 筆")

# 所有資料庫操作都做完了,最後才關閉連線
conn.close()