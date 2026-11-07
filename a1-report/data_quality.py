# -*- coding: utf-8 -*-
"""資料品質檢查:對 A1(死亡)與 A2(受傷)的第 1 當事者逐項體檢,回傳可放進報告的結果。

原則:**不確定的紀錄一律保留並標註,不悄悄刪除。**
  - 狀態 ok   :沒有發現問題。
  - 狀態 flag :發現少量疑點,紀錄全部保留並標註,影響已評估(低於門檻)。
  - 狀態 warn :超過門檻,或屬於需要讀者留意的資料限制,請人工確認。
  真正「排除」的只有三類,全部列在 exclusions 並附筆數:
  (1) 非第 1 當事者的列(避免同一起事故重複計數)、
  (2) A1 超出 A2 最後一天之後的事故(讓死亡與受傷落在同一期間,仍留在資料庫)、
  (3) 地址不在報告的 20 個縣市內的事故。

用法:
    python data_quality.py          # 印出體檢表;有 warn 時結束碼為 0(只提醒,不中斷流程)
    資料塞入資料庫.py 匯入完成後會自動呼叫;build_a1_report.py 會把結果放進報告的「資料品質」章節。
"""
import re
import sys

import pandas as pd

import common

COUNTY_RE = r"^(.{2}[縣市])"
COUNTY_FIX = {"台北市": "臺北市", "台中市": "臺中市", "台南市": "臺南市", "台東縣": "臺東縣"}
REPORT_COUNTIES = ["新北市", "桃園市", "臺北市", "基隆市", "新竹市", "新竹縣", "苗栗縣", "臺中市", "彰化縣", "南投縣",
                   "雲林縣", "嘉義市", "嘉義縣", "臺南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣"]
SPECIAL_UNITS = ("國道公路警察局", "鐵路警察局", "航空警察局", "港務", "保安警察", "刑事警察局")
KEY = ["發生日期", "發生時間", "發生地點"]
FULL_KEY = KEY + ["當事者區分-類別-大類別名稱-車種", "當事者事故發生時年齡", "當事者屬-性-別名稱"]
UNKNOWN_FIELDS = [("天候名稱", "天候"), ("光線名稱", "光線(照明設施)"), ("道路型態大類別名稱", "道路型態"),
                  ("肇因研判子類別名稱-主要", "主要肇因")]

# 門檻(占第 1 當事者列數的比例)
TH_DUP, TH_COORD, TH_AGE, TH_UNKNOWN = 0.001, 0.01, 0.05, 0.05
TH_LAST_MONTH = 0.8   # 最後一個月筆數低於前三個月平均的這個比例,視為資料尚未完整


def _first(d):
    return d[pd.to_numeric(d["當事者順位"], errors="coerce") == 1].copy()


def _county(d):
    return d["發生地點"].astype(str).str.extract(COUNTY_RE)[0].replace(COUNTY_FIX)


def _profile(d):
    """單一資料集(第 1 當事者)的各項異常筆數。"""
    n = len(d)
    lon = pd.to_numeric(d["經度"], errors="coerce")
    lat = pd.to_numeric(d["緯度"], errors="coerce")
    age = pd.to_numeric(d["當事者事故發生時年齡"], errors="coerce")
    hour = pd.to_numeric(d["發生時間"], errors="coerce") // 10000
    unit = d["處理單位名稱警局層"].astype(str)
    county = _county(d).fillna("")
    norm_unit = unit.str.replace("台", "臺")
    mismatch = (~unit.str.contains("|".join(SPECIAL_UNITS))) & (county != "") & \
        pd.Series([c not in u for c, u in zip(county, norm_unit)], index=d.index)
    unknown = {}
    for col, label in UNKNOWN_FIELDS:
        v = d[col].astype(str).str.strip()
        unknown[label] = int(v.isin(["", "nan", "None", "不明"]).sum())
    return {
        "n": n,
        "coord": int(((lon < 118) | (lon > 123) | (lat < 21.5) | (lat > 26) | lon.isna() | lat.isna()).sum()),
        "age": int(((age <= 0) | (age > 100) | age.isna()).sum()),
        "time": int(((hour > 23) | hour.isna()).sum()),
        "dup_key": int(d.duplicated(KEY).sum()),
        "dup_full": int(d.duplicated(FULL_KEY).sum()),
        "unit_mismatch": int(mismatch.sum()),
        "unknown": unknown,
    }


