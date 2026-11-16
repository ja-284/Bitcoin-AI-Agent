// Små, avhengighetsfrie SVG-diagrammer: ring, smultring, minilinje, linjediagram med trådkors og søyler med
// verktøytips. Ett y-akse-sett per diagram (aldri to skalaer). Tekst fra dataene settes alltid med textContent.

const NS = "http://www.w3.org/2000/svg";

export function svg(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
  for (const k of kids) if (k != null) el.append(k);
  return el;
}

function text(x, y, s, attrs = {}) {
  const t = svg("text", { x, y, ...attrs });
  t.textContent = s;
  return t;
}

// ---------------------------------------------------------------- ring: én andel (0..1), tall i midten
export function ring({ value, size = 96, stroke = 9, color = "var(--accent)", center = "", sub = "", label = "" }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = value == null || !isFinite(value) ? 0 : Math.max(0, Math.min(1, value));
  const s = svg("svg", { class: "ring", width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: "img",
    "aria-label": label || `${center} ${sub}` });
  s.append(
    svg("circle", { cx: size / 2, cy: size / 2, r, fill: "none", stroke: "var(--line-2)", "stroke-width": stroke }),
    svg("circle", { class: "arc", cx: size / 2, cy: size / 2, r, fill: "none", stroke: color, "stroke-width": stroke,
      "stroke-linecap": "round", "stroke-dasharray": c, "stroke-dashoffset": c * (1 - v),
      transform: `rotate(-90 ${size / 2} ${size / 2})` }),
    text(size / 2, sub ? size / 2 + 1 : size / 2 + 6, center, { "text-anchor": "middle", fill: "var(--text)",
      "font-size": size > 110 ? 26 : size > 80 ? 19 : 15, "font-weight": 700 }),
  );
  if (sub) s.append(text(size / 2, size / 2 + 17, sub, { "text-anchor": "middle", fill: "var(--muted)", "font-size": 11 }));
  return s;
}

// ---------------------------------------------------------------- smultring: deler av en helhet (<= 6 deler)
export function donut({ parts, size = 132, stroke = 16, center = "", sub = "", tip }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  const gap = parts.filter((p) => p.value > 0).length > 1 ? 3 : 0;
  const s = svg("svg", { class: "ring", width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: "img",
    "aria-label": parts.map((p) => `${p.label}: ${p.value}`).join(", ") });
  s.append(svg("circle", { cx: size / 2, cy: size / 2, r, fill: "none", stroke: "var(--line)", "stroke-width": stroke }));
  let at = 0;
  for (const p of parts) {
    if (p.value <= 0) continue;
    const len = (p.value / total) * c;
    const seg = svg("circle", { cx: size / 2, cy: size / 2, r, fill: "none", stroke: p.color, "stroke-width": stroke,
      "stroke-dasharray": `${Math.max(len - gap, 0.5)} ${c}`, "stroke-dashoffset": -at,
      transform: `rotate(-90 ${size / 2} ${size / 2})`, tabindex: 0, style: "cursor:pointer" });
    if (tip) {
      const show = (e) => tip.show(e, [{ value: `${p.value}`, label: p.label }]);
      seg.addEventListener("pointermove", show);
      seg.addEventListener("focus", show);
      seg.addEventListener("pointerleave", () => tip.hide());
      seg.addEventListener("blur", () => tip.hide());
    }
    s.append(seg);
    at += len;
  }
  s.append(text(size / 2, size / 2 + 2, center, { "text-anchor": "middle", fill: "var(--text)", "font-size": 24, "font-weight": 700 }));
  if (sub) s.append(text(size / 2, size / 2 + 19, sub, { "text-anchor": "middle", fill: "var(--muted)", "font-size": 11 }));
  return s;
}

