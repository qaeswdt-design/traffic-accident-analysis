# 可重用的資料表(從「A1 死亡事故互動報告」匯出)

把報告裡「事故明細」表格的**紀錄方式**(資料長什麼樣子)與**條件**(欄位、排序、篩選、搜尋、展開內容、分頁、匯出)抽成獨立的一組檔案。之後想用同樣的表格處理別的資料,**只要換資料與設定檔,不必改程式,也不必再找人重跑**。

## 一分鐘用法

```bash
cd reusable_table
python build_table_page.py --data 我的資料.csv --config 我的設定.json --out 我的表格.html --title "我的明細表"
```

產生的 `我的表格.html` 是單一檔案,離線可開,可直接寄給別人。只需要 Python 標準函式庫(不用 pandas、不用網路)。

- `--data`:JSON(物件陣列)或 CSV(第一列是欄位名稱,UTF-8)。CSV 整欄都是數字的欄位會自動轉成數字。
- `--config`:表格設定。**從 `table.config.json` 複製一份再改欄位名稱最快。**

也可以不經過 Python,直接放進任何網頁:

```html
<link rel="stylesheet" href="data-table.css">
<div id="table"></div>
<script src="data-table.js"></script>
<script>
  DataTable.mount(document.getElementById("table"), { data: rows, config: config });
</script>
```

## 資料夾內容

| 檔案 | 用途 |
|---|---|
| `data-table.js` | 表格元件(無相依,約 250 行) |
| `data-table.css` | 樣式;顏色是 CSS 變數(`--dt-accent` 等),跟隨系統深色模式 |
| `table.config.json` | **事故明細表的設定**:欄位、排序、篩選、展開內容、匯出,也就是報告裡那張表的「條件」 |
| `rows.sample.json` | **事故明細表的紀錄方式範例**:報告匯出的 263 筆(北北基桃)原始紀錄,欄位見下 |
| `build_table_page.py` | 把「資料 + 設定」做成單一 HTML |
| `example.html` | 用上面兩份產生的成品(與報告裡的表格行為一致) |
| `examples/成績.*` | 完全不同的資料(成績表)只靠一份設定做出同樣功能,示範怎麼套用 |

## 表格有哪些功能

多關鍵字搜尋(空白分隔、需全部符合)、點表頭排序(再點切換升降冪)、下拉與勾選篩選(選項與件數由資料自動算出)、自選顯示欄位、**固定高度翻頁**(每頁高度一致,分頁列位置不跳動)、點任一列展開完整資料、⚑ 資料標註、匯出 CSV(目前篩選與排序的結果)。

## 紀錄方式:事故明細的欄位(rows.sample.json)

一筆紀錄 = 一起死亡事故(A1,第 1 當事者),主要欄位:

| 欄位 | 意思 | 欄位 | 意思 |
|---|---|---|---|
| `d` / `t` / `dow` | 日期 / 時間(時:分)/ 星期 | `cs` / `cc` | 主要肇因 / 肇因類別 |
| `m` / `h` | 月份 / 小時 | `at` / `as` | 事故大類 / 事故型態 |
| `per` | 時段(早峰、日間、晚峰、夜間) | `rc` / `sh` / `sg` / `sp` | 道路類別 / 道路型態 / 號誌 / 速限 |
| `c` | 縣市 | `w` / `l` | 天候 / 照明 |
| `p` | 地點(路口以 ` / ` 連接兩條路) | `dead` / `hurt` | 死亡 / 受傷人數 |
| `x` / `y` | 經度 / 緯度 | `hr` | 是否肇事逃逸(`是`/`否`) |
| `veh` / `vs` | 第 1 當事者車種 / 車種細項 | `age` / `ag` / `sex` | 年齡(可為 null)/ 年齡組 / 性別 |
| `fl` | 資料標註(陣列,空陣列代表沒有疑點) | | |

不確定的紀錄一律保留並標註(`fl`),不刪除。

## 設定檔(config)欄位說明

| 欄位 | 說明 |
|---|---|
| `title` / `locale` | 標題 / 排序用的語系(預設 `zh-Hant`) |
| `height` | 表格區固定高度(像素);手機會自動降為 480 |
| `pageSize` / `pageSizes` | 預設每頁筆數 / 可選的每頁筆數 |
| `defaultSort` | `{"key": "d", "dir": "desc"}` |
| `columns` | 欄位清單,見下表 |
| `computed` | 衍生欄位,見下 |
| `search` | `fields`:搜尋範圍欄位;`extraTemplates`:額外加進搜尋的範本文字 |
| `filters` | 篩選清單,見下表 |
| `detail` | 展開後的內容:`{"label", "template", "hideIfEmpty"}` |
| `flagField` / `flagColumn` | 資料標註所在欄位 / 在哪一欄後面顯示 ⚑ |
| `csv` | `{"filename", "columns": [["欄位", "標題"], ...]}`;省略 `columns` 就匯出目前的表格欄位 |
| `labels` | 介面文字(按鈕、提示)可整組換成別的語言 |

**欄位 `columns[]`**:`key`(欄位名)、`label`(標題)、`template`(顯示格式,見下)、`type`(`"number"` 會靠右並用數值排序)、`sortBy`(排序用的欄位陣列,例如日期再用時間)、`default`(`false` = 預設不顯示,可在「欄位」選單勾選)。

**範本 `template`**:用 `{欄位}` 代入資料,`{欄位|沒有值時顯示}` 可指定預設文字,例如 `{age|不詳}`、`{d}(週{dow})`。

**篩選 `filters[]`**:
- 下拉:`{"type":"select","key":"c","label":"縣市","field":"c"}`;`order` 可寫 `"asc"`、或一個陣列(固定順序),預設依件數多到少。
- 勾選:`{"type":"check","key":"dead2","label":"死亡 2 人以上","field":"dead","op":">=","value":2}`;`op` 可用 `>= > <= < == != nonEmpty`。

**衍生欄位 `computed`**(三種寫法):
- 分組:`{"from":"age","rules":[{"isNull":true,"label":"年齡不詳"},{"lt":18,"label":"未滿18歲"},{"label":"其他"}]}`(由上往下,第一個全部成立的規則生效;條件可用 `isNull lt lte gt gte eq`)
- 切字串:`{"from":"p","split":" / ","index":0}`
- 組合:`{"template":"{veh}({vs})","whenDifferent":["veh","vs"],"otherwise":"{veh}"}`

## 想用在別的資料,最少要做的事

1. 準備資料:CSV 或 JSON 物件陣列。
2. 複製 `table.config.json`(或 `examples/成績.config.json`,後者較短),把 `columns`、`filters`、`detail`、`search.fields` 裡的欄位名稱改成你資料的欄位名稱。
3. 執行 `build_table_page.py`,用瀏覽器開輸出的 HTML 檢查。

## 授權與限制

- 這組檔案是自己寫的,沒有使用外部套件或字型,可自由複製使用。
- 表格一次把全部資料載入記憶體並在瀏覽器內排序/篩選,適合數萬筆以內;更大量的資料請改用伺服器端分頁。
