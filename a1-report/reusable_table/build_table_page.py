# -*- coding: utf-8 -*-
"""把「一份資料 + 一份表格設定」做成單一 HTML 檔(離線可開,不需要任何套件)。

用法:
    python build_table_page.py --data rows.sample.json --config table.config.json --out example.html
    python build_table_page.py --data 我的資料.csv --config 我的設定.json --out 我的表格.html --title "我的明細表"

--data   JSON(物件陣列)或 CSV(第一列是欄位名稱,UTF-8)。CSV 裡整欄都是數字的欄位會自動轉成數字。
--config 表格設定(格式見 README.md);table.config.json 是 A1 事故明細表的設定,可複製後修改。
輸出的 HTML 內嵌了 data-table.css、data-table.js、資料與設定,可直接寄給別人或雙擊開啟。
只需要 Python 標準函式庫,不需要 pandas。
"""
import argparse
import csv
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_data(path):
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if rows:
            for key in rows[0].keys():
                vals = [r[key] for r in rows]
                try:
                    nums = [float(v) if v not in ("", None) else None for v in vals]
                except ValueError:
                    continue
                for r, n in zip(rows, nums):
                    r[key] = (int(n) if n is not None and n == int(n) else n)
        return rows
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit("JSON 資料必須是「物件陣列」,例如 [{...}, {...}]")
    return data


def main():
    ap = argparse.ArgumentParser(description="把資料與表格設定做成單一 HTML")
    ap.add_argument("--data", required=True)
    ap.add_argument("--config", default=os.path.join(HERE, "table.config.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "example.html"))
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    data = load_data(args.data)
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)
    with open(os.path.join(HERE, "data-table.css"), encoding="utf-8") as f:
        css = f.read()
    with open(os.path.join(HERE, "data-table.js"), encoding="utf-8") as f:
        js = f.read()
    title = args.title or config.get("title") or "資料表"
    j = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{margin:0;background:#f4f3ef;font-family:"Microsoft JhengHei","PingFang TC","Noto Sans TC",system-ui,sans-serif}}
@media (prefers-color-scheme: dark){{body{{background:#121211;color:#f0efec}}}}
.wrap{{max-width:1180px;margin:0 auto;padding:20px 16px}}
h1{{font-size:22px;margin:0 0 12px}}
{css}
</style>
</head>
<body>
<div class="wrap"><h1>{html.escape(title)}</h1><div id="table"></div></div>
<script>{js}</script>
<script>
DataTable.mount(document.getElementById("table"), {{ data: {j(data)}, config: {j(config)} }});
</script>
</body>
</html>
"""
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"已輸出 {args.out}({os.path.getsize(args.out) / 1024:,.0f} KB),共 {len(data)} 筆資料")


if __name__ == "__main__":
    main()