def row_flags(d):
    """A1 每一列的標註(不刪除,只標記):回傳 {index: [標註…]},報告的事故明細會顯示。"""
    lon = pd.to_numeric(d["經度"], errors="coerce")
    lat = pd.to_numeric(d["緯度"], errors="coerce")
    age = pd.to_numeric(d["當事者事故發生時年齡"], errors="coerce")
    hour = pd.to_numeric(d["發生時間"], errors="coerce") // 10000
    dup = d.duplicated(KEY, keep=False)
    flags = {}
    for i in d.index:
        f = []
        if pd.isna(age[i]) or age[i] <= 0 or age[i] > 100:
            f.append("年齡不詳或不合理(已歸入「年齡不詳」)")
        if pd.isna(lon[i]) or pd.isna(lat[i]) or not (118 <= lon[i] <= 123 and 21.5 <= lat[i] <= 26):
            f.append("座標缺失或超出台灣範圍")
        if pd.isna(hour[i]) or hour[i] > 23:
            f.append("發生時間異常")
        if dup[i]:
            f.append("疑似重複(同日期、時間、地點)")
        if f:
            flags[i] = f
    return flags


def _fmt(n, total):
    return "0" if not n else f"{n:,}({n / total * 100:.2f}%)"


def _status(n, total, th):
    if not n:
        return "ok"
    return "warn" if n / total > th else "flag"


def run_checks(a1_all, a2_all):
    """a1_all / a2_all:資料庫讀出的完整資料表(A1 尚未截到 A2 期間)。"""
    cutoff = int(pd.to_numeric(a2_all["發生日期"], errors="coerce").max())
    f1_all, f2 = _first(a1_all), _first(a2_all)
    f1_date = pd.to_numeric(f1_all["發生日期"], errors="coerce")
    f1 = f1_all[f1_date <= cutoff]
    p1, p2 = _profile(f1), _profile(f2)
    n1, n2 = p1["n"], p2["n"]
    checks = []

    def add(cid, name, a1, a2, status, note):
        checks.append({"id": cid, "name": name, "a1": a1, "a2": a2, "status": status, "note": note})

    add("coord", "座標缺失或超出台灣範圍", _fmt(p1["coord"], n1), _fmt(p2["coord"], n2),
        max((_status(p1["coord"], n1, TH_COORD), _status(p2["coord"], n2, TH_COORD)), key=["ok", "flag", "warn"].index),
        "全部保留並標註。地圖只繪製 A1;A2 的座標問題不影響任何統計。")
    add("age", "年齡缺失、≤0 或 >100", _fmt(p1["age"], n1), _fmt(p2["age"], n2),
        max((_status(p1["age"], n1, TH_AGE), _status(p2["age"], n2, TH_AGE)), key=["ok", "flag", "warn"].index),
        "不刪除,歸入「年齡不詳」獨立一組,圖表上可見。")
    add("time", "發生時間異常(小時 >23 或缺)", _fmt(p1["time"], n1), _fmt(p2["time"], n2),
        "warn" if (p1["time"] or p2["time"]) else "ok", "若出現,需人工確認原始資料;不會被自動歸入任何時段。")
    add("dup", "疑似重複:同日期+時間+地點", _fmt(p1["dup_key"], n1), _fmt(p2["dup_key"], n2),
        max((_status(p1["dup_key"], n1, TH_DUP), _status(p2["dup_key"], n2, TH_DUP)), key=["ok", "flag", "warn"].index),
        "只標註、不刪除:同一地點同一分鐘發生兩起事故並非不可能。若全部剔除,影響上限即括號內比例。")
    add("dupfull", "疑似重複:主要欄位整列相同", _fmt(p1["dup_full"], n1), _fmt(p2["dup_full"], n2),
        "ok" if not (p1["dup_full"] or p2["dup_full"]) else "flag", "同日期、時間、地點、車種、年齡、性別全部相同,最可能是重複登載;仍保留。")

    k1 = set(map(tuple, f1[KEY].astype(str).values))
    k2 = set(map(tuple, f2[KEY].astype(str).values))
    overlap = len(k1 & k2)
    add("overlap", "同一起事故同時出現在 A1 與 A2", str(overlap), "(同左)", "warn" if overlap else "ok",
        "A1、A2 應互斥;若重疊,致死佔比的分母會重複計算。")
    add("unit", "地址縣市與處理單位不一致", _fmt(p1["unit_mismatch"], n1), _fmt(p2["unit_mismatch"], n2),
        "warn" if (p1["unit_mismatch"] or p2["unit_mismatch"]) else "ok", "縣市由地址文字判定,與警局單位交叉檢查。")
    mm = pd.to_numeric(a2_all["發生日期"], errors="coerce").astype("Int64").astype(str).str[4:6]
    mcol = a2_all["month"].astype(str).str[-2:] if "month" in a2_all.columns else mm
    bad_month = int((mm != mcol).sum())
    add("month", "A2「月份」欄與發生日期不一致", "—", str(bad_month), "warn" if bad_month else "ok", "匯入時的月份標記與資料內日期的一致性。")
    for col, label in UNKNOWN_FIELDS:
        a, b = p1["unknown"][label], p2["unknown"][label]
        st = "ok" if not (a or b) else ("warn" if max(a / n1, b / n2) > TH_UNKNOWN else "flag")
        add("unk_" + label, f"「{label}」空白或不明", _fmt(a, n1), _fmt(b, n2), st, "保留為「不明」類別,不推測、不補值。")

    # 期間完整度
    ym = pd.to_numeric(a2_all["發生日期"], errors="coerce").dropna().astype(int).astype(str).str[:6]
    monthly = ym.value_counts().sort_index()
    last_ratio = None
    if len(monthly) >= 4:
        last_ratio = monthly.iloc[-1] / monthly.iloc[-4:-1].mean()
    last_label = f"{monthly.index[-1][:4]}-{monthly.index[-1][4:]}" if len(monthly) else ""
    add("lag", "最後一個月的資料完整度", "—",
        f"{last_label}:約 {last_ratio * 100:.0f}% 的常態月份" if last_ratio is not None else "—",
        "warn" if (last_ratio is not None and last_ratio < TH_LAST_MONTH) else "ok",
        "官方資料有數週的登載延遲屬常態。報告以 A2 最後一天為終點,最近月份的件數不宜與整月比較。")
    add("denominator", "車輛登記數(分母)與資料期間同步", "—", "—", "flag",
        "分母採固定一個時點(115 年 7 月底),沒有隨月份更新;縣市間的相對比較較可靠,絕對數值僅供參考。")

    # 排除項目(透明列出)
    a1_party_rows = len(a1_all)
    a1_first = len(f1_all)
    late = int((f1_date > cutoff).sum())
    cty = _county(f1)
    out_county = f1[~cty.isin(REPORT_COUNTIES)]
    exclusions = [
        {"name": "非第 1 當事者的列", "count": int(a1_party_rows - a1_first),
         "note": f"A1 原檔每列是一位當事者(共 {a1_party_rows:,} 列),合併為 {a1_first:,} 起事故;只取順位 = 1,避免同一起事故被重複計數。A2 同理。"},
        {"name": "A1 超出 A2 最後一天之後的事故", "count": late,
         "note": f"發生在 {cutoff // 10000}-{cutoff // 100 % 100:02d}-{cutoff % 100:02d} 之後。仍留在資料庫,只是不納入統計,讓死亡與受傷落在同一期間。"},
        {"name": "地址不在報告 20 個縣市內的事故", "count": int(len(out_county)),
         "note": "例如連江縣、金門縣(報告的縣市邊界與車輛登記數不含離島)。"
                 + (f" 本次:{'、'.join(sorted(set(out_county['發生地點'].astype(str).str[:3])))}。" if len(out_county) else "")},
    ]
    counts = {s: sum(1 for c in checks if c["status"] == s) for s in ("ok", "flag", "warn")}
    return {"checks": checks, "exclusions": exclusions, "counts": counts,
            "firstParty": {"a1": n1, "a2": n2}, "cutoff": cutoff,
            "sensitivity": sensitivity(f1, f2, cutoff, monthly)}


