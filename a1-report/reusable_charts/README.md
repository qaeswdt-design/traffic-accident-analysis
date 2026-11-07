# 可重用的圖表版型(從「A1 死亡事故互動報告」抽出)

## 報告用的是哪一種寫法?

**全部是手寫的原生 JavaScript,畫成 HTML 與 SVG。沒有用任何圖表套件**(沒有 Chart.js、ECharts、D3、Plotly,報告裡也沒有任何 CDN 引用)。

| | 手寫 HTML + SVG(目前的做法) | 圖表套件(Chart.js / ECharts / D3…) |
|---|---|---|
| 離線、單一檔案 | ✅ 不需要網路,可直接寄給別人或雙擊開啟 | 需把整個套件內嵌,檔案變大 |
| 特殊圖形 | ✅ 信賴區間森林圖、縮放地圖、固定高度翻頁都能完全照想法做 | 常需要外掛或繞路 |
| 檔案大小 | ✅ 這組圖表約 25 KB | 數百 KB 起 |
| 常見圖形 | 要自己寫(折線、圓餅、散佈圖這裡沒有) | ✅ 內建很多 |
| 動畫、大量資料(萬筆以上) | 需要自己處理 | ✅ 較成熟 |

**建議**:要離線單檔、版型很特定時,沿用這組版型;要快速做折線、圓餅、散佈圖或資料量很大時,改用套件(例如 ECharts)。

## 內容

| 檔案 | 用途 |
|---|---|
| `charts.js` | 六種圖表版型 + 信賴區間工具 + 提示框,無相依 |
| `charts.css` | 樣式與顏色(CSS 變數,跟隨深色模式),放在 `class="ch-root"` 的容器內 |
| `demo.html` | 六張圖的完整示範(隨機示範資料),直接雙擊開啟;**改裡面的資料與選項就是最快的套用方式** |

使用方式:

```html
<link rel="stylesheet" href="charts.css">
<body class="ch-root">
  <div id="box"></div>
  <script src="charts.js"></script>
  <script>
    Charts.barList(document.getElementById("box"), [{ key: "a", label: "甲", value: 12 }, ...], { onClick: it => ... });
  </script>
</body>
```

圖表不管理狀態:**資料與選取狀態由你的程式保存,有變動就重新呼叫一次函式**(報告也是這樣做的,見 `demo.html` 的 `drawBar()` 等)。

## 六種版型

| 版型 | 適合畫什麼 | 報告裡對應的圖 |
|---|---|---|
| `Charts.barList` | 排名、占比、類別件數;可點選篩選、可分頁 | 肇因、車種、縣市、事故型態… |
| `Charts.columns` | 依序的類別(時間、月份),可堆疊、可標示區段 | 24 小時分布(依年齡層/車種堆疊) |
| `Charts.forest` | 估計值 + 信賴區間,看差異是否只是隨機波動 | 每千件傷亡事故中的死亡事故、每十萬輛車死亡事故 |
| `Charts.stackedBars` | 兩個類別交叉(橫向堆疊) | 年齡 × 車種 |
| `Charts.heatmap` | 兩個類別交叉的件數與占比 | 時段 × 照明設施 |
| `Charts.geoScatter` | 點位地圖,可縮放、拖曳、疊道路與界線 | 事故地點 |

### 資料格式與選項

**`barList(host, items, opts)`**
- `items`:`[{ key, label, value, text?, selected?, tip? }]`(`text` = 右側顯示文字,`tip` = 提示框 HTML)
- `opts`:`onClick(item)`、`pageSize`(有值就分頁,每頁固定列數,不足補空列,翻頁時高度不跳動)、`max`

**`columns(host, opts)`**
- `categories: [{key,label}]`、`series: [{key,label,color}]`、`values: {類別key: {系列key: 數量}}`
- `bands: [[起始索引, 結束索引(不含), "標籤"], ...]` 畫背景區段;`selected: Set`、`onClick(類別key)`、`tipText(key,row)`、`height`

