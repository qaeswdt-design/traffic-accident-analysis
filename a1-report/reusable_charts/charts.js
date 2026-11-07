/*
 * charts.js — 從「A1 死亡事故互動報告」抽出來的圖表版型(無相依,不需要 Chart.js / D3 / ECharts)
 *
 * 全部用原生 JavaScript 畫成 HTML 與 SVG,離線可用,可直接放進單一 HTML 檔。
 * 六種版型(括號內是報告裡對應的函式與用途):
 *   Charts.barList     橫條清單,可點選、可分頁       (barList:肇因、車種、縣市…)
 *   Charts.columns     直條圖,可堆疊、可標示區段       (hourChart:24 小時分布,依年齡層/車種堆疊)
 *   Charts.forest      點 + 信賴區間(森林圖)         (forest/riskChart:每千件傷亡事故中的死亡事故)
 *   Charts.stackedBars 橫向堆疊條                    (stackChart:年齡 × 車種)
 *   Charts.heatmap     熱度表(格內顯示件數與占比)     (matrix:時段 × 照明)
 *   Charts.geoScatter  可縮放、拖曳的點位地圖         (mapChart:事故地點 + 道路 + 縣市界)
 * 另有統計工具 Charts.wilson / Charts.byar(信賴區間),與 Charts.tip(提示框)。
 * 每種圖的資料格式與選項見同資料夾 README.md;範例見 demo.html。
 *
 * 安全:tip 提示框、label 等文字若來自使用者資料,請先用 Charts.esc() 跳脫再放進 HTML 字串。
 */
