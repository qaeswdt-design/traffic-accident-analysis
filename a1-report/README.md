# A1 死亡事故互動報告(第二版)

這個資料夾**自給自足**:報告程式、共用規則(`common.py`)、資料下載與匯入腳本、資料庫(`data.db`)都在這裡,不依賴上一層的第一版專案,可以單獨複製到別處使用。以 **A1(死亡事故)** 為主角,產生一份**單一檔案、離線可開**的互動式 HTML 報告,用於面試現場討論。

資料:警政署「道路交通事故」A1、A2(資料集 13139、57023)。A2 只用來當「每千件傷亡事故中的死亡事故」的分母。**資料期間、起數、結論文字都由資料即時算出**,不會因為資料更新而過期。

## 資料流程與自動更新

```
當前資料下載更新.py ──→ downloads/ ──→ 資料塞入資料庫.py ──→ data.db
                                                               │
              build_a1_report.py ←── common.py(篩選規則)←──────┘
                      │
                      └─→ A1_死亡事故互動報告.html(或容器內的 public/index.html)
```

更新資料(都在本資料夾執行):

```bash
pip install -r requirements.txt
python 當前資料下載更新.py      # 比對官方更新時間,有更新才下載(--yes 不詢問)
python 資料塞入資料庫.py        # 匯入 data.db(同月份會先刪再寫,可重複執行)
```

用 Docker 開著報告時,`data.db` 一變動,容器會自動重新產生:

```
data.db 變動 ──→ 容器偵測到(每 15 秒檢查)──→ 等寫入穩定 20 秒後自動重新產生報告
             ──→ 開著的網頁出現「資料庫已更新 · 重新整理」
```

- 產生失敗(例如匯入到一半)會保留舊報告,下一輪再試;狀態看 `docker logs traffic-a1-v2`。
- 判斷「有沒有更新」是看 `data.db` 的修改時間與大小。
- `build_a1_report.py` 找 `data.db` 的順序:`--source-dir` → 環境變數 `TRAFFIC_SOURCE_DIR` → 本資料夾。
- `data.db`、`downloads/`、`last_update.json` 體積大或可重新下載,不進 git;clone 後先執行上面兩支腳本取得資料。

## 內容

- 時間、當事者、肇因、地點、環境與照明五個面向,加上事故明細表與「方法與限制」說明。
- 每張圖都能點選篩選,其他圖同步變化;可切換「北北基桃 / 全台」。
- 縣市與分組比較附 95% 信賴區間(比例用 Wilson、件數率用 Byar 近似的 Poisson)。

## 輸出

產生單一檔案 `A1_死亡事故互動報告.html`(離線可開、雙擊即可),或用 Docker 在 http://localhost:8003 開啟。

倉庫裡附了一份已產生好的成品,方便不用安裝任何東西就能直接開來看;它是產生當下資料的**快照**(資料期間顯示在頁首),之後資料更新、重新執行腳本就會覆蓋它。

```bash
python build_a1_report.py        # 產生 A1_死亡事故互動報告.html
```

## 檔案

| 檔案 | 用途 |
|---|---|
| `build_a1_report.py` | 讀 `data.db`,篩選第 1 當事者、對齊 A1/A2 期間、分組、簡化地圖邊界,把資料以 JSON 嵌進樣板 |
| `a1_report_template.html` | 版面與互動(純 JavaScript + SVG,沒有外部相依) |
| `watch_and_serve.py` | 容器內執行:網頁伺服器 + 監看 `data.db` 自動重新產生 |
| `common.py` | 篩選規則、時段定義、車輛登記數、下載用 Session(從第一版複製) |
| `當前資料下載更新.py` | 從 data.gov.tw 下載 A1/A2,比對更新時間(從第一版複製) |
| `資料塞入資料庫.py` | 把下載檔匯入 SQLite `data.db`(從第一版複製) |
| `data.db` `downloads/` `last_update.json` | 資料庫、原始下載檔、更新時間紀錄(不進 git) |
| `geo_boundary/COUNTY_MOI_1140318.gml` | 內政部縣市界,地圖用 |
| `Dockerfile` `docker-compose.yml` `.dockerignore` | Docker 設定(做法同 `小說爬蟲整合`) |
| `啟動報告.bat` `停止報告.bat` | Windows 雙擊啟動/停止 |

## 用 Docker 執行

```bash
docker compose up -d --build     # 開在 http://localhost:8003,並開始監看 data.db
docker compose down              # 停止
```

- 連接埠 `8003`,只綁 `127.0.0.1`(`8001` 小說爬蟲、`8002` ytmusic_web 已被占用)。
- 映像檔只裝套件;整個資料夾(程式與 `data.db`)由 compose 掛載進容器,改程式不用重建。
- `docker-compose.yml` 的 `AUTO_BUILD: "0"` 可跳過啟動時的重新產生;`POLL_SECONDS`、`SETTLE_SECONDS` 調整偵測頻率。

## 限制

分到第三層篩選時常只剩個位數,請看信賴區間。分母是事故件數,不是里程;報告描述分布,不推論因果。車輛登記數是 `common.py` 內寫死的 115 年 7 月底數字(第一版與第二版各有一份,要更新時兩邊都要改),不會隨資料更新。
