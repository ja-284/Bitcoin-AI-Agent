// An exchange-style value chart in plain SVG: the portfolio line with a soft fill, the buy-and-hold benchmark
// dashed, trade markers, a crosshair with a tooltip. No library (NOK 0, nothing to download, nothing to trust).
import { fmt } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const PAD = { l: 8, r: 64, t: 16, b: 26 };

function downsample(times, values, bench, maxPts) {
  if (times.length <= maxPts) return { t: times, v: values, b: bench };
  const step = times.length / maxPts;
  const t = [], v = [], b = [];
  for (let i = 0; i < maxPts; i++) {
    const j = Math.min(times.length - 1, Math.round((i + 1) * step) - 1);
    t.push(times[j]); v.push(values[j]); b.push(bench[j]);
  }
  t[t.length - 1] = times[times.length - 1];
  v[v.length - 1] = values[values.length - 1];
  b[b.length - 1] = bench[bench.length - 1];
  return { t, v, b };
}

function niceTicks(lo, hi, count = 4) {
  const span = hi - lo || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
  return out;
}

function el(name, attrs = {}, parent) {
  const e = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

export function mountChart(host, win, { hours, showBench = true } = {}) {
  host.innerHTML = "";
  host.classList.add("chart-wrap");
  const svg = el("svg", { role: "img", "aria-label": "Portfolio value chart" }, host);
  const tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.hidden = true;
  host.appendChild(tip);

  const draw = () => {
    const W = host.clientWidth, H = host.clientHeight;
    if (!W || !H) return;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";
    const { t, v, b } = downsample(win.times, win.equity, win.bench, Math.max(60, Math.floor(W / 2)));
    if (t.length < 2) return;
    const all = showBench ? v.concat(b) : v;
    let lo = Math.min(...all), hi = Math.max(...all);
    const padY = (hi - lo) * 0.12 || hi * 0.02 || 1;
    lo -= padY; hi += padY;
    const x = (ms) => PAD.l + ((ms - t[0]) / (t[t.length - 1] - t[0])) * (W - PAD.l - PAD.r);
    const y = (val) => PAD.t + (1 - (val - lo) / (hi - lo)) * (H - PAD.t - PAD.b);

    const defs = el("defs", {}, svg);
    const grad = el("linearGradient", { id: "fill", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0%", "stop-color": "var(--chart-fill-top)" }, grad);
    el("stop", { offset: "100%", "stop-color": "var(--chart-fill-bottom)" }, grad);

    for (const tick of niceTicks(lo, hi)) {
      el("line", { x1: PAD.l, x2: W - PAD.r, y1: y(tick), y2: y(tick), stroke: "var(--chart-grid)" }, svg);
      const lab = el("text", { x: W - PAD.r + 10, y: y(tick) + 4, fill: "var(--text-3)", "font-size": 11 }, svg);
      lab.textContent = fmt.num(tick, hi - lo < 10 ? 1 : 0);
    }
    const nX = Math.max(2, Math.min(6, Math.floor(W / 120)));
    for (let i = 0; i < nX; i++) {
      const ms = t[0] + ((t[t.length - 1] - t[0]) * (i + 0.5)) / nX;
      const lab = el("text", { x: x(ms), y: H - 6, fill: "var(--text-3)", "font-size": 11, "text-anchor": "middle" }, svg);
      lab.textContent = hours <= 48 ? fmt.time(new Date(ms)) : fmt.day(new Date(ms)).replace(/^\w+,?\s/, "");
    }

    const line = t.map((ms, i) => `${i ? "L" : "M"}${x(ms).toFixed(1)},${y(v[i]).toFixed(1)}`).join("");
    el("path", { d: `${line}L${x(t[t.length - 1])},${H - PAD.b}L${x(t[0])},${H - PAD.b}Z`, fill: "url(#fill)" }, svg);
    if (showBench) {
      const bl = t.map((ms, i) => `${i ? "L" : "M"}${x(ms).toFixed(1)},${y(b[i]).toFixed(1)}`).join("");
      el("path", { d: bl, fill: "none", stroke: "var(--chart-bench)", "stroke-width": 1.4, "stroke-dasharray": "4 4" }, svg);
    }
    el("path", { d: line, fill: "none", stroke: "var(--chart-line)", "stroke-width": 2, "stroke-linejoin": "round" }, svg);

    if (hours <= 720) {
      for (const tr of win.trades) {
        const ms = new Date(tr.as_of).getTime();
        const i = win.times.findIndex((tt) => tt >= ms);
        if (i < 0) continue;
        const cx = x(win.times[i]), cy = y(win.equity[i]);
        const up = tr.side === "BUY";
        el("path", {
          d: up ? `M${cx},${cy + 7}l-4.5,7h9z` : `M${cx},${cy - 7}l-4.5,-7h9z`,
          fill: up ? "var(--gain)" : "var(--loss)", opacity: 0.9,
        }, svg);
      }
    }
    const lastX = x(t[t.length - 1]), lastY = y(v[v.length - 1]);
    el("circle", { cx: lastX, cy: lastY, r: 4, fill: "var(--chart-line)", stroke: "var(--surface)", "stroke-width": 2 }, svg);

    const cross = el("line", { y1: PAD.t, y2: H - PAD.b, stroke: "var(--border-strong)", "stroke-dasharray": "3 3", visibility: "hidden" }, svg);
    const dot = el("circle", { r: 4.5, fill: "var(--chart-line)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }, svg);
    const move = (clientX) => {
      const rect = svg.getBoundingClientRect();
      const px = clientX - rect.left;
      let i = 0, best = Infinity;
      for (let k = 0; k < t.length; k++) {
        const d = Math.abs(x(t[k]) - px);
        if (d < best) { best = d; i = k; }
      }
      cross.setAttribute("x1", x(t[i])); cross.setAttribute("x2", x(t[i])); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", x(t[i])); dot.setAttribute("cy", y(v[i])); dot.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.style.left = Math.min(Math.max(x(t[i]), 90), W - 90) + "px";
      tip.innerHTML = `<div class="faint">${fmt.dateTime(new Date(t[i]))}</div>
        <div class="num" style="font-weight:650">${fmt.nok(v[i])}</div>
        ${showBench ? `<div class="num faint">Buy-and-hold ${fmt.nok(b[i])}</div>` : ""}`;
    };
    const leave = () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); tip.hidden = true; };
    svg.onpointermove = (e) => move(e.clientX);
    svg.onpointerdown = (e) => move(e.clientX);
    svg.onpointerleave = leave;
  };

  draw();
  const ro = new ResizeObserver(draw);
  ro.observe(host);
  return () => ro.disconnect();
}

export function sparkline(values) {
  const W = 300, H = 56, n = values.length;
  const lo = Math.min(...values), hi = Math.max(...values);
  const pts = values.map((v, i) => `${((i / (n - 1)) * W).toFixed(1)},${(H - 4 - ((v - lo) / (hi - lo || 1)) * (H - 8)).toFixed(1)}`);
  const up = values[n - 1] >= values[0];
  const c = up ? "var(--gain)" : "var(--loss)";
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <polyline points="${pts.join(" ")}" fill="none" stroke="${c}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}