(function (global) {
  "use strict";

  /* ---------- 基本工具 ---------- */
  const NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, kids, ns) {
    const e = ns ? document.createElementNS(NS, tag) : document.createElement(tag);
    for (const k in attrs || {}) {
      const v = attrs[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === "text") e.textContent = v;
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v);
    }
    [].concat(kids === undefined ? [] : kids).forEach(c => { if (c != null) e.append(c); });
    return e;
  }
  const S = (tag, attrs, kids) => el(tag, attrs, kids, true);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const f1 = n => Number(n).toFixed(1);
  const narrowHost = (host, limit) => !!host && host.clientWidth > 0 && host.clientWidth < limit;   // 依容器寬度決定要不要用窄版

  // 提示框(滑鼠移入顯示;手機點一下顯示,點別處或捲動就收起)
  let tipEl = null;
  function tip(node, htmlFn) {
    if (!tipEl) {
      tipEl = el("div", { class: "ch-tip", role: "status" });
      document.body.append(tipEl);
      document.addEventListener("touchstart", e => { if (!e.target.closest("svg, .ch-brow, td, .ch-seg")) tipEl.style.display = "none"; }, { passive: true });
      window.addEventListener("scroll", () => (tipEl.style.display = "none"), { passive: true });
    }
    node.addEventListener("mousemove", e => {
      tipEl.innerHTML = htmlFn(); tipEl.style.display = "block";
      const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
      let x = e.clientX + 14, y = e.clientY + 14;
      if (x + w > innerWidth - 8) x = e.clientX - w - 14;
      if (y + h > innerHeight - 8) y = e.clientY - h - 14;
      tipEl.style.left = x + "px"; tipEl.style.top = y + "px";
    });
    node.addEventListener("mouseleave", () => (tipEl.style.display = "none"));
  }

  /* ---------- 統計:95% 信賴區間 ---------- */
  // 比例(k 件 / n 件)的 Wilson 區間,回傳 [下限, 上限](0–1)
  function wilson(k, n, z) {
    z = z || 1.96;
    if (!n) return [0, 0];
    const p = k / n, z2 = z * z, d = 1 + z2 / n, c = (p + z2 / (2 * n)) / d;
    const h = z * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / d;
    return [Math.max(0, c - h), Math.min(1, c + h)];
  }
  // 件數(Poisson)的 Byar 近似區間,回傳 [下限, 上限](同單位的件數)
  function byar(k, z) {
    z = z || 1.96;
    const lo = k === 0 ? 0 : k * Math.pow(1 - 1 / (9 * k) - z / (3 * Math.sqrt(k)), 3);
    const k1 = k + 1, hi = k1 * Math.pow(1 - 1 / (9 * k1) + z / (3 * Math.sqrt(k1)), 3);
    return [lo, hi];
  }
  function niceStep(raw) {
    const p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
    return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
  }

  /* =========================================================
   * 1. barList — 橫條清單
   *    items: [{ key, label, value, text?, selected?, tip? }]
   *    opts : { onClick(item), pageSize?, max? }
   *    pageSize 有值就分頁:每頁固定列數(不足補空列,翻頁時高度不跳動);長條以全部項目的最大值為準
   * ========================================================= */
  function barList(host, items, opts) {
    opts = opts || {};
    const st = host._barState || (host._barState = { page: 0 });
    const size = opts.pageSize, pages = size ? Math.max(1, Math.ceil(items.length / size)) : 1;
    st.page = Math.min(Math.max(0, st.page), pages - 1);
    const shown = size ? items.slice(st.page * size, (st.page + 1) * size) : items;
    const max = opts.max || Math.max(1e-9, ...(size ? items : shown).map(i => i.value));
    const anySel = items.some(i => i.selected);
    const list = el("div", { class: "ch-blist" });
    shown.forEach(it => {
      const b = el("button", { type: "button", class: "ch-brow" + (it.selected ? " sel" : "") + (anySel && !it.selected ? " dim" : ""),
        "aria-pressed": String(!!it.selected), onclick: () => opts.onClick && opts.onClick(it) }, [
        el("span", { class: "lab", text: it.label, title: it.label }),
        el("span", { class: "trk" }, el("span", { class: "fill", style: `width:${Math.max(0, it.value / max * 100)}%` })),
        el("span", { class: "val", text: it.text !== undefined ? it.text : String(it.value) })]);
      if (it.tip) tip(b, () => it.tip);
      list.append(b);
    });
    if (size) for (let i = shown.length; i < size; i++)
      list.append(el("div", { class: "ch-brow ph", "aria-hidden": "true" }, [el("span", { class: "lab", text: " " }), el("span", { class: "trk" }), el("span", { class: "val", text: " " })]));
    host.replaceChildren(list);
    if (size && pages > 1) {
      const go = d => () => { st.page += d; barList(host, items, opts); };
      host.append(el("div", { class: "ch-pager" }, [
        el("button", { class: "ch-btn", type: "button", text: "← 上一頁", disabled: st.page === 0 ? "" : null, onclick: go(-1) }),
        el("span", { text: `第 ${st.page + 1} / ${pages} 頁 · ${st.page * size + 1}–${Math.min(items.length, (st.page + 1) * size)} 項,共 ${items.length} 項` }),
        el("button", { class: "ch-btn", type: "button", text: "下一頁 →", disabled: st.page >= pages - 1 ? "" : null, onclick: go(1) })]));
    }
  }

  /* =========================================================
   * 2. columns — 直條圖(可堆疊、可標區段)
   *    opts: {
   *      categories: [{ key, label }],            // x 軸,依序畫
   *      series:     [{ key, label, color }],     // 堆疊的系列;只有一個就是普通直條
   *      values:     { [categoryKey]: { [seriesKey]: number } },
   *      bands:      [[fromIndex, toIndexExclusive, "標籤"], ...],   // 背景區段(例如早峰/日間/晚峰/夜間)
   *      selected:   Set<categoryKey>, onClick(categoryKey),
   *      labelEvery: 1(窄版自動改 3), tipText(categoryKey, row) → HTML 字串, height: 240 }
   * ========================================================= */
  function columns(host, o) {
    const nar = narrowHost(host, 520);
    const W = nar ? 380 : 720, H = o.height || 240, L = 30, T = 34, B = 30, pw = W - L - 8, ph = H - T - B;
    const cats = o.categories, series = o.series, sel = o.selected || new Set();
    const total = c => series.reduce((s, x) => s + ((o.values[c.key] || {})[x.key] || 0), 0);
    const max = Math.max(4, Math.ceil(Math.max(...cats.map(total)) / 4) * 4);
    const bw = pw / cats.length, svg = S("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.ariaLabel || "直條圖" });
    (o.bands || []).forEach(([a, b, name], i) => {
      if (i % 2 === 0) svg.append(S("rect", { class: "ch-band", x: L + a * bw, y: T, width: (b - a) * bw, height: ph }));
      svg.append(S("text", { class: "ch-t3", x: L + (a + b) / 2 * bw, y: T - 10, "text-anchor": "middle", text: name }));
    });
    for (let g = 0; g <= 4; g++) {
      const v = max * g / 4, y = T + ph - v / max * ph;
      svg.append(S("line", { class: "ch-gl", x1: L, x2: W - 8, y1: y, y2: y }));
      svg.append(S("text", { class: "ch-t3", x: L - 6, y: y + 4, "text-anchor": "end", text: Math.round(v) }));
    }
    const every = o.labelEvery || (nar ? 3 : 1), gap = nar ? 1.5 : 3;
    cats.forEach((c, i) => {
      const row = o.values[c.key] || {}, x = L + i * bw + gap, w = bw - 2 * gap, dimmed = sel.size && !sel.has(c.key);
      let yBase = T + ph;                                   // 由下往上堆疊;段與段之間留 1.5px 底色縫
      series.forEach(s => {
        const n = row[s.key] || 0; if (!n) return;
        const segH = n / max * ph, y = yBase - segH;
        svg.append(S("rect", { x, y: y + 0.75, width: w, height: Math.max(0, segH - 1.5), rx: 2, style: `fill:${s.color};opacity:${dimmed ? 0.3 : 1}` }));
        yBase = y;
      });
      const t = total(c);
      if (t) svg.append(S("text", { class: "ch-t", x: x + w / 2, y: yBase - 4, "text-anchor": "middle", text: t }));
      if (i % every === 0) svg.append(S("text", { class: "ch-t3", x: x + w / 2, y: H - 12, "text-anchor": "middle", text: c.label }));
      const hit = S("rect", { class: "ch-hit", x: L + i * bw, y: T, width: bw, height: ph + B, onclick: () => o.onClick && o.onClick(c.key) });
      tip(hit, () => o.tipText ? o.tipText(c.key, row) : `<b>${esc(c.label)}</b><br>${t}` + (series.length > 1 ? "<br>" + series.filter(s => row[s.key]).map(s => `${esc(s.label)}:${row[s.key]}`).join(" · ") : ""));
      svg.append(hit);
    });
    host.replaceChildren(svg);
  }

  /* =========================================================
   * 3. forest — 點 + 信賴區間
   *    items: [{ label, v, lo, hi, sub?, sel?, hollow?, tip?, onClick? }]   hollow=樣本太少,畫空心圓
   *    opts : { base?(整體值,畫虛線), unit?, max?, ariaLabel? }
   *    容器窄於 620px 時自動改成「每列兩行」(上行文字、下行全寬區間圖),手機不需左右捲動
   * ========================================================= */
  function forest(host, items, opts) {
    opts = opts || {};
    const nar = narrowHost(host, 620);
    const W = nar ? 360 : 720, rowH = nar ? 54 : 34, left = nar ? 12 : 128, right = nar ? 12 : 138, top = nar ? 30 : 26, bot = 28;
    const H = top + items.length * rowH + bot;
    const max = opts.max || Math.max(1, ...items.map(i => i.hi)) * 1.06;
    const X = v => left + (W - left - right) * v / max;
    const svg = S("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.ariaLabel || "信賴區間圖", style: nar ? "" : "min-width:600px" });
    const step = niceStep(max / (nar ? 4 : 5));
    for (let v = 0; v <= max; v += step) {
      svg.append(S("line", { class: "ch-gl", x1: X(v), x2: X(v), y1: top - 6, y2: H - bot + 2 }));
      svg.append(S("text", { class: "ch-t3", x: X(v), y: H - 8, "text-anchor": "middle", text: +v.toFixed(2) }));
    }
    if (opts.base != null) {
      svg.append(S("line", { class: "ch-base", x1: X(opts.base), x2: X(opts.base), y1: top - 10, y2: H - bot + 2 }));
      svg.append(S("text", { class: "ch-t", x: Math.min(X(opts.base) + 4, W - 60), y: top - 14, text: `整體 ${f1(opts.base)}` }));
    }
    items.forEach((it, i) => {
      const y0 = top + i * rowH, cy = nar ? y0 + 36 : y0 + rowH / 2;
      const lab = { class: "ch-tb", text: it.label, style: it.sel ? "font-weight:700" : "" };
      if (nar) {
        svg.append(S("text", Object.assign({ x: left, y: y0 + 15 }, lab)));
        svg.append(S("text", { class: "ch-tb", x: W - right, y: y0 + 15, "text-anchor": "end", text: `${f1(it.v)}${opts.unit || ""}${it.sub ? "  (" + it.sub + ")" : ""}` }));
      } else svg.append(S("text", Object.assign({ x: 4, y: cy + 4 }, lab)));
      svg.append(S("line", { class: "ch-ci", x1: X(it.lo), x2: X(it.hi), y1: cy, y2: cy }));
      svg.append(S("line", { class: "ch-ci", x1: X(it.lo), x2: X(it.lo), y1: cy - 4, y2: cy + 4 }));
      svg.append(S("line", { class: "ch-ci", x1: X(it.hi), x2: X(it.hi), y1: cy - 4, y2: cy + 4 }));
      svg.append(S("circle", { class: "ch-dot" + (it.hollow ? " hollow" : "") + (it.sel ? " sel" : ""), cx: X(it.v), cy, r: 6 }));
      if (!nar) {
        svg.append(S("text", { class: "ch-tb", x: W - right + 12, y: cy + 1, text: f1(it.v) + (opts.unit || "") }));
        if (it.sub) svg.append(S("text", { class: "ch-t3", x: W - right + 12, y: cy + 14, text: it.sub }));
      }
      const hit = S("rect", { class: "ch-hit", x: 0, y: y0, width: W, height: rowH, onclick: () => it.onClick && it.onClick(it) });
      if (it.tip) tip(hit, () => it.tip);
      svg.append(hit);
    });
    host.replaceChildren(svg);
  }

  /* =========================================================
   * 4. stackedBars — 橫向堆疊條
   *    rows  : [{ key, label, values: { [seriesKey]: number } }]
   *    series: [{ key, label, color }]
   *    opts  : { onClick(rowKey), selected?: Set, legendHost?: Element, unit?: "起" }
   * ========================================================= */
  function stackedBars(host, rows, series, opts) {
    opts = opts || {};
    const tot = r => series.reduce((s, x) => s + (r.values[x.key] || 0), 0);
    const max = Math.max(1, ...rows.map(tot)), sel = opts.selected || new Set();
    const wrap = el("div", { class: "ch-stk" });
    rows.forEach(r => {
      const tr = el("div", { class: "ch-tr" });
      series.forEach(s => {
        const n = r.values[s.key] || 0; if (!n) return;
        const seg = el("div", { class: "ch-seg", style: `width:${n / max * 100}%;background:${s.color}` });
        tip(seg, () => `<b>${esc(r.label)}</b> · ${esc(s.label)}<br>${n} ${opts.unit || ""}`);
        tr.append(seg);
      });
      wrap.append(el("div", { class: "ch-srow" + (sel.has(r.key) ? " sel" : "") }, [
        el("button", { type: "button", class: "l", text: r.label, onclick: () => opts.onClick && opts.onClick(r.key) }), tr,
        el("span", { class: "ch-muted", text: tot(r) + " " + (opts.unit || "") })]));
    });
    host.replaceChildren(wrap);
    if (opts.legendHost) opts.legendHost.replaceChildren(...series.map(s => el("span", {}, [el("i", { style: `background:${s.color}` }), s.label])));
  }

  /* =========================================================
   * 5. heatmap — 熱度表(格內顯示件數與該列占比,顏色越深占比越高)
   *    opts: { rows:[{key,label}], cols:[{key,label}], matrix:[[n...]...], rgb:"42,120,214", showTotal:true,
   *            selected?: {row,col}, onCell(rowKey,colKey), cellTip?(r,c,n,share) }
   * ========================================================= */
  function heatmap(host, o) {
    const rgb = o.rgb || "42,120,214";
    const tb = el("table", { class: "ch-mx" });
    tb.append(el("tr", {}, [el("th", { class: "rl" }), ...o.cols.map(c => el("th", { text: c.label })), o.showTotal === false ? null : el("th", { text: "合計" })]));
    o.rows.forEach((r, i) => {
      const tot = o.matrix[i].reduce((a, b) => a + b, 0), tr = el("tr", {}, [el("th", { class: "rl", text: r.label })]);
      o.cols.forEach((c, j) => {
        const n = o.matrix[i][j], share = tot ? n / tot : 0;
        const on = o.selected && o.selected.row === r.key && o.selected.col === c.key;
        const td = el("td", { class: on ? "sel" : "", style: `background:rgba(${rgb},${(share * 0.8).toFixed(2)});color:${share > .5 ? "#fff" : "inherit"}`,
          onclick: () => o.onCell && o.onCell(r.key, c.key) }, [String(n), el("small", { text: tot ? Math.round(share * 100) + "%" : "–" })]);
        tip(td, () => o.cellTip ? o.cellTip(r, c, n, share) : `<b>${esc(r.label)} · ${esc(c.label)}</b><br>${n},占該列 ${f1(share * 100)}%`);
        tr.append(td);
      });
      if (o.showTotal !== false) tr.append(el("td", { class: "tot", text: String(tot) }));
      tb.append(tr);
    });
    host.replaceChildren(tb);
  }

  /* =========================================================
   * 6. geoScatter — 可縮放、拖曳的點位地圖(純 SVG)
   *    opts: {
   *      outlines: [{ d, label?, labelAt?:[x,y], focus?: boolean }],   // 縣市界等底圖;d = SVG path,座標為地圖單位
   *      layers:   [{ d, className }],                                  // 道路等線圖層,className 對應 CSS(例如 road motorway)
   *      points:   [{ x, y, r?, color, tip?, onClick? }],               // 點;r = 基準半徑(螢幕像素,預設 4)
   *      ghosts:   [{ x, y }],                                          // 被篩掉的點(淡灰小點)
   *      maxZoom: 14, view?: {x,y,w,h}(保留縮放位置)
   *    }
   *    座標系:自行投影成平面座標(報告用 x = 經度×cos(緯度)×1000、y = −緯度×1000)
   *    互動:滾輪/雙指縮放、拖曳、連點兩下放大、右上角 + − ⟲ 按鈕;放大時點與文字維持固定螢幕大小
   *    回傳 { view, reset() }
   * ========================================================= */
  function geoScatter(host, o) {
    const pts = o.points || [], maxZoom = o.maxZoom || 14;
    // 底圖範圍:所有 outlines 的路徑座標
    let x0 = 1e18, y0 = 1e18, x1 = -1e18, y1 = -1e18;
    (o.outlines || []).forEach(p => { const n = p.d.match(/-?\d+(?:\.\d+)?/g); if (!n) return;
      for (let i = 0; i + 1 < n.length; i += 2) { const x = +n[i], y = +n[i + 1]; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; } });
    if (x0 > x1) { pts.forEach(p => { x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); }); }
    const pad = Math.max(x1 - x0, y1 - y0) * 0.03;
    const base = o.base || { x: x0 - pad, y: y0 - pad, w: x1 - x0 + 2 * pad, h: y1 - y0 + 2 * pad };
    const view = o.view && o.view.w ? o.view : Object.assign({}, base);
    const k = base.w / 620, svg = S("svg", { role: "img", "aria-label": o.ariaLabel || "點位地圖(可縮放、拖曳)", style: `aspect-ratio:${base.w}/${base.h}` });
    (o.outlines || []).forEach(p => {
      svg.append(S("path", { class: "ch-county" + (p.focus ? " focus" : ""), d: p.d, "fill-rule": "evenodd" }));
      if (p.label && p.labelAt) svg.append(S("text", { x: p.labelAt[0], y: p.labelAt[1], class: "ch-t3", "text-anchor": "middle", "data-fs": 13 * k, style: "opacity:.7", text: p.label }));
    });
    (o.layers || []).forEach(l => svg.append(S("path", { class: l.className, d: l.d })));
    (o.ghosts || []).forEach(g => svg.append(S("circle", { class: "ch-ghost", cx: g.x, cy: g.y, "data-r": 2.2 * k })));
    let lastDrag = 0;
    pts.forEach(p => {
      const c = S("circle", { class: "ch-pt", cx: p.x, cy: p.y, "data-r": (p.r || 4.2) * k, fill: p.color,
        onclick: () => { if (performance.now() - lastDrag < 350) return; p.onClick && p.onClick(p); } });
      if (p.tip) tip(c, () => p.tip);
      svg.append(c);
    });
    const z = () => base.w / view.w;
    function apply() {
      view.w = Math.min(base.w, Math.max(base.w / maxZoom, view.w)); view.h = view.w * base.h / base.w;
      view.x = Math.min(base.x + base.w - view.w, Math.max(base.x, view.x)); view.y = Math.min(base.y + base.h - view.h, Math.max(base.y, view.y));
      svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
      const zz = z();
      svg.querySelectorAll("[data-r]").forEach(c => c.setAttribute("r", (+c.dataset.r / zz).toFixed(2)));      // 點維持固定螢幕大小
      svg.querySelectorAll("[data-fs]").forEach(t => (t.style.fontSize = (+t.dataset.fs / zz).toFixed(2) + "px"));
      svg.classList.add("moving"); clearTimeout(svg._mv); svg._mv = setTimeout(() => svg.classList.remove("moving"), 180);   // 拖曳中隱藏 .minor 圖層(CSS)
      svg.classList.toggle("z2", zz >= 2);                                                                       // 放大 2 倍以上才顯示 .detail 圖層(CSS)
      svg.style.touchAction = zz > 1.01 ? "none" : "pan-y"; svg.style.cursor = zz > 1.01 ? "grab" : "default";
      zin.disabled = zz >= maxZoom - 0.01; zout.disabled = zz <= 1.01;
    }
    const toSvg = (cx, cy) => { const pt = svg.createSVGPoint(); pt.x = cx; pt.y = cy; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
    function zoomAt(px, py, f) {
      const w2 = Math.min(base.w, Math.max(base.w / maxZoom, view.w / f)), ratio = w2 / view.w;
      view.x = px - (px - view.x) * ratio; view.y = py - (py - view.y) * ratio; view.w = w2; apply();
    }
    const mid = f => () => zoomAt(view.x + view.w / 2, view.y + view.h / 2, f);
    const zin = el("button", { type: "button", "aria-label": "放大", text: "+", onclick: mid(1.7) });
    const zout = el("button", { type: "button", "aria-label": "縮小", text: "−", onclick: mid(1 / 1.7) });
    const zreset = el("button", { type: "button", "aria-label": "回到全圖", text: "⟲", onclick: () => { Object.assign(view, base); apply(); } });
    svg.addEventListener("wheel", e => { e.preventDefault(); const p = toSvg(e.clientX, e.clientY); zoomAt(p.x, p.y, Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0016))); }, { passive: false });
    svg.addEventListener("dblclick", e => { const p = toSvg(e.clientX, e.clientY); zoomAt(p.x, p.y, 2); });
    const ptrs = new Map(); let down = null, moved = false, prevDist = 0, prevCenter = null;
    svg.addEventListener("pointerdown", e => {
      ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (ptrs.size === 1) { down = { x: e.clientX, y: e.clientY }; moved = false; }
      if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; prevDist = Math.hypot(a.x - b.x, a.y - b.y); prevCenter = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; moved = true; }
    });
    svg.addEventListener("pointermove", e => {
      if (!ptrs.has(e.pointerId)) return;
      const prev = ptrs.get(e.pointerId), cur = { x: e.clientX, y: e.clientY }; ptrs.set(e.pointerId, cur);
      if (ptrs.size === 2) {                                                  // 雙指:縮放 + 平移
        const [a, b] = [...ptrs.values()], dist = Math.hypot(a.x - b.x, a.y - b.y), ctr = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, ppu = svg.getScreenCTM().a;
        view.x -= (ctr.x - prevCenter.x) / ppu; view.y -= (ctr.y - prevCenter.y) / ppu;
        const p = toSvg(ctr.x, ctr.y); if (prevDist > 0) zoomAt(p.x, p.y, dist / prevDist); else apply();
        prevDist = dist; prevCenter = ctr; return;
      }
      if (z() <= 1.01) return;                                                // 未放大時不拖曳(手機單指 = 捲頁面)
      if (!moved && Math.hypot(cur.x - down.x, cur.y - down.y) < 5) return;    // 小於 5px 視為點選
      if (!moved) { moved = true; try { svg.setPointerCapture(e.pointerId); } catch (_) {} svg.style.cursor = "grabbing"; }
      const ppu = svg.getScreenCTM().a; view.x -= (cur.x - prev.x) / ppu; view.y -= (cur.y - prev.y) / ppu; apply();
    });
    const end = e => {
      if (!ptrs.delete(e.pointerId)) return;
      if (moved) lastDrag = performance.now();
      if (ptrs.size < 2) prevDist = 0;
      if (ptrs.size === 1) down = Object.assign({}, [...ptrs.values()][0]);
      if (ptrs.size === 0) { moved = false; svg.style.cursor = z() > 1.01 ? "grab" : "default"; }
    };
    svg.addEventListener("pointerup", end); svg.addEventListener("pointercancel", end); svg.addEventListener("lostpointercapture", end);
    host.classList.add("ch-mapbox");
    host.replaceChildren(svg, el("div", { class: "ch-mapctl" }, [zin, zout, zreset]));
    apply();
    return { view, reset: () => { Object.assign(view, base); apply(); } };
  }

  global.Charts = { el, svg: S, esc, tip, wilson, byar, barList, columns, forest, stackedBars, heatmap, geoScatter };
})(window);
