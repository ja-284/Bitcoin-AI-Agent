// Every page. Each takes the state from data.js and returns HTML; `after` hooks attach the chart and the controls.
import { fmt, cls, icon, esc, sigChip, toast, confirmDialog } from "./ui.js";
import { mountChart, sparkline } from "./chart.js";
import { PERIODS } from "./data.js";

const changeChip = (c, label) =>
  c == null ? `<span class="chip">${label}: no data</span>`
    : `<span class="chip ${cls(c.abs)}">${label} ${fmt.pct(c.rel)} · ${fmt.nokSigned(c.abs)}</span>`;

const honest = `<div class="banner honest">${icon("info")}<div>The BUY/HOLD/SELL signal has <strong>no demonstrated
  predictive value</strong> yet. The system trades it with strict limits while research continues. Past results are not
  a forecast.</div></div>`;

const hourResult = (v) => `<span class="num ${cls(v)}">${v === 0 ? "±0" : fmt.nokSigned(v)}</span>`;

// ---------------------------------------------------------------- Home
export function home(s) {
  const p = s.portfolio, a = s.account, d = s.lastDecision;
  const btcShare = p.equity ? p.btc_value / p.equity : 0;
  const week = s.window(168).equity;
  const status = a.mode === "live" ? `<span class="chip gain"><span class="dot"></span>Trading automatically</span>`
    : a.mode === "paused" ? `<span class="chip warn">${icon("pause")}Paused by you</span>`
    : `<span class="chip loss">${icon("alert")}Halted: ${esc(a.halted || "")}</span>`;
  return {
    html: `${honest}
    <div class="grid g-3">
      <section class="card span-2">
        <div class="card-h"><h2 class="card-t">Portfolio value</h2>${status}</div>
        <div class="hero-value num">${fmt.nok(p.equity)}</div>
        <div class="hero-sub">${changeChip(s.change["24h"], "24h")}${changeChip(s.change["7d"], "7d")}
          <span class="chip ${cls(s.sinceDeposit.abs)}">Since deposit ${fmt.pct(s.sinceDeposit.rel)}</span></div>
        <div style="margin-top:18px">${sparkline(week)}</div>
        <div class="card-h" style="margin:6px 0 0"><span class="faint" style="font-size:12.5px">Last 7 days</span>
          <a class="card-link" href="#/portfolio">Open chart →</a></div>
      </section>
      <section class="card">
        <div class="card-h"><h2 class="card-t">Position</h2><span class="faint num" style="font-size:12.5px">BTC ${fmt.nok(p.price, 0)}</span></div>
        <div class="split" aria-label="BTC share of the portfolio"><i style="width:${(btcShare * 100).toFixed(1)}%;background:var(--btc)"></i>
          <i style="width:${(100 - btcShare * 100).toFixed(1)}%;background:var(--accent)"></i></div>
        <dl class="kv" style="margin-top:16px">
          <dt><span class="dot" style="display:inline-block;color:var(--btc);margin-right:8px"></span>Bitcoin</dt><dd class="num">${fmt.nok(p.btc_value)}</dd>
          <dt><span class="dot" style="display:inline-block;color:var(--accent);margin-right:8px"></span>Cash</dt><dd class="num">${fmt.nok(p.cash)}</dd>
          <dt>Allocated cap</dt><dd class="num">${fmt.nok(a.allocation_cap)}</dd>
          <dt>Fees paid</dt><dd class="num">${fmt.nok(p.fees_paid)}</dd>
        </dl>
      </section>
    </div>
    <div class="grid g-3" style="margin-top:var(--gap)">
      <section class="card">
        <div class="card-h"><h2 class="card-t">Latest decision</h2>${sigChip(d.action)}</div>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px">${sigChip(d.signal)}
          <span class="muted" style="font-size:13.5px">signal for ${fmt.dateTime(new Date(d.as_of))}</span></div>
        <p style="margin:0 0 12px;font-size:14px">${esc(d.reasons[d.reasons.length - 1] || "")}</p>
        <a class="card-link" href="#/decision/${encodeURIComponent(d.as_of)}">Why this decision →</a>
      </section>
      <section class="card">
        <div class="card-h"><h2 class="card-t">Next run</h2><span class="chip">${icon("pulse")}hourly</span></div>
        <div class="stat-value num">${fmt.time(new Date(s.system.next_run))}</div>
        <div class="muted" style="font-size:13.5px">Last run ${fmt.dateTime(new Date(s.system.last_run))}</div>
        <dl class="kv" style="margin-top:14px"><dt>Runs, 7 days</dt><dd class="num">${s.system.runs_7d}</dd>
          <dt>Missed hours, 7 days</dt><dd class="num">${s.system.missing_7d}</dd></dl>
      </section>
      <section class="card">
        <div class="card-h"><h2 class="card-t">Against buy-and-hold</h2><a class="card-link" href="#/risk">Risk →</a></div>
        <div class="stat-value num ${cls(s.vsBuyHold)}">${fmt.nokSigned(s.vsBuyHold)}</div>
        <div class="muted" style="font-size:13.5px">Buy-and-hold would be ${fmt.nok(p.buy_hold)}</div>
        <dl class="kv" style="margin-top:14px"><dt>Drawdown from peak</dt><dd class="num">${fmt.pctPlain(p.drawdown, 1)}</dd>
          <dt>Trades so far</dt><dd class="num">${p.trades}</dd></dl>
      </section>
    </div>
    ${s.events.length ? `<section class="card" style="margin-top:var(--gap)"><div class="card-h"><h2 class="card-t">Recent events</h2></div>
      <div class="list">${s.events.slice(-4).reverse().map((e) => `<div class="check"><span class="ic ${e.kind === "resumed" ? "ok" : "no"}">${icon(e.kind === "resumed" ? "play" : "pause")}</span>
      <div><div>${esc(e.text)}</div><div class="faint" style="font-size:12.5px">${fmt.dateTime(new Date(e.t))}</div></div></div>`).join("")}</div></section>` : ""}`,
  };
}