# ---------- 敏感度分析:換一種清洗方式,主要結論會變嗎? ----------
# 「結論維持」的判準(與報告「重點發現」一致):
CONCLUSIONS = [("ped_ratio", 5.0, "行人的致死佔比至少是機車的 5 倍"),
               ("night_day", 1.5, "夜間的致死佔比至少是日間的 1.5 倍"),
               ("old_adult", 1.5, "65 歲以上的致死佔比至少是 18–64 歲的 1.5 倍")]


def _four_cities(d):
    return d[_county(d).isin(common.CITY_ORDER)].copy()


def _metrics(x1, x2):
    """北北基桃:各分組「每千件傷亡事故中的死亡事故」(A1 ÷ (A1+A2) × 1000)與其比值。"""
    def share(mask1, mask2):
        a, b = int(mask1.sum()), int(mask2.sum())
        return a / (a + b) * 1000 if a + b else None

    def prep(d):
        d = d.copy()
        hour = pd.to_numeric(d["發生時間"], errors="coerce") // 10000
        d["_per"] = hour.apply(common.classify_period)
        d["_age"] = pd.to_numeric(d["當事者事故發生時年齡"], errors="coerce")
        d["_veh"] = d["當事者區分-類別-大類別名稱-車種"]
        return d
    x1, x2 = prep(x1), prep(x2)
    moto = share(x1._veh == "機車", x2._veh == "機車")
    ped = share(x1._veh == "人", x2._veh == "人")
    night = share(x1._per == "夜間(20-05)", x2._per == "夜間(20-05)")
    day = share(x1._per == "日間(09-15)", x2._per == "日間(09-15)")
    old = share(x1._age >= 65, x2._age >= 65)
    adult = share(x1._age.between(18, 64), x2._age.between(18, 64))
    div = lambda a, b: (a / b) if a is not None and b else None
    m = {"a1": len(x1), "a2": len(x2), "moto": moto, "ped": ped,
         "ped_ratio": div(ped, moto), "night_day": div(night, day), "old_adult": div(old, adult)}
    m["holds"] = all(m[k] is not None and m[k] >= th for k, th, _ in CONCLUSIONS)
    return m


