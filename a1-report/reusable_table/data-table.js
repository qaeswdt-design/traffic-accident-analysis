/*
 * data-table.js — 無相依(不需要任何套件)的資料表元件
 * 功能:多關鍵字搜尋、點表頭排序、下拉與勾選篩選、自選欄位、固定高度翻頁、
 *       點列展開詳細資料、資料標註 ⚑、匯出 CSV。
 *
 * 用法:
 *   DataTable.mount(document.getElementById("box"), { data: [ {...}, ... ], config: { ... } });
 * config 的欄位說明見同資料夾的 README.md;範例見 table.config.json。
 * 這個檔案是從「A1 死亡事故互動報告」的事故明細表抽出來的,行為與該表一致,
 * 但所有欄位、篩選、詳細資料都由 config 決定,換一份資料只要換 config。
 */
(function (global) {
  "use strict";

  /* ---------- 小工具 ---------- */
  function el(tag, attrs, kids) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) {
      const v = attrs[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === "text") e.textContent = v;
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v);
    }
    [].concat(kids || []).forEach(c => { if (c != null) e.append(c); });
    return e;
  }
  // 範本:{欄位} 或 {欄位|沒有值時顯示的文字}
  const tpl = (t, row) => String(t).replace(/\{([^{}|]+)(?:\|([^{}]*))?\}/g, (_, k, d) => {
    const v = row[k.trim()];
    return v === null || v === undefined || v === "" ? (d === undefined ? "" : d) : v;
  });
  const isNum = v => typeof v === "number" && !isNaN(v);

  // 衍生欄位,三種寫法:
  //  1) rules  :依規則把數值分組(例如年齡 → 年齡層)。規則由上往下,第一個全部成立的規則決定結果
  //  2) split  :把文字切開取其中一段,例如 {"from":"p","split":" / ","index":0}
  //  3) template:用範本組合欄位;可加 whenDifferent:[a,b](兩欄不同才用 template,否則用 otherwise)
  function applyComputed(rows, computed) {
    Object.keys(computed || {}).forEach(name => {
      const def = computed[name];
      if (def.split !== undefined) { rows.forEach(r => { const v = r[def.from]; r[name] = v == null ? "" : String(v).split(def.split)[def.index || 0] || ""; }); return; }
      if (def.template !== undefined) {
        rows.forEach(r => {
          const same = def.whenDifferent && (r[def.whenDifferent[0]] === r[def.whenDifferent[1]] || r[def.whenDifferent[1]] == null || r[def.whenDifferent[1]] === "");
          r[name] = same ? tpl(def.otherwise || "", r) : tpl(def.template, r);
        });
        return;
      }
      rows.forEach(r => {
        const v = r[def.from];
        for (const rule of def.rules) {
          const ok = (!rule.isNull || v == null) &&
            (rule.lt === undefined || (v != null && v < rule.lt)) && (rule.lte === undefined || (v != null && v <= rule.lte)) &&
            (rule.gt === undefined || (v != null && v > rule.gt)) && (rule.gte === undefined || (v != null && v >= rule.gte)) &&
            (rule.eq === undefined || v === rule.eq);
          if (ok) { r[name] = rule.label; return; }
        }
        r[name] = "";
      });
    });
  }
  const OPS = { ">=": (a, b) => a >= b, ">": (a, b) => a > b, "<=": (a, b) => a <= b, "<": (a, b) => a < b, "==": (a, b) => a === b, "!=": (a, b) => a !== b,
    nonEmpty: a => (Array.isArray(a) ? a.length > 0 : !!a) };

  /* ---------- 主程式 ---------- */
  function mount(root, opts) {
    const cfg = opts.config || {};
    const rows = (opts.data || []).map(r => Object.assign({}, r));
    applyComputed(rows, cfg.computed);
    const L = Object.assign({ search: "搜尋(多個關鍵字用空白分隔,需全部符合)", clear: "清除表格篩選", columns: "欄位", csv: "匯出 CSV",
      prev: "← 上一頁", next: "下一頁 →", first: "« 第一頁", last: "最後頁 »", empty: "沒有符合的資料。可以放寬搜尋關鍵字或清除篩選。",
      all: "全部", sortHint: "點一下排序,再點切換方向", perPage: n => `每頁 ${n} 筆`,
      count: (n, total) => `共 ${n} 筆` + (n !== total ? `(全部 ${total} 筆)` : ""),
      pageInfo: (p, pages, a, b, n) => (n ? `第 ${p} / ${pages} 頁 · ${a}–${b} 筆,共 ${n} 筆` : "沒有符合的資料") }, cfg.labels || {});
    const columns = cfg.columns || [];
    const state = { sortKey: (cfg.defaultSort || {}).key || (columns[0] || {}).key, sortDir: (cfg.defaultSort || {}).dir === "asc" ? 1 : -1,
      q: "", f: {}, page: 0, size: cfg.pageSize || 15, open: null, cols: new Set(columns.filter(c => c.default !== false).map(c => c.key)) };
    const colOf = k => columns.find(c => c.key === k);
    const cellText = (c, r) => (c.template ? tpl(c.template, r) : (r[c.key] == null ? "" : String(r[c.key])));
    const hay = r => {
      const parts = (cfg.search && cfg.search.fields ? cfg.search.fields : columns.map(c => c.key)).map(k => r[k]);
      (cfg.search && cfg.search.extraTemplates || []).forEach(t => parts.push(tpl(t, r)));
      return parts.map(v => (Array.isArray(v) ? v.join(" ") : v == null ? "" : String(v))).join(" ").toLowerCase();
    };
    const sortVal = (c, r) => {
      const keys = c.sortBy || [c.key];
      return keys.map(k => (r[k] == null ? (c.type === "number" ? -Infinity : "") : r[k]));
    };
    const cmp = (c, a, b) => {
      const x = sortVal(c, a), y = sortVal(c, b);
      for (let i = 0; i < x.length; i++) {
        const d = isNum(x[i]) && isNum(y[i]) ? x[i] - y[i] : String(x[i]).localeCompare(String(y[i]), cfg.locale || "zh-Hant");
        if (d) return d;
      }
      return 0;
    };
    const pass = r => {
      for (const f of cfg.filters || []) {
        const v = state.f[f.key];
        if (!v) continue;
        if (f.type === "select") { if (String(r[f.field]) !== v) return false; }
        else if (f.type === "check") { const op = OPS[f.op || "=="]; if (!op(r[f.field], f.value)) return false; }
      }
      return true;
    };

    /* ----- 靜態結構 ----- */
    const q = el("input", { class: "dt-search", type: "search", placeholder: L.search, "aria-label": L.search });
    const clearBtn = el("button", { class: "dt-btn", type: "button", text: L.clear, hidden: "" });
    const colMenu = el("div", { class: "dt-colmenu" });
    const colBtn = el("details", { class: "dt-colpick" }, [el("summary", { class: "dt-btn", text: L.columns }), colMenu]);
    const csvBtn = el("button", { class: "dt-btn", type: "button", text: L.csv });
    const filterBar = el("div", { class: "dt-filters" });
    const countEl = el("div", { class: "dt-count" });
    const thead = el("thead"), tbody = el("tbody");
    const scroll = el("div", { class: "dt-scroll", style: `height:${cfg.height || 560}px` }, el("table", { class: "dt-table" }, [thead, tbody]));
    const pager = el("div", { class: "dt-pager" });
    root.classList.add("dt-root");
    root.replaceChildren(el("div", { class: "dt-ctl" }, [q, clearBtn, colBtn, csvBtn]), filterBar, countEl, scroll, pager);

    /* ----- 篩選控制項(依資料自動產生選項與件數) ----- */
    (cfg.filters || []).forEach(f => {
      if (f.type === "select") {
        const cnt = new Map();
        rows.forEach(r => { const v = r[f.field]; if (v !== undefined && v !== null && v !== "") cnt.set(String(v), (cnt.get(String(v)) || 0) + 1); });
        const order = Array.isArray(f.order) ? f.order.filter(v => cnt.has(v)) : [...cnt.keys()].sort((a, b) => f.order === "asc" ? a.localeCompare(b, cfg.locale || "zh-Hant") : cnt.get(b) - cnt.get(a));
        filterBar.append(el("select", { "aria-label": f.label, "data-k": f.key, onchange: e => { state.f[f.key] = e.target.value; state.page = 0; draw(); } },
          [el("option", { value: "", text: `${f.label}:${L.all}` })].concat(order.map(v => el("option", { value: v, text: `${v}(${cnt.get(v)})` })))));
      } else if (f.type === "check") {
        filterBar.append(el("label", {}, [el("input", { type: "checkbox", "data-k": f.key, onchange: e => { state.f[f.key] = e.target.checked; state.page = 0; draw(); } }), f.label]));
      }
    });
    columns.forEach(c => colMenu.append(el("label", {}, [el("input", { type: "checkbox", checked: state.cols.has(c.key) ? "" : null,
      onchange: e => { e.target.checked ? state.cols.add(c.key) : state.cols.delete(c.key); draw(); } }), c.label])));
    q.addEventListener("input", () => { state.q = q.value; state.page = 0; draw(); });
    clearBtn.addEventListener("click", () => { state.f = {}; state.q = ""; q.value = ""; state.page = 0; draw(); });
    csvBtn.addEventListener("click", () => exportCsv());

    let current = [];
    function draw() {
      filterBar.querySelectorAll("[data-k]").forEach(c => { const v = state.f[c.dataset.k]; if (c.type === "checkbox") c.checked = !!v; else c.value = v || ""; });
      const terms = state.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
      const col = colOf(state.sortKey) || columns[0];
      current = rows.filter(pass).filter(r => { if (!terms.length) return true; const h = hay(r); return terms.every(t => h.includes(t)); })
        .sort((a, b) => cmp(col, a, b) * state.sortDir);
      const cols = columns.filter(c => state.cols.has(c.key));
      thead.replaceChildren(el("tr", {}, cols.map(c => {
        const on = state.sortKey === c.key;
        return el("th", { "aria-sort": on ? (state.sortDir > 0 ? "ascending" : "descending") : null, class: c.type === "number" ? "dt-num" : "" },
          el("button", { type: "button", title: L.sortHint, onclick: () => {
            if (state.sortKey === c.key) state.sortDir *= -1; else { state.sortKey = c.key; state.sortDir = c.type === "number" || c.sortFirst === "desc" ? -1 : 1; }
            state.page = 0; draw(); } }, [c.label, el("span", { class: "dt-arw", text: on ? (state.sortDir > 0 ? "▲" : "▼") : "↕" })]));
      })));
      const pages = Math.max(1, Math.ceil(current.length / state.size));
      state.page = Math.min(Math.max(0, state.page), pages - 1);
      const from = state.page * state.size, pageRows = current.slice(from, from + state.size);
      tbody.replaceChildren();
      pageRows.forEach(r => {
        const open = state.open === r, toggle = () => { state.open = open ? null : r; draw(); };
        tbody.append(el("tr", { class: "dt-row" + (open ? " dt-open" : ""), tabindex: "0", "aria-expanded": String(open), onclick: toggle,
          onkeydown: e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } } },
          cols.map(c => el("td", { class: c.type === "number" ? "dt-num" : "" }, [cellText(c, r),
            cfg.flagColumn === c.key && cfg.flagField && r[cfg.flagField] && r[cfg.flagField].length
              ? el("span", { class: "dt-flag", title: (cfg.flagTitle || "資料標註:") + r[cfg.flagField].join(";"), text: " ⚑" }) : null]))));
        if (open) tbody.append(detail(r, cols.length));
      });
      if (!current.length) tbody.append(el("tr", {}, el("td", { colspan: cols.length, class: "dt-faint", text: L.empty })));
      clearBtn.hidden = !(terms.length || Object.keys(state.f).some(k => state.f[k]));
      countEl.textContent = L.count(current.length, rows.length);
      const go = p => () => { state.page = p; draw(); };
      const sizeSel = el("select", { "aria-label": "page size", onchange: e => { state.size = +e.target.value; state.page = 0; draw(); } },
        (cfg.pageSizes || [10, 15, 30]).map(n => el("option", { value: n, text: L.perPage(n), selected: n === state.size ? "" : null })));
      pager.replaceChildren(
        el("div", { class: "dt-row-flex" }, [el("button", { class: "dt-btn", type: "button", text: L.first, disabled: state.page === 0 ? "" : null, onclick: go(0) }),
          el("button", { class: "dt-btn", type: "button", text: L.prev, disabled: state.page === 0 ? "" : null, onclick: go(state.page - 1) })]),
        el("span", { text: L.pageInfo(state.page + 1, pages, from + 1, from + pageRows.length, current.length) }),
        el("div", { class: "dt-row-flex" }, [sizeSel, el("button", { class: "dt-btn", type: "button", text: L.next, disabled: state.page >= pages - 1 ? "" : null, onclick: go(state.page + 1) }),
          el("button", { class: "dt-btn", type: "button", text: L.last, disabled: state.page >= pages - 1 ? "" : null, onclick: go(pages - 1) })]));
    }
    function detail(r, span) {
      const items = (cfg.detail || []).map(d => {
        const v = tpl(d.template, r);
        if (d.hideIfEmpty && !v.trim()) return null;
        return el("div", {}, [el("b", { text: d.label }), v || "—"]);
      });
      if (cfg.flagField && r[cfg.flagField] && r[cfg.flagField].length)
        items.push(el("div", {}, [el("b", { text: cfg.flagLabel || "資料標註" }), el("span", { class: "dt-flag", text: "⚑ " + r[cfg.flagField].join(";") })]));
      return el("tr", { class: "dt-detail" }, el("td", { colspan: span }, el("div", { class: "dt-kv" }, items)));
    }
    function exportCsv() {
      const cols = (cfg.csv && cfg.csv.columns) || columns.map(c => [c.key, c.label]);
      const esc = v => `"${String(Array.isArray(v) ? v.join(";") : v == null ? "" : v).replace(/"/g, '""')}"`;
      const text = "﻿" + [cols.map(c => esc(c[1])).join(","), ...current.map(r => cols.map(c => esc(r[c[0]])).join(","))].join("\r\n");
      const a = el("a", { href: URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" })), download: (cfg.csv && cfg.csv.filename) || "table.csv" });
      document.body.append(a); a.click(); a.remove();
    }
    draw();
    return { redraw: draw, getRows: () => current.slice(), state };
  }

  global.DataTable = { mount };
})(window);
