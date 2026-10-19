'''
自動判別資料是否更新過:以「詮釋資料更新時間」時間戳記處理
(不需要 Playwright/瀏覽器版本 —— 改用 data.gov.tw 官方 M2M CSV 匯出 API)

原理說明:
data.gov.tw 官方提供整批資料集詮釋資料的 CSV 匯出端點,
裡面已經包含「資料集識別碼」「詮釋資料更新時間」「資料下載網址」等欄位,
不需要用瀏覽器引擎打開網頁畫面去解析 HTML,單純用 requests 下載 CSV 即可。
這是官方設計給程式化存取(M2M)用的端點,比爬網頁畫面更穩定、也更符合網站規範。
'''
import re
import os
import io
import csv
import json
import time
import random
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# data.gov.tw 官方資料集詮釋資料匯出 API(CSV 格式)
EXPORT_API_URL = "https://data.gov.tw/api/v2/rest/dataset/export?format=csv"

# 要追蹤的資料集識別碼(對應原本網址 https://data.gov.tw/dataset/13139 裡的數字)
TARGET_DATASET_IDS = ["13139", "57023"]

OUTPUT_DIR = "downloads"
TIMESTAMP_RECORD_FILE = "last_update.json"


def load_last_update_records():
    """讀取上次記錄的更新時間,檔案不存在就回傳空字典"""
    if os.path.exists(TIMESTAMP_RECORD_FILE):
        with open(TIMESTAMP_RECORD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_last_update_records(records):
    """把最新的更新時間寫回記錄檔"""
    with open(TIMESTAMP_RECORD_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def fetch_dataset_export():
    """下載官方整批資料集匯出 CSV,回傳 {資料集識別碼: row_dict} 的字典"""
    print("正在下載 data.gov.tw 官方資料集匯出清單...")
    resp = requests.get(
        EXPORT_API_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=(10, 60),
        verify=False,
    )
    resp.raise_for_status()

    # CSV 內容通常是 UTF-8 with BOM,用 utf-8-sig 處理避免第一個欄位名稱多出 \ufeff
    text = resp.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    result = {}
    for row in reader:
        dataset_id = (row.get("資料集識別碼") or "").strip()
        if dataset_id:
            result[dataset_id] = row

    print(f"  共取得 {len(result)} 筆資料集資訊")
    return result


def get_dataset_info(all_rows, dataset_id):
    """從整批資料裡取出單一資料集的更新時間 + 下載連結清單"""
    row = all_rows.get(dataset_id)
    if row is None:
        return None, []

    update_time = (row.get("詮釋資料更新時間") or "").strip() or None

    # 「資料下載網址」欄位若有多個下載連結,是用分號 ; 分隔
    raw_links = (row.get("資料下載網址") or "").strip()
    links = [u.strip() for u in raw_links.split(";") if u.strip()]

    return update_time, links


def download_all(links):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}

    for url in links:
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=(10, 20), verify=False)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  下載失敗: {url} ({e})")
            continue

        cd = resp.headers.get("content-disposition", "")
        match = re.search(r'filename="?([^"]+)"?', cd)
        if match:
            filename = match.group(1)
        else:
            filename = url.split("/")[-1] or "download.dat"

        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"下載完成: {filename}")
        time.sleep(random.randint(6, 10))


def process_dataset(dataset_id, all_rows, records):
    """處理單一資料集:抓時間+連結 → 跟記錄比對 → 有更新才下載"""
    print(f"檢查資料集: {dataset_id} (https://data.gov.tw/dataset/{dataset_id})")
    update_time, links = get_dataset_info(all_rows, dataset_id)
    print(f"  目前的更新時間: {update_time}")

    last_time = records.get(dataset_id)
    print(f"  上次記錄的更新時間: {last_time}")

    if update_time is None:
        print("  警告: 在匯出清單裡找不到這個資料集識別碼,請確認 ID 是否正確")
    elif update_time != last_time:
        print("  偵測到更新,開始下載...")
        x=input("如需更新請按 1")
        if x =='1':
            download_all(links)
            records[dataset_id] = update_time
        
    else:
        print("  尚無更新,跳過下載")

    print()


def main():
    records = load_last_update_records()
    all_rows = fetch_dataset_export()

    for dataset_id in TARGET_DATASET_IDS:
        process_dataset(dataset_id, all_rows, records)

    save_last_update_records(records)


if __name__ == "__main__":
    main()





 