def sensitivity(f1, f2, cutoff, monthly):
    """f1/f2:第 1 當事者(A1 已截到 A2 期間)。回傳各清洗情境的重算結果;所有情境只改變「怎麼清洗」,資料來源相同。"""
    x1, x2 = _four_cities(f1), _four_cities(f2)
    scenarios = [("基準", "本報告採用的做法:A1 截到 A2 最後一天,疑點全部保留", x1, x2)]
    # 只用完整月份:最後一個月不完整時,截到上個月月底
    if len(monthly) >= 4 and monthly.iloc[-1] / monthly.iloc[-4:-1].mean() < TH_LAST_MONTH:
        prev = pd.Period(monthly.index[-2], "M").end_time
        cut2 = int(prev.strftime("%Y%m%d"))
        d1 = x1[pd.to_numeric(x1["發生日期"], errors="coerce") <= cut2]
        d2 = x2[pd.to_numeric(x2["發生日期"], errors="coerce") <= cut2]
        scenarios.append(("只用完整月份", f"截到 {cut2 // 10000}-{cut2 // 100 % 100:02d}-{cut2 % 100:02d},排除最近不完整的月份", d1, d2))
    scenarios.append(("剔除 A2 整列重複", "A2 中同日期、時間、地點、車種、年齡、性別全部相同的列,只留第一筆", x1, x2[~x2.duplicated(FULL_KEY)]))
    scenarios.append(("剔除 A2 同時間同地點", "最嚴格的重複判定:同日期、時間、地點的列全部剔除(連第一筆也不留)", x1, x2[~x2.duplicated(KEY, keep=False)]))

    def known_age(d):
        a = pd.to_numeric(d["當事者事故發生時年齡"], errors="coerce")
        return d[(a > 0) & (a <= 100)]
    scenarios.append(("剔除年齡不詳", "A1、A2 都剔除年齡缺失、≤0 或 >100 的列", known_age(x1), known_age(x2)))
    rows = []
    for name, desc, a, b in scenarios:
        m = _metrics(a, b)
        m.update({"name": name, "desc": desc})
        rows.append(m)
    ranges = {}
    for k in ("moto", "ped", "ped_ratio", "night_day", "old_adult"):
        vals = [r[k] for r in rows if r[k] is not None]
        ranges[k] = [min(vals), max(vals)] if vals else None
    return {"scenarios": rows, "ranges": ranges, "allHold": all(r["holds"] for r in rows),
            "conclusions": [{"key": k, "threshold": th, "text": t} for k, th, t in CONCLUSIONS]}


ICON = {"ok": "✓", "flag": "⚑", "warn": "⚠"}


def main():
    a1 = common.load_table("tma1_data")
    a2 = common.load_table("tma2_data")
    res = run_checks(a1, a2)
    print("\n===== 資料品質檢查(第 1 當事者;不確定的紀錄一律保留並標註)=====")
    for c in res["checks"]:
        print(f"{ICON[c['status']]} {c['name']}: A1 {c['a1']} | A2 {c['a2']}")
    print("-- 排除項目 --")
    for e in res["exclusions"]:
        print(f"  {e['name']}: {e['count']:,}")
    sens = res["sensitivity"]
    print("-- 敏感度分析(北北基桃,換清洗方式重算)--")
    for r in sens["scenarios"]:
        f = lambda v, fmt: "—" if v is None else format(v, fmt)
        print(f"  {r['name']:<14} A1={r['a1']:>4} A2={r['a2']:>6} 機車 {f(r['moto'], '.2f')}‰ 行人/機車 {f(r['ped_ratio'], '.1f')}× "
              f"夜/日 {f(r['night_day'], '.1f')}× 老/成人 {f(r['old_adult'], '.1f')}× 結論{'維持' if r['holds'] else '改變'}")
    k = res["counts"]
    print(f"結果:通過 {k['ok']}、保留並標註 {k['flag']}、需留意 {k['warn']}")
    if k["warn"]:
        print("⚠ 有「需留意」項目,請查看上方;資料仍已匯入,報告的「資料品質」章節會一併呈現。")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    main()