// ---------------------------------------------------------------- Portfolio
export function portfolio(s) {
  let period = "7d", bench = true;
  const statBlock = (hours) => {
    const w = s.window(hours);
    const first = w.equity[0], last = w.equity[w.equity.length - 1];
    const bFirst = w.bench[0], bLast = w.bench[w.bench.length - 1];
    const fees = w.trades.reduce((a, t) => a + t.fee, 0);
    return `<div class="grid g-4 keep2">
      <div><div class="stat-label">Change</div><div class="stat-value num ${cls(last - first)}">${fmt.pct(last / first - 1)}</div><div class="faint num" style="font-size:12.5px">${fmt.nokSigned(last - first)}</div></div>
      <div><div class="stat-label">Buy-and-hold</div><div class="stat-value num ${cls(bLast - bFirst)}">${fmt.pct(bLast / bFirst - 1)}</div><div class="faint num" style="font-size:12.5px">${fmt.nokSigned(bLast - bFirst)}</div></div>
      <div><div class="stat-label">Trades</div><div class="stat-value num">${w.trades.length}</div><div class="faint" style="font-size:12.5px">in this period</div></div>
      <div><div class="stat-label">Fees</div><div class="stat-value num">${fmt.nok(fees)}</div><div class="faint" style="font-size:12.5px">in this period</div></div></div>`;
  };
  return {
    html: `${honest}<section class="card">
      <div class="card-h" style="flex-wrap:wrap"><div><div class="stat-label">Portfolio value</div>
        <div class="hero-value num">${fmt.nok(s.portfolio.equity)}</div></div>
        <div class="seg" role="group" aria-label="Chart period" id="periods">${PERIODS.map(([k]) => `<button data-p="${k}" class="${k === period ? "on" : ""}">${k}</button>`).join("")}</div></div>
      <div id="chart"></div>
      <div class="chart-legend"><span><i style="background:var(--chart-line)"></i>Your portfolio</span>
        <label style="cursor:pointer"><input type="checkbox" id="bench" checked style="accent-color:var(--accent)"> <i style="background:var(--chart-bench)"></i>Buy-and-hold from the period's start</label>
        <span><span class="gain">▲</span> buy <span class="loss">▼</span> sell (periods up to 1m)</span></div>
      <div id="pstats" style="margin-top:20px"></div></section>
    <div class="grid g-2" style="margin-top:var(--gap)">
      <section class="card"><div class="card-h"><h2 class="card-t">All time</h2></div><dl class="kv">
        <dt>Deposited (allocated)</dt><dd class="num">${fmt.nok(s.account.deposited)}</dd>
        <dt>Value now</dt><dd class="num">${fmt.nok(s.portfolio.equity)}</dd>
        <dt>Result</dt><dd class="num ${cls(s.sinceDeposit.abs)}">${fmt.nokSigned(s.sinceDeposit.abs)} (${fmt.pct(s.sinceDeposit.rel)})</dd>
        <dt>Buy-and-hold instead</dt><dd class="num">${fmt.nok(s.portfolio.buy_hold)}</dd>
        <dt>Fees paid</dt><dd class="num">${fmt.nok(s.portfolio.fees_paid)}</dd>
        <dt>Peak value</dt><dd class="num">${fmt.nok(s.portfolio.peak)}</dd></dl></section>
      <section class="card"><div class="card-h"><h2 class="card-t">Strategy</h2><span class="chip accent">${esc(s.account.strategy_version)}</span></div>
        <p class="muted" style="margin:0 0 12px;font-size:14px">BUY holds up to the cap in Bitcoin, sized down in volatile hours;
        SELL holds cash; HOLD keeps the position. Small changes, quick reversals and more than ${s.limits.max_trades_24h} trades a day
        are refused, because every trade costs a fee.</p><a class="card-link" href="#/signals">What the inputs are worth →</a></section></div>`,
    after(root) {
      let unmount = null;
      const render = () => {
        const hours = PERIODS.find(([k]) => k === period)[1];
        unmount?.();
        unmount = mountChart(root.querySelector("#chart"), s.window(hours), { hours, showBench: bench });
        root.querySelector("#pstats").innerHTML = statBlock(hours);
      };
      root.querySelector("#periods").addEventListener("click", (e) => {
        const b = e.target.closest("button[data-p]");
        if (!b) return;
        period = b.dataset.p;
        root.querySelectorAll("#periods button").forEach((x) => x.classList.toggle("on", x === b));
        render();
      });
      root.querySelector("#bench").addEventListener("change", (e) => { bench = e.target.checked; render(); });
      render();
      return () => unmount?.();
    },
  };
}

