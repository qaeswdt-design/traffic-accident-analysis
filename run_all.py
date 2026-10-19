# -*- coding: utf-8 -*-
"""
一鍵重新產生「台灣交通事故分析」專案的所有圖表。

用法：
    python run_all.py            # 只重跑圖表（用現有 data.db，最常用）
    python run_all.py --refresh  # 先檢查官方資料有沒有更新，有更新才重新下載+匯入資料庫，再重跑圖表

執行完成後，所有圖表會輸出到 ./outputs/ 資料夾。
"""
import os
import sys
import subprocess
import argparse

# Windows 中文環境的終端機預設常是 cp950(Big5)，不含 ▶/✓/✗ 這類符號，
# 強制改成 UTF-8 輸出，避免執行到一半因為印字元就整個當掉。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- 資料更新（可選，預設跳過，因為原腳本有互動確認、且不一定每次都要重抓） ----
REFRESH_STEPS = [
    ("下載最新官方資料（比對更新時間，有更新才下載）", "當前資料下載更新.py"),
    ("將下載的 CSV/JSON 匯入 data.db", "資料塞入資料庫.py"),
]

# ---- 圖表產生（依專案簡報的章節順序排列） ----
CHART_STEPS = [
    ("01A 事故時間分布", "時間上的分析.py"),
    ("02  事故主要肇因 TOP5", "北北基桃交通事故主要肇因 TOP 5.py"),
    ("02B 地區間肇因比較", "橫條圖.py"),
    ("03  道路環境分析", "依時間區分.py"),
    ("04  外部環境分析（光線）", "依光照分析.py"),
    ("05  道路設施分析（號誌／車道劃分設施）", "road_facility_final.py"),
    ("06  當事者特徵分析（含01B車種×縣市比較）", "關於事故者的交叉分析.py"),
    ("07  事故結果分析（死亡率）", "死傷人數分析.py"),
]

# ---- 探索性/延伸功能，預設不執行（跑起來較久，且非簡報必要圖表） ----
OPTIONAL_STEPS = [
    ("事故密度熱點圖（靜態）", "事故點分布圖.py"),
    ("互動式地圖（輸出 HTML，對應「後續研究：地圖視覺化上線」）", "互動地圖.py"),
]


def run_step(label, script_name):
    script_path = os.path.join(BASE_DIR, script_name)
    print(f"\n{'='*60}\n▶ {label}\n  ({script_name})\n{'='*60}")
    if not os.path.exists(script_path):
        print(f"  ⚠ 找不到腳本，略過: {script_path}")
        return False
    # 子行程也強制用 UTF-8 輸出，避免各支分析腳本裡的中文 print() 在 Windows
    # 內建終端機（預設 cp950）跑到一半也炸掉。
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # 強制非互動繪圖後端：避免 plt.show() 在有些機器上跳出視窗、卡住等使用者手動關閉，
    # 圖表本來就是靠 savefig() 存檔，不需要跳窗顯示。
    env["MPLBACKEND"] = "Agg"
    result = subprocess.run([sys.executable, script_path], cwd=BASE_DIR, env=env)
    if result.returncode != 0:
        print(f"  ✗ 執行失敗（exit code {result.returncode}）")
        return False
    print(f"  ✓ 完成")
    return True


def main():
    parser = argparse.ArgumentParser(description="一鍵重新產生所有交通事故分析圖表")
    parser.add_argument("--refresh", action="store_true",
                         help="先檢查並下載最新官方資料、重新匯入資料庫，再產生圖表")
    parser.add_argument("--with-optional", action="store_true",
                         help="連同探索性功能（密度熱點圖、互動地圖）一起執行")
    args = parser.parse_args()

    steps = []
    if args.refresh:
        steps += REFRESH_STEPS
    steps += CHART_STEPS
    if args.with_optional:
        steps += OPTIONAL_STEPS

    print(f"共 {len(steps)} 個步驟，圖表將輸出到 {os.path.join(BASE_DIR, 'outputs')}\n")

    results = []
    for label, script_name in steps:
        ok = run_step(label, script_name)
        results.append((label, ok))

    print(f"\n{'='*60}\n執行結果總覽\n{'='*60}")
    for label, ok in results:
        print(f"  {'✓' if ok else '✗'}  {label}")

    failed = [label for label, ok in results if not ok]
    if failed:
        print(f"\n有 {len(failed)} 個步驟失敗，請檢查上方錯誤訊息。")
        sys.exit(1)
    else:
        print("\n全部完成！圖表都在 outputs/ 資料夾裡。")


if __name__ == "__main__":
    main()
