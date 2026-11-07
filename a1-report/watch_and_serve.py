# -*- coding: utf-8 -*-
"""在容器內執行:啟動網頁伺服器,並監看 data.db,資料一更新就自動重新產生報告。

流程:
  1. 啟動時先產生一次報告(AUTO_BUILD=0 則跳過,直接用上次的)。
  2. 每 POLL_SECONDS 秒檢查 data.db 的指紋(修改時間 + 大小)。
  3. 指紋變了,且連續 SETTLE_SECONDS 秒沒再變(等匯入寫完),就重新產生。
  4. 產生成功後寫出 public/version.json,開著的網頁會偵測到並提示重新整理。
產生失敗時保留舊報告,下一次檢查會再試。

自動下載氣象資料(AUTO_FETCH_WEATHER=1):容器啟動時,以及之後每 WEATHER_CHECK_HOURS 小時,
執行「氣象資料下載更新.py --yes --if-needed 20」;距離上次成功不到 20 小時會直接略過。
下載寫入 data.db 後,上面的監看機制會自動重新產生報告。下載失敗只記錄在日誌,不影響網頁。
"""
import functools
import http.server
import os
import subprocess
import sys
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(BASE, "public")
SOURCE = os.environ.get("TRAFFIC_SOURCE_DIR") or BASE  # data.db 所在資料夾(預設就是本資料夾)
DB = os.path.join(SOURCE, "data.db")
PORT = int(os.environ.get("PORT", "8003"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "15"))
SETTLE_SECONDS = int(os.environ.get("SETTLE_SECONDS", "20"))
AUTO_FETCH_WEATHER = os.environ.get("AUTO_FETCH_WEATHER", "0") == "1"
WEATHER_CHECK_HOURS = float(os.environ.get("WEATHER_CHECK_HOURS", "6"))


def log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def signature():
    try:
        st = os.stat(DB)
        return (int(st.st_mtime), st.st_size)
    except OSError:
        return None


def build():
    os.makedirs(PUBLIC, exist_ok=True)
    cmd = [sys.executable, os.path.join(BASE, "build_a1_report.py"),
           "-o", os.path.join(PUBLIC, "index.html"),
           "--version-json", os.path.join(PUBLIC, "version.json")]
    log("開始產生報告…")
    t0 = time.time()
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, encoding="utf-8")
    if r.returncode == 0:
        log(f"報告已更新({time.time() - t0:.0f} 秒)")
        return True
    log("報告產生失敗,保留舊版:\n" + (r.stderr or r.stdout)[-800:])
    return False


def fetch_weather_loop():
    """背景執行緒:定期下載氣象資料(增量,已是最新時腳本會自行略過)。"""
    script = os.path.join(BASE, "氣象資料下載更新.py")
    while True:
        log("檢查氣象資料是否需要更新…")
        try:
            r = subprocess.run([sys.executable, script, "--yes", "--if-needed", "20", "--db", DB], cwd=BASE,
                               capture_output=True, text=True, encoding="utf-8", timeout=3 * 3600)
            tail = (r.stdout or "").strip().splitlines()[-3:]
            log(("氣象資料:" if r.returncode == 0 else "氣象資料下載失敗:") + " ".join(tail or [(r.stderr or "")[-300:]]))
        except Exception as e:
            log(f"氣象資料下載例外:{e}")
        time.sleep(WEATHER_CHECK_HOURS * 3600)


def serve():
    os.makedirs(PUBLIC, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=PUBLIC)
    handler.log_message = lambda *a, **k: None  # 不要每個請求都印一行
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"網頁已啟動 http://localhost:{PORT}(容器內資料庫:{DB})")


def main():
    if signature() is None:
        log(f"找不到資料庫 {DB},只提供上次產生的報告。")
    serve()
    if AUTO_FETCH_WEATHER:
        threading.Thread(target=fetch_weather_loop, daemon=True).start()
    built_sig = None
    if os.environ.get("AUTO_BUILD", "1") == "1" and signature() is not None:
        if build():
            built_sig = signature()
    else:
        built_sig = signature()
    while True:
        time.sleep(POLL_SECONDS)
        sig = signature()
        if sig is None or sig == built_sig:
            continue
        log("偵測到 data.db 變動,等待寫入完成…")
        while True:
            time.sleep(SETTLE_SECONDS)
            now = signature()
            if now == sig:
                break
            sig = now
        if build():
            built_sig = sig


if __name__ == "__main__":
    main()