**`forest(host, items, opts)`**
- `items`:`[{ label, v, lo, hi, sub?, sel?, hollow?, tip?, onClick? }]`(`hollow` = 樣本太少,畫空心圓)
- `opts`:`base`(整體值,畫虛線)、`unit`、`max`
- 容器窄於 620px 自動改成每列兩行,手機不用左右捲動
- 區間用 `Charts.wilson(k, n)`(比例)或 `Charts.byar(k)`(件數)算

**`stackedBars(host, rows, series, opts)`**
- `rows: [{key,label,values:{系列key:數量}}]`、`series: [{key,label,color}]`
- `opts`:`onClick`、`selected: Set`、`unit`、`legendHost`(要放圖例的元素)

**`heatmap(host, opts)`**
- `rows`、`cols: [{key,label}]`、`matrix: [[數量...]...]`、`rgb`(主色,預設藍)、`selected: {row,col}`、`onCell(rowKey,colKey)`

**`geoScatter(host, opts)`**
- `outlines: [{ d, label?, labelAt?, focus? }]`:底圖(縣市界),`d` 是 SVG path,座標為**自己投影好的平面座標**(報告用 x = 經度 × cos(23.7°) × 1000、y = −緯度 × 1000,見 `build_a1_report.py` 與 `build_roads.py`)
- `layers: [{ d, className }]`:道路等線圖層;`className` 搭配 `charts.css` 的 `.ch-road.major / .minor / .detail`(`.detail` 需放大 2 倍才顯示,可依需求改成一直顯示)
- `points: [{ x, y, r?, color, tip?, onClick? }]`、`ghosts`(被篩掉的點)、`maxZoom`、`view`(保留縮放位置)
- 互動:滾輪/雙指縮放、拖曳、連點兩下放大、`+ − ⟲` 按鈕;**放大時點與文字維持固定螢幕大小**;拖曳不會誤觸「點選」

## 版型背後的設計規則(沿用到新圖時請維持)

1. **一個軸、不用雙 Y 軸**;兩種不同尺度的量,拆成兩張圖。
2. **細的標記**:長條細、點半徑 6、線寬 2;段與段之間留 1.5–2px 底色縫。
3. **顏色固定順序**(`--ch-s1`、`--ch-s2`、`--ch-s3`、`--ch-other`),不輪迴;超過 3–4 類就改成「單一色 + 分組」或折成「其他」。顏色跟著「類別」走,篩選時不重新分配。
4. **文字用文字色**,不用系列色;顏色旁一定有圖例或直接標註,不單靠顏色區分。
5. **每張圖都有提示框**(`tip`),滑鼠移入或手機點一下顯示。
6. **窄版要能用**:依「容器寬度」(不是視窗寬度)切換版面,避免並排小卡片裡的圖被截斷。
7. **統計誠實**:樣本少的點畫空心圓;估計值附信賴區間;分母不是暴露量時要在旁邊註明。

## 在別的專案裡套用

1. 複製 `charts.js`、`charts.css` 到專案。
2. 打開 `demo.html`,找到最接近你需求的那張圖,複製它的程式段,把資料換成你的。
3. 資料要先整理成上面的格式(每種圖都是簡單的陣列或物件,不需要特別的資料結構)。
4. 地圖:自己準備邊界與道路的 SVG path(座標用同一套投影)。台灣縣市界可參考 `build_a1_report.py` 的 `build_geo()`,道路可用 `build_roads.py` 從 OpenStreetMap 下載(使用時須保留 © OpenStreetMap contributors 的出處標示)。

## 授權與限制

- 這組檔案是自己寫的,沒有使用外部套件或字型,可自由複製使用。
- 一次把全部資料載入瀏覽器處理,適合數萬筆以內;地圖的點超過數萬個會變慢。
- 這裡只有上述六種圖。折線、圓餅、散佈圖沒有,需要時請另寫或改用圖表套件。
