# -*- coding: utf-8 -*-
"""下載北北基桃周邊的主要道路(國道、快速道路/省道、主要幹道),簡化後存成 geo_boundary/roads_major.json,
讓報告的事故地圖可以離線顯示道路。只需執行一次(道路幾乎不變);報告產生時會自動讀取。道路等級:國道、快速道路/省道、主要幹道、次要幹道、一般道路。

資料來源:OpenStreetMap(© OpenStreetMap contributors,ODbL 授權),經 Overpass API 取得。
用法:
    python build_roads.py                      # 下載並產生(約 8 MB 下載,幾十秒)
    python build_roads.py --input a.json b.json   # 改用已下載好的 Overpass JSON(可多個),不再連網
輸出的座標與 build_a1_report.py 的地圖投影一致(x = 經度 × cos(23.7°) × 1000、y = −緯度 × 1000),
以 0.1 單位(約 10 公尺)為精度,並用相對座標壓縮。
"""
import argparse
import json
import math
import os
import time
import urllib.parse
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "geo_boundary", "roads_major.json")
COS_LAT = 0.916
BBOX = (24.55, 120.85, 25.40, 122.15)          # 南, 西, 北, 東:涵蓋北北基桃及周邊
CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary"]   # 國道;快速道路/省道;主要幹道;次要幹道;一般道路
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "traffic-a1-report/1.0 (personal analysis project)"
EPS_DEG = 0.00018                              # 簡化容許誤差,約 20 公尺


def fetch_class(cls, tries=4):
    """一次只抓一種道路等級(單次查詢較小、較不易逾時);伺服器忙碌時指數退避重試。"""
    q = (f'[out:json][timeout:240];(way["highway"="{cls}"]'
         f'({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}););out geom tags;')
    for i in range(tries):
        req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": UA})
        try:
            print(f"下載 {cls} …")
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:                       # 502/504(伺服器忙碌)、逾時等
            wait = 20 * (2 ** i)
            print(f"  失敗({e}),{wait} 秒後重試")
            time.sleep(wait)
    raise SystemExit(f"下載 {cls} 失敗,請稍後再試")


def fetch():
    raw = {"elements": [], "osm3s": {}}
    for cls in CLASSES:
        part = fetch_class(cls)
        raw["elements"] += part.get("elements", [])
        raw["osm3s"] = part.get("osm3s", raw["osm3s"])
        time.sleep(3)
    return raw


def dp(points, eps):
    """Douglas-Peucker 簡化(迭代版)。"""
    n = len(points)
    if n <= 2:
        return points
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        seg, a, b = points[i + 1:j], points[i], points[j]
        ab = b - a
        norm = math.hypot(ab[0], ab[1])
        dist = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1]) if norm == 0 else \
            np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / norm
        k = int(np.argmax(dist))
        if dist[k] > eps:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]
    return points[keep]


def fmt(v):
    s = f"{v / 10:.1f}"
    return s[:-2] if s.endswith(".0") else s


def way_path(coords):
    """經緯度 → 0.1 單位整數座標 → 'M x y l dx dy …'(相對座標,用整數差避免誤差累積)。"""
    xy = np.column_stack([np.round(coords[:, 1] * COS_LAT * 10000), np.round(-coords[:, 0] * 10000)]).astype(np.int64)
    keep = np.ones(len(xy), bool)
    keep[1:] = np.any(xy[1:] != xy[:-1], axis=1)
    xy = xy[keep]
    if len(xy) < 2:
        return ""
    out = [f"M{fmt(xy[0][0])} {fmt(xy[0][1])}l"]
    out += [f"{fmt(dx)} {fmt(dy)}" for dx, dy in np.diff(xy, axis=0)]
    return out[0] + " ".join(out[1:])


def build(raw):
    paths = {c: [] for c in CLASSES}
    n_way = n_pts_raw = n_pts = 0
    for el in raw.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        cls = el.get("tags", {}).get("highway")
        if cls not in paths:
            continue
        pts = np.array([[g["lat"], g["lon"]] for g in el["geometry"]], dtype=float)
        n_way += 1
        n_pts_raw += len(pts)
        pts = dp(pts, EPS_DEG)
        n_pts += len(pts)
        d = way_path(pts)
        if d:
            paths[cls].append(d)
    print(f"{n_way} 段道路,節點 {n_pts_raw:,} → {n_pts:,}(簡化後)")
    return {c: "".join(v) for c, v in paths.items()}


def main():
    ap = argparse.ArgumentParser(description="產生報告用的主要道路資料")
    ap.add_argument("--input", nargs="+", help="已下載的 Overpass JSON(可多個;省略則連網下載)")
    args = ap.parse_args()
    if args.input:
        raw = {"elements": [], "osm3s": {}}
        for path in args.input:
            with open(path, encoding="utf-8") as f:
                part = json.load(f)
            raw["elements"] += part.get("elements", [])
            raw["osm3s"] = part.get("osm3s", raw["osm3s"])
    else:
        raw = fetch()
    out = {
        "source": "© OpenStreetMap contributors (ODbL)",
        "bbox": BBOX,
        "classes": CLASSES,
        "osmTimestamp": raw.get("osm3s", {}).get("timestamp_osm_base", ""),
        "builtAt": time.strftime("%Y-%m-%d"),
        "paths": build(raw),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"已輸出 {OUT}({os.path.getsize(OUT) / 1024:,.0f} KB)")


if __name__ == "__main__":
    main()
