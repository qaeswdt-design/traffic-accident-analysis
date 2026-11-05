# A1 死亡事故互動報告(第二版)

上一層的專案是以 A1+A2 做成圖表與簡報(第一版)。第二版放在這個子資料夾 `a1-report/`,以 **A1(死亡事故)** 為主角,做成一份**單一檔案、離線可開**的互動式 HTML 報告,用於面試現場討論。第一版的程式與簡報沒有動。

資料:警政署「道路交通事故」A1、A2(資料集 13139、57023)。A2 只用來當「每千件傷亡事故中的死亡事故」的分母。**資料期間、起數、結論文字都由資料即時算出**,不會因為資料更新而過期。

## 資料來源與自動更新

報告直接讀**專案根目錄(上一層)**的 `data.db`、`last_update.json` 與 `common.py`(根目錄是下載與匯入資料的地方),這裡不再放複本。

```
你在根目錄更新資料 ──→ data.db 變動 ──→ 容器偵測到(每 15 秒檢查)
                                       ──→ 等寫入穩定 20 秒後自動重新產生報告
                                       ──→ 開著的網頁出現「資料庫已更新 · 重新整理」
```

- 更新資料照舊在專案根目錄做:`python run_all.py --refresh`(或 `當前資料下載更新.py` + `資料塞入資料庫.py`)。
- 產生失敗(例如匯入到一半)會保留舊報告,下一輪再試;狀態看 `docker logs traffic-a1-v2`。
- 判斷「有沒有更新」是看 `data.db` 的修改時間與大小。
- 不用 Docker 時,`build_a1_report.py` 的找法是:`--source-dir` → 環境變數 `TRAFFIC_SOURCE_DIR` → 上一層(專案根目錄)。
- `data.db` 很大,不在 GitHub 上;clone 後要先在根目錄依根目錄 README 下載並匯入資料。

## 內容

- 時間、當事者、肇因、地點、環境與照明五個面向,加上事故明細表與「方法與限制」說明。
- 每張圖都能點選篩選,其他圖同步變化;可切換「北北基桃 / 全台」。
- 縣市與分組比較附 95% 信賴區間(比例用 Wilson、件數率用 Byar 近似的 Poisson)。

## 輸出

產生單一檔案 `A1_死亡事故互動報告.html`(離線可開、雙擊即可,已被 `.gitignore` 排除),或用 Docker 在 http://localhost:8003 開啟。

```bash
python build_a1_report.py        # 產生 A1_死亡事故互動報告.html
```

## 檔案

| 檔案 | 用途 |
|---|---|
| `build_a1_report.py` | 讀 `data.db`,篩選第 1 當事者、對齊 A1/A2 期間、分組、簡化地圖邊界,把資料以 JSON 嵌進樣板 |
| `a1_report_template.html` | 版面與互動(純 JavaScript + SVG,沒有外部相依) |
| `watch_and_serve.py` | 容器內執行:網頁伺服器 + 監看 `data.db` 自動重新產生 |
| (根目錄)`common.py` | 篩選規則、時段定義、車輛登記數;第二版直接 import 根目錄這份,不另放複本 |
| `geo_boundary/COUNTY_MOI_1140318.gml` | 內政部縣市界,地圖用 |
| `Dockerfile` `docker-compose.yml` `.dockerignore` | Docker 設定(做法同 `小說爬蟲整合`) |
| `啟動報告.bat` `停止報告.bat` | Windows 雙擊啟動/停止 |

## 用 Docker 執行

```bash
docker compose up -d --build     # 開在 http://localhost:8003,並開始監看 data.db
docker compose down              # 停止
```

- 連接埠 `8003`,只綁 `127.0.0.1`(`8001` 小說爬蟲、`8002` ytmusic_web 已被占用)。
- 映像檔只裝 pandas 與 numpy;程式由 compose 掛載進去,改程式不用重建。專案根目錄以**唯讀**掛載到 `/source`(`data.db`、`common.py` 都從那裡讀)。
- `docker-compose.yml` 的 `AUTO_BUILD: "0"` 可跳過啟動時的重新產生;`POLL_SECONDS`、`SETTLE_SECONDS` 調整偵測頻率。

## 限制

分到第三層篩選時常只剩個位數,請看信賴區間。分母是事故件數,不是里程;報告描述分布,不推論因果。車輛登記數是 `common.py` 內寫死的 115 年 7 月底數字,不會隨資料更新。
