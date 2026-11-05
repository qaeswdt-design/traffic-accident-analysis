# -*- coding: utf-8 -*-
"""在容器內執行:啟動網頁伺服器,並監看 data.db,資料一更新就自動重新產生報告。

流程:
  1. 啟動時先產生一次報告(AUTO_BUILD=0 則跳過,直接用上次的)。
  2. 每 POLL_SECONDS 秒檢查 data.db 的指紋(修改時間 + 大小)。
  3. 指紋變了,且連續 SETTLE_SECONDS 秒沒再變(等匯入寫完),就重新產生。
  4. 產生成功後寫出 public/version.json,開著的網頁會偵測到並提示重新整理。
產生失敗時保留舊報告,下一次檢查會再試。
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
SOURCE = os.environ.get("TRAFFIC_SOURCE_DIR") or os.path.dirname(BASE)  # 專案根目錄(data.db 所在)
DB = os.path.join(SOURCE, "data.db")
PORT = int(os.environ.get("PORT", "8003"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "15"))
SETTLE_SECONDS = int(os.environ.get("SETTLE_SECONDS", "20"))


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