// ---------------------------------------------------------------- Activity
export function activity(s) {
  let filter = "all";
  const rows = () => {
    const list = [...s.activity].reverse().filter((r) =>
      filter === "all" ? true : filter === "trades" ? r.action !== "NONE" : filter === "none" ? r.action === "NONE" : r.action === filter);
    let day = "", out = "";
    for (const r of list.slice(0, 400)) {
      const d = new Date(r.as_of), k = fmt.dayKey(d);
      if (k !== day) { day = k; out += `<div class="day">${fmt.day(d)}</div>`; }
      const detail = s.decisionsByHour.has(r.as_of);
      out += `<div class="row ${detail ? "link" : ""}" ${detail ? `data-h="${esc(r.as_of)}" tabindex="0"` : ""}>
        <span class="num muted">${fmt.hourLabel(d)}</span>${sigChip(r.signal)}<span>${sigChip(r.action)}</span>
        <span class="hide-m num faint">${fmt.nok(r.equity)}</span>${hourResult(r.hour_change)}</div>`;
    }
    return out || `<p class="muted">Nothing in this filter.</p>`;
  };
  return {
    html: `<section class="card"><div class="card-h" style="flex-wrap:wrap">
      <div class="seg" id="filt">${[["all", "All hours"], ["trades", "Trades"], ["BUY", "Buys"], ["SELL", "Sells"], ["none", "No trade"]]
        .map(([k, l]) => `<button data-f="${k}" class="${k === filter ? "on" : ""}">${l}</button>`).join("")}</div>
      <button class="btn" id="csv">${icon("download")}Export trades (CSV)</button></div>
      <p class="faint" style="font-size:12.5px;margin:0 0 6px">Each hour: the signal, what the system did, and how the portfolio value changed that hour.
      Detailed reasons are kept for the last 14 days in this demo.</p>
      <div class="list" id="rows">${rows()}</div></section>`,
    after(root) {
      root.querySelector("#filt").addEventListener("click", (e) => {
        const b = e.target.closest("button[data-f]");
        if (!b) return;
        filter = b.dataset.f;
        root.querySelectorAll("#filt button").forEach((x) => x.classList.toggle("on", x === b));
        root.querySelector("#rows").innerHTML = rows();
      });
      const open = (e) => { const r = e.target.closest("[data-h]"); if (r) location.hash = `#/decision/${encodeURIComponent(r.dataset.h)}`; };
      root.querySelector("#rows").addEventListener("click", open);
      root.querySelector("#rows").addEventListener("keydown", (e) => { if (e.key === "Enter") open(e); });
      root.querySelector("#csv").addEventListener("click", () => {
        const head = "time_utc,side,btc_quantity,price_nok,amount_nok,fee_nok\n";
        const body = s.trades.map((t) => [t.t, t.side, t.qty, t.price, t.amount, t.fee].join(",")).join("\n");
        const url = URL.createObjectURL(new Blob([head + body + "\n"], { type: "text/csv" }));
        const a = Object.assign(document.createElement("a"), { href: url, download: s.fictional ? "trades-demo.csv" : "trades.csv" });
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
    },
  };
}

// ---------------------------------------------------------------- Decision detail
export function decision(s, asOf) {
  const d = s.decisionsByHour.get(asOf);
  if (!d) return { html: `<section class="card"><p>No detailed record for this hour (the demo keeps 14 days).</p><a class="card-link" href="#/activity">← Activity</a></section>` };
  const f = d.factors;
  const bar = (label, v, note, disabled = false) => `<div class="field"><div class="field-h"><label>${label}</label>
    <span class="num ${disabled ? "faint" : ""}">${disabled ? "disabled" : fmt.pctPlain(v)}</span></div>
    <div class="meter ${disabled ? "" : v < 1 ? "warn" : "gain"}"><i style="width:${(disabled ? 0 : v * 100).toFixed(0)}%"></i></div><p>${esc(note)}</p></div>`;
  const cats = Object.entries(d.category_scores).map(([k, v]) => `<div class="field"><div class="field-h"><label style="text-transform:capitalize">${k.replace("_", " ")}</label>
    <span class="num ${cls(v)}">${fmt.num(v, 2)}</span></div><div class="meter ${v >= 0 ? "gain" : "loss"}"><i style="width:${Math.abs(v) * 100}%"></i></div></div>`).join("");
  return {
    html: `<a class="card-link" href="#/activity" style="display:inline-flex;align-items:center;gap:6px;margin-bottom:12px">← Activity</a>
    <div class="grid g-3">
      <section class="card span-2"><div class="card-h"><h2 class="card-t">${fmt.dateTime(new Date(d.as_of))} · decided ${fmt.time(new Date(d.decided_at))}</h2>
        <div style="display:flex;gap:6px">${sigChip(d.signal)}${sigChip(d.action)}</div></div>
        <div class="grid g-3 keep2">
          <div><div class="stat-label">Held before</div><div class="stat-value num">${fmt.nok(d.exposure_before)}</div></div>
          <div><div class="stat-label">Target</div><div class="stat-value num">${fmt.nok(d.target)}</div></div>
          <div><div class="stat-label">This hour</div><div class="stat-value">${hourResult(d.hour_change)}</div></div></div>
        <h3 class="card-t" style="margin:20px 0 6px">Why</h3>
        <ul style="margin:0;padding-left:18px">${d.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
        <h3 class="card-t" style="margin:20px 0 6px">Explanation</h3><p style="margin:0" class="muted">${esc(d.explanation)}</p></section>
      <section class="card"><div class="card-h"><h2 class="card-t">Order</h2></div>${d.fill ? `<dl class="kv">
        <dt>Side</dt><dd>${sigChip(d.fill.side)}</dd><dt>Quantity</dt><dd class="num">${fmt.btc(d.fill.qty)}</dd>
        <dt>Price</dt><dd class="num">${fmt.nok(d.fill.price, 0)}</dd><dt>Amount</dt><dd class="num">${fmt.nok(d.fill.amount)}</dd>
        <dt>Fee</dt><dd class="num">${fmt.nok(d.fill.fee)}</dd></dl>` : `<p class="muted" style="margin:0">No order this hour.</p>`}
        <h3 class="card-t" style="margin:20px 0 6px">Inputs</h3><dl class="kv">
        <dt>Price</dt><dd class="num">${fmt.nok(d.price, 0)}</dd><dt>Signal score</dt><dd class="num">${fmt.num(d.overall_score, 3)}</dd>
        <dt>P(move &gt; 0,25 %)</dt><dd class="num">${fmt.pctPlain(d.p_large, 1)}</dd><dt>24 h volatility</dt><dd class="num">${fmt.pctPlain(d.rv_24, 2)}</dd>
        <dt>Confidence (not used)</dt><dd class="num faint">${fmt.pctPlain(d.confidence)}</dd></dl></section>
    </div>
    <div class="grid g-3" style="margin-top:var(--gap)">
      <section class="card"><div class="card-h"><h2 class="card-t">Sizing</h2><span class="chip">size ${fmt.pctPlain(f.size)}</span></div>
        ${bar("Volatility", f.f_vol, f.notes.f_vol)}${bar("Move size", f.f_move, f.notes.f_move)}${bar("Confidence", 1, f.notes.f_conf, true)}</section>
      <section class="card"><div class="card-h"><h2 class="card-t">Safety checks</h2></div>
        ${d.checks.map((c) => `<div class="check"><span class="ic ${c.passed ? "ok" : "no"}">${icon(c.passed ? "check" : "x")}</span>
        <div><div style="font-weight:550">${esc(c.name)}</div><div class="faint" style="font-size:12.5px">${esc(c.detail)}</div></div></div>`).join("")}</section>
      <section class="card"><div class="card-h"><h2 class="card-t">Signal categories</h2></div>${cats}</section>
    </div>`,
  };
}

// ---------------------------------------------------------------- Signals & research
export function signals(s) {
  const r = s.research;
  return {
    html: `${honest}<section class="card"><div class="card-h"><h2 class="card-t">What drives each decision, and what it is worth</h2></div>
      <div class="list">${r.inputs.map((i) => `<div class="field"><div class="field-h"><label>${esc(i.name)}</label>
        <span class="chip ${/no demonstrated|uninformative/.test(i.status) ? "loss" : /blind/.test(i.status) ? "warn" : "gain"}">${esc(i.status)}</span></div>
        <p>${esc(i.version)} · used for: ${esc(i.used_for)}</p></div>`).join("")}</div></section>
    <section class="card" style="margin-top:var(--gap)"><div class="card-h"><h2 class="card-t">Registered research checkpoints</h2></div>
      ${r.checkpoints.map((c) => `<div class="field"><div class="field-h"><label>${esc(c.name)}</label><span class="num muted">${fmt.num(c.done)} / ${fmt.num(c.of)} h</span></div>
      <div class="meter"><i style="width:${Math.min(100, (c.done / c.of) * 100).toFixed(1)}%"></i></div><p>Expected: ${esc(c.eta)}</p></div>`).join("")}
      <p class="faint" style="font-size:12.5px;margin:12px 0 0">A checkpoint's verdict decides which inputs the strategy may use. A better model
      reaches this app only after it passes its registered test and you approve the switch.</p></section>`,
  };
}

// ---------------------------------------------------------------- Risk
export function risk(s) {
  const p = s.portfolio, L = s.limits, a = s.account;
  const recent = s.trades.filter((t) => s.now - new Date(t.t) < 24 * 3600e3).length;
  const day = s.change["24h"]?.rel ?? 0;
  const meter = (label, value, limit, text, kind) => `<div class="field"><div class="field-h"><label>${label}</label><span class="num muted">${text}</span></div>
    <div class="meter ${kind}"><i style="width:${Math.min(100, (value / limit) * 100).toFixed(1)}%"></i></div></div>`;
  return {
    html: `<div class="grid g-2"><section class="card"><div class="card-h"><h2 class="card-t">Limits now</h2>
        <span class="chip ${a.mode === "live" ? "gain" : "loss"}">${a.mode === "live" ? "within limits" : "halted"}</span></div>
      ${meter("Exposure vs cap", p.btc_value, a.allocation_cap, `${fmt.nok(p.btc_value)} of ${fmt.nok(a.allocation_cap)}`, "")}
      ${meter("Drawdown (risk stop)", p.drawdown, L.max_drawdown, `${fmt.pctPlain(p.drawdown, 1)} of ${fmt.pctPlain(L.max_drawdown)}`, p.drawdown > L.max_drawdown * 0.7 ? "loss" : "warn")}
      ${meter("24 h loss (daily stop)", Math.max(0, -day), L.daily_loss_limit, `${fmt.pct(day)} vs −${fmt.pctPlain(L.daily_loss_limit)}`, "warn")}
      ${meter("Trades in 24 h", recent, L.max_trades_24h, `${recent} of ${L.max_trades_24h}`, "")}</section>
      <section class="card"><div class="card-h"><h2 class="card-t">The rules</h2><span class="chip accent">${esc(a.strategy_version)}</span></div><dl class="kv">
        <dt>Hard cap in code</dt><dd class="num">${fmt.nok(a.hard_max, 0)}</dd>
        <dt>Your cap</dt><dd class="num">${fmt.nok(a.allocation_cap, 0)}</dd>
        <dt>Resize only if the change exceeds</dt><dd class="num">${fmt.pctPlain(L.band_fraction)} of the cap</dd>
        <dt>No reversal within</dt><dd class="num">${L.min_hold_hours} h</dd>
        <dt>Max trades per 24 h</dt><dd class="num">${L.max_trades_24h}</dd>
        <dt>Daily loss stop</dt><dd class="num">−${fmt.pctPlain(L.daily_loss_limit)}</dd>
        <dt>Drawdown stop</dt><dd class="num">−${fmt.pctPlain(L.max_drawdown)}</dd>
        <dt>Full size up to hourly volatility</dt><dd class="num">${fmt.pctPlain(L.target_hourly_vol, 1)}</dd>
        <dt>Smallest order</dt><dd class="num">${fmt.nok(L.min_order_value, 0)}</dd></dl>
        <p class="faint" style="font-size:12.5px;margin:12px 0 0">A stop sells everything and halts trading until you resume it in Settings.</p></section></div>
    <section class="card" style="margin-top:var(--gap)"><div class="card-h"><h2 class="card-t">Stops and resumes</h2></div>
      ${s.events.length ? s.events.slice().reverse().map((e) => `<div class="check"><span class="ic ${e.kind === "resumed" ? "ok" : "no"}">${icon(e.kind === "resumed" ? "play" : "pause")}</span>
      <div><div>${esc(e.text)}</div><div class="faint" style="font-size:12.5px">${fmt.dateTime(new Date(e.t))}</div></div></div>`).join("") : `<p class="muted">None yet.</p>`}</section>`,
  };
}

// ---------------------------------------------------------------- Funding
export function funding(s) {
  const a = s.account, b = a.exchange_balance;
  return {
    html: `<div class="grid g-2"><section class="card"><div class="card-h"><h2 class="card-t">Exchange account</h2>
        <span class="chip ${s.fictional ? "warn" : "gain"}">${esc(a.venue)}</span></div><dl class="kv">
        <dt>Cash on the exchange</dt><dd class="num">${fmt.nok(b.cash)}</dd><dt>Bitcoin on the exchange</dt><dd class="num">${fmt.btc(b.btc)}</dd>
        <dt>Allocated to the system</dt><dd class="num">${fmt.nok(a.allocation_cap)}</dd><dt>Not allocated</dt><dd class="num">${fmt.nok(a.unallocated)}</dd>
        <dt>Fee per trade</dt><dd class="num">${fmt.pctPlain(a.fee_rate, 2)}</dd></dl>
        <p class="faint" style="font-size:12.5px;margin:14px 0 0">The money stays on your own exchange account. The system can only trade within your cap:
        its key has no withdrawal right (Firi does not allow withdrawals through its API at all).</p></section>
      <section class="card"><div class="card-h"><h2 class="card-t">Add money</h2></div><ol class="steps">
        <li>Open the exchange's app and deposit (card or bank transfer). The exchange's own deposit fee applies.</li>
        <li>Raise your cap in <a class="card-link" href="#/settings">Settings</a> if you want the system to use more (never above ${fmt.nok(a.hard_max, 0)}).</li>
        <li>The next hourly run picks the new cap up automatically.</li></ol>
        <h3 class="card-t" style="margin:6px 0 10px">Take money out</h3><ol class="steps">
        <li>Lower the cap, or pause trading in Settings.</li><li>Withdraw in the exchange's app. Only you can do this.</li></ol></section></div>`,
  };
}

// ---------------------------------------------------------------- Settings
export function settings(s, ctx) {
  const a = s.account;
  const local = { cap: a.allocation_cap, paused: a.mode === "paused" };
  const theme = ctx.getTheme();
  return {
    html: `<div class="grid g-2"><section class="card"><div class="card-h"><h2 class="card-t">Capital</h2></div>
        <div class="field"><div class="field-h"><label for="cap">Allocation cap</label><span class="num" id="capv">${fmt.nok(local.cap, 0)}</span></div>
          <input id="cap" type="range" min="50" max="${a.hard_max}" step="10" value="${local.cap}">
          <p>The most the system may hold in Bitcoin and cash together. It never goes above ${fmt.nok(a.hard_max, 0)}, the cap written into the code.</p></div>
        <div class="field"><div class="field-h"><label>Risk profile</label><span class="chip accent">${esc(a.strategy_version)} · standard</span></div>
          <p>The limits are listed on the Risk page. Other profiles come as new, tested strategy versions, never as silent changes.</p></div>
        <button class="btn primary" id="save">Save changes</button></section>
      <section class="card"><div class="card-h"><h2 class="card-t">Trading</h2></div>
        <div class="field"><div class="field-h"><label for="pause">Pause automatic trading</label>
          <label class="switch"><input type="checkbox" id="pause" ${local.paused ? "checked" : ""}><span></span></label></div>
          <p>While paused the system still analyses every hour, but places no order.</p></div>
        <div class="field"><div class="field-h"><label>Sell everything now</label><button class="btn danger" id="flatten">Sell all</button></div>
          <p>Sells the system's Bitcoin at the next run and pauses trading.</p></div>
        <div class="field"><div class="field-h"><label>Resume after a stop</label><button class="btn" id="resume" ${a.halted ? "" : "disabled"}>${icon("play")}Resume</button></div>
          <p>${a.halted ? `Halted: ${esc(a.halted)}.` : "Nothing is halted."}</p></div></section>
      <section class="card"><div class="card-h"><h2 class="card-t">Appearance</h2></div>
        <div class="field"><div class="field-h"><label>Theme</label><div class="seg" id="theme">${[["system", "System"], ["light", "Light"], ["dark", "Dark"]]
          .map(([k, l]) => `<button data-t="${k}" class="${theme === k ? "on" : ""}">${l}</button>`).join("")}</div></div></div></section>
      <section class="card"><div class="card-h"><h2 class="card-t">Notifications</h2><span class="chip">coming</span></div>
        ${["A trade was made", "Trading paused or halted", "A run failed or an hour was missed"].map((t) => `<div class="field"><div class="field-h"><label>${t}</label>
        <label class="switch"><input type="checkbox" disabled checked><span></span></label></div></div>`).join("")}
        <p class="faint" style="font-size:12.5px;margin:10px 0 0">Push notifications arrive with the installable app. Today the existing email alarms cover failures.</p></section></div>`,
    after(root) {
      const notSaved = () => toast(s.fictional ? "Demo: nothing is saved. Saving starts once the owner's settings path is live." : "Saved.");
      root.querySelector("#cap").addEventListener("input", (e) => { root.querySelector("#capv").textContent = fmt.nok(+e.target.value, 0); });
      root.querySelector("#save").addEventListener("click", notSaved);
      root.querySelector("#pause").addEventListener("change", async (e) => {
        const on = e.target.checked;
        if (!(await confirmDialog(on ? "Pause automatic trading?" : "Resume automatic trading?",
          on ? "No order is placed until you resume. The analysis keeps running." : "The next hourly run may place an order.", on ? "Pause" : "Resume"))) {
          e.target.checked = !on; return;
        }
        notSaved();
      });
      root.querySelector("#flatten").addEventListener("click", async () => {
        if (await confirmDialog("Sell everything?", "The system sells all of its Bitcoin at the next run and then pauses.", "Sell all", true)) notSaved();
      });
      root.querySelector("#resume").addEventListener("click", notSaved);
      root.querySelector("#theme").addEventListener("click", (e) => {
        const b = e.target.closest("button[data-t]");
        if (!b) return;
        ctx.setTheme(b.dataset.t);
        root.querySelectorAll("#theme button").forEach((x) => x.classList.toggle("on", x === b));
      });
    },
  };
}

// ---------------------------------------------------------------- System
export function system(s) {
  const y = s.system;
  return {
    html: `<div class="grid g-3"><section class="card"><div class="stat-label">Last run</div><div class="stat-value num">${fmt.time(new Date(y.last_run))}</div>
        <div class="faint" style="font-size:12.5px">${fmt.date(new Date(y.last_run))}</div></section>
      <section class="card"><div class="stat-label">Runs, last 7 days</div><div class="stat-value num">${y.runs_7d} <span class="faint" style="font-size:14px">of 168</span></div>
        <div class="faint" style="font-size:12.5px">${y.missing_7d} missed hours</div></section>
      <section class="card"><div class="stat-label">Heartbeat</div><div class="stat-value ${y.heartbeat === "ok" ? "gain" : "loss"}">${y.heartbeat === "ok" ? "Healthy" : "Attention"}</div>
        <div class="faint" style="font-size:12.5px">External dead-man's switch</div></section></div>
    <section class="card" style="margin-top:var(--gap)"><div class="card-h"><h2 class="card-t">Incidents</h2></div>
      ${y.incidents.map((i) => `<div class="check"><span class="ic no">${icon("alert")}</span><div><div>${esc(i.text)}</div>
      <div class="faint" style="font-size:12.5px">${fmt.dateTime(new Date(i.t))}</div></div></div>`).join("") || `<p class="muted">None.</p>`}</section>
    <section class="card" style="margin-top:var(--gap)"><div class="card-h"><h2 class="card-t">Versions</h2></div><dl class="kv">
      <dt>Execution strategy</dt><dd>${esc(s.account.strategy_version)}</dd><dt>Signal</dt><dd>scoring 0.2.0</dd>
      <dt>Move-size model</dt><dd>move_size_1h_v1 (frozen)</dd><dt>Data contract</dt><dd>${esc(s.schema)}</dd></dl></section>`,
  };
}

// ---------------------------------------------------------------- About
export function about() {
  return {
    html: `<section class="card"><div class="card-h"><h2 class="card-t">How it works</h2></div><ol class="steps">
      <li>Every hour the system collects Bitcoin prices and news, scores them and saves a BUY, HOLD or SELL signal with its reasons.</li>
      <li>A separate trading layer reads that saved result. It decides how much of your cap to hold in Bitcoin, checks every safety limit, and places at most one order on your exchange account.</li>
      <li>Every decision, including "no trade", is recorded with its inputs, so this app can show exactly why.</li>
      <li>Research keeps running in the background. A better model replaces the current inputs only after it passes a registered test and you approve it.</li></ol></section>
    <div class="grid g-2" style="margin-top:var(--gap)"><section class="card"><div class="card-h"><h2 class="card-t">The risks</h2></div>
      <ul style="margin:0;padding-left:18px" class="muted"><li>The signal has no demonstrated predictive value yet. Trading it can lose money.</li>
      <li>Every trade pays a fee, so frequent trading costs money even when prices do not move.</li>
      <li>Bitcoin can fall fast. The stops limit losses but cannot prevent them.</li><li>Exchanges, the internet or the system can fail. The system pauses on any doubt.</li></ul></section>
      <section class="card"><div class="card-h"><h2 class="card-t">Tax (Norway)</h2></div><p class="muted" style="margin:0">Each sale realises a gain or a loss that belongs in your tax return
      (Skatteetaten: virtuelle eiendeler). The Activity page exports every trade with NOK values. This is information, not tax advice.</p></section></div>`,
  };
}

// ---------------------------------------------------------------- More (mobile)
export function more() {
  const items = [["signals", "flask", "Signals & research"], ["funding", "wallet", "Funding"], ["system", "pulse", "System"], ["about", "info", "About"]];
  return { html: `<section class="card"><div class="nav">${items.map(([r, i, l]) => `<a href="#/${r}">${icon(i)}${l}</a>`).join("")}</div></section>` };
}