// ---------------------------------------------------------------- minilinje (i lister; tallene står ved siden av)
export function spark(values, { width = 64, height = 26, color = "var(--accent)" } = {}) {
  const pts = values.map((v, i) => [i, v]).filter(([, v]) => v != null);
  const s = svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" });
  if (pts.length < 2) {
    s.append(svg("line", { x1: 2, x2: width - 2, y1: height / 2, y2: height / 2, stroke: "var(--line-2)", "stroke-width": 2, "stroke-linecap": "round" }));
    return s;
  }
  const lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
  const span = hi - lo || 1;
  const n = values.length - 1 || 1;
  const d = pts.map(([i, v], k) => `${k ? "L" : "M"}${(2 + (i / n) * (width - 4)).toFixed(1)},${(height - 3 - ((v - lo) / span) * (height - 6)).toFixed(1)}`).join("");
  s.append(svg("path", { d, fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
  return s;
}

// ---------------------------------------------------------------- linjediagram med trådkors
// series: [{name, values, color, dash, area}], dates: ["2030-01-01", ...], markers: [{i, kind: "BUY"|"SELL"}]
export function lineChart(host, { dates, series, markers = [], height = 230, fmtY, fmtDate, tip, extra }) {
  host.replaceChildren();
  const W = Math.max(host.clientWidth, 260), H = height, padT = 14, padB = 26, padR = 4;
  const all = series.flatMap((s) => s.values).filter((v) => v != null);
  if (!all.length) {
    host.append(Object.assign(document.createElement("p"), { className: "empty", textContent: "Ingen data ennå." }));
    return;
  }
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08;
  lo -= pad; hi += pad;
  const n = dates.length;
  const x = (i) => (n === 1 ? W / 2 : (i / (n - 1)) * (W - padR));
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": series.map((q) => q.name).join(" og ") });
  const defs = svg("defs");
  const gid = `g${Math.random().toString(36).slice(2, 8)}`;
  defs.append(svg("linearGradient", { id: gid, x1: 0, x2: 0, y1: 0, y2: 1 },
    svg("stop", { offset: "0%", "stop-color": series[0].color, "stop-opacity": 0.28 }),
    svg("stop", { offset: "100%", "stop-color": series[0].color, "stop-opacity": 0 })));
  s.append(defs);
  // rolig rutenett: tre linjer med verdier på høyre side
  for (let k = 0; k < 3; k++) {
    const v = lo + ((k + 0.5) / 3) * (hi - lo);
    s.append(svg("line", { x1: 0, x2: W, y1: y(v), y2: y(v), stroke: "var(--line)", "stroke-width": 1 }));
    s.append(text(W - 2, y(v) - 4, fmtY(v), { "text-anchor": "end", fill: "var(--muted)", "font-size": 10.5 }));
  }
  // datoer: første, midten, siste
  [0, Math.floor((n - 1) / 2), n - 1].filter((v, i, a) => a.indexOf(v) === i).forEach((i, k, arr) => {
    s.append(text(x(i), H - 6, fmtDate(dates[i]), { "text-anchor": k === 0 ? "start" : k === arr.length - 1 ? "end" : "middle",
      fill: "var(--muted)", "font-size": 10.5 }));
  });
  const path = (vals) => {
    let d = "", pen = false;
    vals.forEach((v, i) => {
      if (v == null) return;
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  series.forEach((q, k) => {
    const d = path(q.values);
    if (!d) return;
    if (q.area) {
      const firstI = q.values.findIndex((v) => v != null);
      const lastI = q.values.length - 1 - [...q.values].reverse().findIndex((v) => v != null);
      s.append(svg("path", { d: `${d}L${x(lastI).toFixed(1)},${H - padB}L${x(firstI).toFixed(1)},${H - padB}Z`, fill: `url(#${gid})` }));
    }
    s.append(svg("path", { d, fill: "none", stroke: q.color, "stroke-width": k === 0 ? 2.25 : 2, "stroke-dasharray": q.dash ? "5 5" : null,
      "stroke-linejoin": "round", "stroke-linecap": "round" }));
  });
  // kjøp ▲ under linjen, salg ▼ over, med en ring i flatens farge rundt
  const main = series[0].values;
  for (const m of markers) {
    const v = main[m.i];
    if (v == null) continue;
    const cx = x(m.i), cy = y(v), up = m.kind === "BUY";
    const tri = up ? `M${cx},${cy + 7} l6,10 l-12,0 Z` : `M${cx},${cy - 7} l6,-10 l-12,0 Z`;
    s.append(svg("path", { d: tri, fill: up ? "var(--up)" : "var(--down)", stroke: "var(--card-solid)", "stroke-width": 2, "stroke-linejoin": "round" }));
  }
  // trådkors
  const cross = svg("line", { y1: padT, y2: H - padB, stroke: "var(--line-2)", "stroke-width": 1, visibility: "hidden" });
  const dots = series.map((q) => svg("circle", { r: 4.5, fill: q.color, stroke: "var(--card-solid)", "stroke-width": 2, visibility: "hidden" }));
  s.append(cross, ...dots);
  const hit = svg("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent", tabindex: 0, style: "outline:none" });
  s.append(hit);
  let focusI = n - 1;
  const showAt = (i, evt) => {
    i = Math.max(0, Math.min(n - 1, i));
    focusI = i;
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    series.forEach((q, k) => {
      const v = q.values[i];
      dots[k].setAttribute("visibility", v == null ? "hidden" : "visible");
      if (v != null) { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); }
    });
    const rows = series.map((q) => ({ value: q.values[i] == null ? "–" : fmtY(q.values[i], true), label: q.name, color: q.color, dash: q.dash }));
    const more = extra ? extra(i) : null;
    if (more) rows.push(more);
    const r = s.getBoundingClientRect();
    tip.show(evt || { clientX: r.left + (x(i) / W) * r.width, clientY: r.top + 20 }, rows, fmtDate(dates[i], true));
  };
  const toIndex = (evt) => {
    const r = s.getBoundingClientRect();
    return Math.round(((evt.clientX - r.left) / r.width) * W / (W - padR) * (n - 1));
  };
  hit.addEventListener("pointermove", (e) => showAt(toIndex(e), e));
  hit.addEventListener("pointerdown", (e) => showAt(toIndex(e), e));
  const hide = () => { cross.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); tip.hide(); };
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("blur", hide);
  hit.addEventListener("focus", () => showAt(focusI));
  hit.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") { showAt(focusI - 1); e.preventDefault(); }
    if (e.key === "ArrowRight") { showAt(focusI + 1); e.preventDefault(); }
  });
  host.append(s);
}

// ---------------------------------------------------------------- søyler med verktøytips per søyle
export function bars(host, { values, labels, height = 110, color = "var(--accent)", fmt, tip, title }) {
  host.replaceChildren();
  const W = Math.max(host.clientWidth, 240), H = height, padB = 18;
  const vals = values.map((v) => (v == null ? null : v));
  const hi = Math.max(...vals.filter((v) => v != null), 0) || 1;
  const n = vals.length, gap = 2, bw = (W - gap * (n - 1)) / n;
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": title });
  vals.forEach((v, i) => {
    const h = v == null ? 0 : Math.max(2, (v / hi) * (H - padB - 6));
    const bx = i * (bw + gap);
    const g = svg("g", { tabindex: 0, style: "cursor:default;outline:none" });
    g.append(svg("rect", { x: bx - gap / 2, y: 0, width: bw + gap, height: H, fill: "transparent" }));
    const r = svg("rect", { x: bx, y: H - padB - h, width: Math.max(bw, 1), height: h, rx: Math.min(4, bw / 2),
      fill: v == null ? "var(--line)" : color, opacity: 0.9 });
    g.append(r);
    const show = (e) => { r.setAttribute("opacity", 1); tip.show(e.clientX ? e : centerOf(r), [{ value: v == null ? "–" : fmt(v), label: labels[i] }]); };
    g.addEventListener("pointermove", show);
    g.addEventListener("focus", show);
    const hide = () => { r.setAttribute("opacity", 0.9); tip.hide(); };
    g.addEventListener("pointerleave", hide);
    g.addEventListener("blur", hide);
    s.append(g);
  });
  [0, Math.floor(n / 2), n - 1].forEach((i, k) => {
    s.append(text(i * (bw + gap) + (k === 0 ? 0 : k === 2 ? bw : bw / 2), H - 4, labels[i],
      { "text-anchor": k === 0 ? "start" : k === 2 ? "end" : "middle", fill: "var(--muted)", "font-size": 10.5 }));
  });
  host.append(s);
}

function centerOf(el) {
  const r = el.getBoundingClientRect();
  return { clientX: r.left + r.width / 2, clientY: r.top };
}

// ---------------------------------------------------------------- ett felles verktøytips
export function makeTip(el) {
  return {
    show(evt, rows, head) {
      el.replaceChildren();
      if (head) el.append(Object.assign(document.createElement("div"), { className: "td", textContent: head }));
      for (const r of rows) {
        el.append(Object.assign(document.createElement("div"), { className: "tv num", textContent: r.value }));
        const l = Object.assign(document.createElement("div"), { className: "tl" });
        if (r.color) { const i = document.createElement("i"); i.style.borderColor = r.color; if (r.dash) i.className = "dash"; l.append(i); }
        l.append(document.createTextNode(r.label));
        el.append(l);
      }
      el.hidden = false;
      const w = el.offsetWidth, h = el.offsetHeight;
      let left = evt.clientX + 14, top = evt.clientY - h - 12;
      if (left + w > innerWidth - 8) left = evt.clientX - w - 14;
      if (left < 8) left = 8;
      if (top < 8) top = evt.clientY + 18;
      el.style.left = `${left}px`;
      el.style.top = `${top}px`;
    },
    hide() { el.hidden = true; },
  };
}
