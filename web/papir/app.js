// Papirhandel: oversikt over alle kontoene og én side per konto. Leser bare dokumentet fra data.js.
import { bars, donut, lineChart, makeTip, ring, spark } from "./charts.js";
import { loadDoc } from "./data.js";

const app = document.getElementById("app");
const tip = makeTip(document.getElementById("tip"));
const S = { doc: null, book: pref("book", "firi"), sort: "ret", fam: "ALLE", query: "", showAll: false, range: "alt", scroll: 0 };

const FAMILY_RULE = {
  A: "Følger modellens kjøp- og selgsignal.",
  B: "Eier bitcoin når trenden er opp, ellers kontanter.",
  C: "Kjøper over snittet og selger under, med en margin så den ikke hopper fram og tilbake.",
  D: "Modellens signal, men bare når trenden er opp.",
  E: "Eier bitcoin bare når markedet er rolig.",
  F: "Kjøper etter et kraftig fall og holder et fast antall dager.",
  G: "Kjøper når kursen når en ny topp, selger ved en ny bunn.",
  H: "En annen regel, med en stopp som selger hvis kursen faller for mye.",
  MS: "En annen regel, men mer eller mindre penger inne etter hvor store svingninger modellen venter.",
  BASE: "Sammenligning: kjøp og hold, eller bare kontanter.",
};
const REASON = { signal: "signal", stop_loss: "stopp", trailing_stop: "glidende stopp", time_stop: "tidsstopp", rebalance: "justering" };

// ---------------------------------------------------------------- små hjelpere
function pref(k, d) { try { return localStorage.getItem(`papir.${k}`) || d; } catch { return d; } }
function save(k, v) { try { localStorage.setItem(`papir.${k}`, v); } catch { /* privat modus: bare ikke husk */ } }

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

const nf2 = new Intl.NumberFormat("nb-NO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf1 = new Intl.NumberFormat("nb-NO", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat("nb-NO", { maximumFractionDigits: 0 });
const kr = (v) => (v == null ? "–" : `${nf2.format(v)} kr`);
const kr0 = (v) => (v == null ? "–" : `${nf0.format(v)} kr`);
const signed = (r, f = nf1) => (r == null ? "–" : `${r > 0 ? "+" : r < 0 ? "−" : ""}${f.format(Math.abs(r * 100))} %`);
const pctPlain = (r, f = nf0) => (r == null ? "–" : `${f.format(r * 100)} %`);
const EPS = 1e-9;

function pill(r) {
  const cls = r > EPS ? "up" : r < -EPS ? "down" : "flat";
  const arrow = r > EPS ? "▲" : r < -EPS ? "▼" : "•";
  return h("span", { class: `pill ${cls} num` }, `${arrow} ${signed(r)}`);
}
const dayDate = (d) => new Date(`${d}T00:00:00Z`);
const shortDate = (d, long) => dayDate(d).toLocaleDateString("nb-NO", { day: "numeric", month: "short", year: long ? "numeric" : undefined, timeZone: "UTC" });
const card = (title, sub, ...kids) => h("section", { class: "card" }, title ? h("h2", {}, title, sub ? h("span", { class: "sub" }, sub) : null) : null, ...kids);

// ---------------------------------------------------------------- tema
function applyTheme(t) {
  if (t === "light") document.documentElement.dataset.theme = "light";
  else delete document.documentElement.dataset.theme;
  document.querySelector('meta[name="theme-color"]').setAttribute("content", t === "light" ? "#f3f5fb" : "#0b0e17");
  document.getElementById("theme").textContent = t === "light" ? "☾" : "☀";
  document.getElementById("theme").setAttribute("aria-label", t === "light" ? "Bytt til mørkt" : "Bytt til lyst");
}
document.getElementById("theme").addEventListener("click", () => {
  const t = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  save("theme", t);
  applyTheme(t);
  render();
});
applyTheme(pref("theme", "dark"));

// ---------------------------------------------------------------- oversikten
function book() { return S.doc.books[S.book]; }
function byId() { return new Map(book().accounts.map((a) => [a.id, a])); }
const trendColor = (a) => (a.ret > EPS ? "var(--up)" : a.ret < -EPS ? "var(--down)" : "var(--flat)");

function accountRow(a, rank) {
  const meta = [S.doc.familyNames[a.family] || a.family];
  return h("a", { class: rank ? "row" : "row no-rank", href: `#/konto/${encodeURIComponent(a.id)}` },
    rank ? h("span", { class: "rank num" }, rank) : null,
    h("div", { style: "min-width:0" },
      h("div", { class: "name" }, a.name),
      h("div", { class: "meta" }, meta.join(" · "), a.in_btc ? h("span", { class: "tag" }, "₿ eier") : null,
        a.active ? null : h("span", { class: "tag" }, "venter"))),
    spark(a.values, { color: trendColor(a), width: 52 }),
    h("div", { class: "right" }, pill(a.ret), h("span", { class: "value num" }, kr(a.value))));
}

function seg() {
  const b = (key, label) => h("button", { "aria-pressed": String(S.book === key), onclick: () => { S.book = key; save("book", key); render(); } }, label);
  return h("div", { class: "seg", role: "group", "aria-label": "Hvilke priser" }, b("firi", "Firi-priser"), b("modell", "Modellpriser"));
}

function overview(after) {
  const doc = S.doc, bk = book(), sum = bk.summary, root = h("div", { class: "wrap" });
  if (doc.fictional) root.append(h("div", { class: "banner" }, "Demo med oppdiktede tall (2030). Ekte tall vises når siden kobles til."));
  root.append(seg());
  const days = doc.operation.days;
  const next = doc.readings.find((r) => !r.reached) || doc.readings[doc.readings.length - 1];
  const left = Math.max(next.days - days, 0);
  root.append(card(null, null, h("div", { class: "hero" },
    ring({ value: days / next.days, size: 118, stroke: 11, center: `${days}`, sub: `av ${next.days} dager`, label: `${days} av ${next.days} dager` }),
    h("div", { class: "big" },
      h("b", {}, left ? `${left} dager til avlesning` : "Avlesning nådd"),
      `Avlesning etter ${next.days} dager (${shortDate(next.date, true)}).`, h("br"),
      doc.operation.errors || doc.operation.missing_days.length
        ? h("span", { class: "warn" }, `⚠ ${doc.operation.missing_days.length} manglende dager, ${doc.operation.errors} feil`)
        : h("span", { class: "ok" }, "✓ Går som den skal")))));
  if (!sum) {
    root.append(card(null, null, h("p", { class: "empty" }, "Ingen papirdager ennå. Den første dagen behandles rett etter midnatt (UTC).")));
    root.append(foot());
    return root;
  }
  const ranked = bk.accounts.filter((a) => a.family !== "BASE");
  // kontoene nå
  const parts = [
    { label: "I pluss", value: sum.in_plus, color: "var(--up)" },
    { label: "Uendret", value: sum.flat, color: "var(--flat)" },
    { label: "I minus", value: sum.in_minus, color: "var(--down)" },
  ];
  root.append(card("Kontoene nå", `${sum.accounts} stk`,
    h("div", { class: "split" },
      donut({ parts, center: `${sum.accounts}`, sub: "kontoer", tip }),
      h("div", { class: "legend" }, parts.map((p) => h("div", { class: "item" },
        h("span", { class: "key", style: `background:${p.color}` }), p.label, h("span", { class: "val num" }, p.value))))),
    h("div", { class: "rings", style: "margin-top:16px" },
      ringBox(sum.in_btc / sum.accounts, `${sum.in_btc}`, "eier bitcoin nå", "var(--bh)"),
      ringBox(sum.beat_buy_hold / ranked.length, `${sum.beat_buy_hold}`, "slår kjøp og hold", "var(--accent)"),
      goalRing(sum, ranked.length))));
  // bitcoin
  const firi = S.book === "firi";
  const px = firi ? doc.btc.firi_mid : doc.btc.close;
  const real = px.filter((v) => v != null);
  const chg = real.length > 1 ? real[real.length - 1] / real[0] - 1 : null;
  const host = h("div", { class: "chart" });
  root.append(card("Bitcoin", firi ? "Firi, midtkurs i kr" : "Binance-sluttkurs, USD",
    h("div", { class: "acct-value" }, h("span", { class: "v num", style: "font-size:26px" }, firi ? kr0(real[real.length - 1]) : `${nf0.format(real[real.length - 1])} $`),
      chg == null ? null : pill(chg), h("span", { class: "value", style: "color:var(--muted);font-size:12px" }, "siden første papirdag")),
    host));
  after.push(() => lineChart(host, { dates: doc.days, series: [{ name: "Bitcoin", values: px, color: "var(--bh)", area: true }], height: 130,
    fmtY: (v) => (firi ? kr0(v) : `${nf0.format(v)} $`), fmtDate: shortDate, tip }));
  // best og svakest
  const ids = byId();
  root.append(card("Best akkurat nå", null, h("div", { class: "list" }, sum.best.map((id, i) => accountRow(ids.get(id), i + 1)))));
  root.append(card("Svakest akkurat nå", null, h("div", { class: "list" }, sum.worst.map((id, i) => accountRow(ids.get(id), ranked.length - i)))));
  // kjøp og hold og kontanter
  root.append(card("Å slå", "sammenligning", h("div", { class: "list" },
    ["BASE_buy_and_hold", "BASE_cash"].map((id) => ids.get(id)).filter(Boolean).map((a) => accountRow(a)))));
  // grupper
  const maxAbs = Math.max(...sum.families.map((f) => Math.abs(f.mean_ret)), 1e-6);
  root.append(card("Grupper", "snitt per gruppe", sum.families.filter((f) => f.family !== "BASE").map((f) => {
    const w = (Math.abs(f.mean_ret) / maxAbs) * 50;
    const style = f.mean_ret >= 0 ? `left:50%;width:${w}%;background:var(--up)` : `right:50%;width:${w}%;background:var(--down)`;
    return h("div", { class: "fam" },
      h("div", {}, f.name, h("span", { class: "n" }, f.n)),
      h("div", { class: "bar", "aria-hidden": "true" }, h("span", { class: "zero" }), h("i", { style })),
      h("div", { class: `pct num ${f.mean_ret > EPS ? "ok" : f.mean_ret < -EPS ? "warn" : ""}` }, signed(f.mean_ret)));
  })));
  root.append(allAccounts());
  if (doc.market) root.append(market(doc.market, after));
  root.append(drift());
  root.append(foot());
  return root;
}

function ringBox(v, center, label, color) {
  return h("div", { class: "ring-wrap" }, ring({ value: v, size: 84, stroke: 8, color, center, label: `${center} ${label}` }), h("div", { class: "ring-label" }, label));
}

function goalRing(sum, n) {
  const ready = book().accounts.some((a) => a.no_loss_30);
  if (!ready) return h("div", { class: "ring-wrap" }, ring({ value: 0, size: 84, stroke: 8, center: "–", label: "målet: etter 30 dager" }), h("div", { class: "ring-label" }, "når målet (etter 30 d)"));
  return ringBox(sum.goal.no_loss_30 / n, `${sum.goal.no_loss_30}`, "når målet (30 d) så langt", "var(--up)");
}

function allAccounts() {
  const wrap = card("Alle kontoer", null);
  const list = h("div", { class: "list" });
  const sorters = { ret: (a, b) => b.ret - a.ret, name: (a, b) => a.name.localeCompare(b.name, "nb"), trades: (a, b) => b.trades - a.trades, dd: (a, b) => a.max_dd - b.max_dd };
  const draw = () => {
    const q = S.query.trim().toLowerCase();
    const xs = book().accounts.filter((a) => (S.fam === "ALLE" || a.family === S.fam) && (!q || a.name.toLowerCase().includes(q))).sort(sorters[S.sort]);
    const shown = S.showAll || q ? xs : xs.slice(0, 15);
    list.replaceChildren(...(shown.length ? shown.map((a) => accountRow(a)) : [h("p", { class: "empty" }, "Ingen kontoer passer.")]));
    more.hidden = shown.length === xs.length;
    more.textContent = `Vis alle (${xs.length})`;
  };
  const chip = (group, key, label) => h("button", { class: "chip", "aria-pressed": String(S[group] === key), onclick: (e) => {
    S[group] = key;
    e.currentTarget.parentElement.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === e.currentTarget)));
    draw();
  } }, label);
  const more = h("button", { class: "more", onclick: () => { S.showAll = true; draw(); } });
  wrap.append(
    h("input", { class: "search", type: "search", placeholder: "Søk etter en konto", value: S.query, "aria-label": "Søk etter en konto",
      oninput: (e) => { S.query = e.target.value; draw(); } }),
    h("div", { class: "chips", role: "group", "aria-label": "Sorter" }, chip("sort", "ret", "Avkastning"), chip("sort", "dd", "Minst fall"), chip("sort", "trades", "Flest handler"), chip("sort", "name", "Navn")),
    h("div", { class: "chips", role: "group", "aria-label": "Gruppe" }, chip("fam", "ALLE", "Alle"),
      Object.keys(FAMILY_RULE).map((f) => chip("fam", f, S.doc.familyNames[f] || f))),
    list, more);
  draw();
  return wrap;
}

function market(m, after) {
  const off = osloOffset();
  const hourly = Array.from({ length: 24 }, (_, i) => m.spread_by_hour_utc[(i - off + 24) % 24]);
  const hourHost = h("div", { class: "chart" }), dayHost = h("div", { class: "chart" });
  after.push(() => bars(hourHost, { values: hourly, labels: hourly.map((_, i) => `kl. ${String(i).padStart(2, "0")}`), fmt: (v) => `${nf2.format(v)} % gap`,
    tip, title: "Kjøp/salg-gapet per time på døgnet", color: "var(--accent)" }));
  after.push(() => bars(dayHost, { values: m.trades_by_day.map((d) => d.count), labels: m.trades_by_day.map((d) => shortDate(d.day)),
    fmt: (v) => `${v} handler`, tip, title: "Handler per dag hos Firi", color: "var(--bh)" }));
  const p = m.passive;
  return card("Firi-markedet", `${m.quotes} timer målt`,
    h("div", { class: "stat-row" },
      h("div", { class: "stat" }, h("div", { class: "k" }, "Gap mellom kjøp og salg nå"), h("div", { class: "v num" }, `${nf2.format(m.now.spread_pct)} %`)),
      h("div", { class: "stat" }, h("div", { class: "k" }, "Et kjøp på 500 kr koster"), h("div", { class: "v num" }, `+${nf2.format(m.now.buy500_pct ?? 0)} %`))),
    p ? h("div", { class: "rings", style: "margin-top:16px;grid-template-columns:1fr 1fr" },
      ringBox(p.bid_fill_share, pctPlain(p.bid_fill_share), "tålmodig kjøp fylt innen 1 t", "var(--accent)"),
      ringBox(p.ask_fill_share, pctPlain(p.ask_fill_share), "tålmodig salg fylt innen 1 t", "var(--bh)")) : null,
    h("h2", { style: "margin-top:18px" }, "Gap per time", h("span", { class: "sub" }, `norsk tid · snitt ${nf2.format(m.spread_median_pct)} %`)), hourHost,
    h("h2", { style: "margin-top:16px" }, "Handler per dag", h("span", { class: "sub" }, "hos Firi")), dayHost);
}

function osloOffset() {
  const now = new Date();
  const oslo = Number(now.toLocaleString("en-GB", { timeZone: "Europe/Oslo", hour: "2-digit", hour12: false }));
  return (oslo - now.getUTCHours() + 24) % 24;
}

function drift() {
  const o = S.doc.operation;
  const row = (k, v, cls) => h("div", { class: "fam", style: "grid-template-columns:1fr auto" }, h("div", {}, k), h("div", { class: `pct num ${cls || ""}` }, v));
  return card("Drift", null,
    row("Papirdager behandlet", `${o.days}`),
    row("Manglende dager", `${o.missing_days.length}`, o.missing_days.length ? "warn" : "ok"),
    row("Feil lagret", `${o.errors}`, o.errors ? "warn" : "ok"),
    o.last_error ? row("Siste feil", `${o.last_error.type}`) : null,
    row("Oppdatert", new Date(S.doc.generated_at).toLocaleString("nb-NO", { dateStyle: "short", timeStyle: "short" })));
}

function foot() {
  return h("p", { class: "foot" }, S.doc.note, h("br"), `Strategisett ${S.doc.strategy_set} · 500 kr per konto · ingen ekte penger`);
}

// ---------------------------------------------------------------- én konto
function accountPage(id, after) {
  const ids = byId(), a = ids.get(id), root = h("div", { class: "wrap" });
  root.append(h("button", { class: "back", onclick: () => { location.hash = "#/"; } }, "‹ Alle kontoer"));
  if (!a) { root.append(card(null, null, h("p", { class: "empty" }, "Fant ikke denne kontoen."))); return root; }
  const bh = ids.get("BASE_buy_and_hold");
  const vsBh = bh && a.id !== bh.id ? a.ret - bh.ret : null;
  root.append(seg());
  root.append(h("div", { class: "acct-head" },
    h("h1", {}, a.name),
    h("div", { class: "acct-tags" },
      h("span", { class: "tag" }, S.doc.familyNames[a.family] || a.family),
      h("span", { class: "tag" }, a.in_btc ? `₿ Eier bitcoin (${pctPlain(a.exposure)})` : "Kontanter"),
      a.active ? null : h("span", { class: "tag" }, "Venter på data")),
    h("div", { class: "acct-value" }, h("span", { class: "v num" }, kr(a.value)), pill(a.ret)),
    h("div", { class: "rule" }, `Startet med 500 kr. `, vsBh == null || Math.abs(vsBh) < EPS ? "" :
      `${nf1.format(Math.abs(vsBh * 100))} prosentpoeng ${vsBh > 0 ? "bedre" : "dårligere"} enn kjøp og hold. `, FAMILY_RULE[a.family] || "")));
  // diagrammet
  const n = S.doc.days.length;
  const span = { "7": 7, "30": 30, "90": 90, alt: n }[S.range] || n;
  const from = Math.max(0, n - span);
  const host = h("div", { class: "chart" });
  const tabs = h("div", { class: "tabs", role: "group", "aria-label": "Periode" },
    [["7", "7 d"], ["30", "30 d"], ["90", "90 d"], ["alt", "Alt"]].map(([k, l]) => h("button", { "aria-pressed": String(S.range === k), onclick: () => { S.range = k; render(); } }, l)));
  const idx = new Map(S.doc.days.map((d, i) => [d, i]));
  const evByDay = new Map(a.events.map((e) => [e.day, e]));
  const markers = a.events.map((e) => ({ i: idx.get(e.day) - from, kind: e.action })).filter((m) => m.i >= 0);
  const series = [{ name: "Denne kontoen", values: a.values.slice(from), color: "var(--accent)", area: true }];
  if (bh && a.id !== bh.id) series.push({ name: "Kjøp og hold", values: bh.values.slice(from), color: "var(--bh)", dash: true });
  root.append(card("Utvikling", "verdi i kr", tabs, host,
    h("div", { class: "key-row" },
      series.map((q) => h("span", {}, h("span", { class: `ln${q.dash ? " dash" : ""}`, style: `border-color:${q.color}` }), q.name)),
      markers.length ? h("span", {}, h("span", { style: "color:var(--up)" }, "▲"), " kjøp  ", h("span", { style: "color:var(--down)" }, "▼"), " salg") : null)));
  after.push(() => lineChart(host, { dates: S.doc.days.slice(from), series, markers, fmtY: (v, full) => (full ? kr(v) : kr0(v)), fmtDate: shortDate, tip,
    extra: (i) => { const e = evByDay.get(S.doc.days[from + i]); return e ? { value: `${e.action === "BUY" ? "▲ Kjøp" : "▼ Salg"} ${kr0(e.amount)}`, label: REASON[e.reason] || "handel" } : null; } }));
  // ringer
  const nl = (w, d) => (w ? ring({ value: w.share, size: 84, stroke: 8, color: w.share >= 0.75 ? "var(--up)" : "var(--accent)", center: pctPlain(w.share), label: `${pctPlain(w.share)} av ${d}-dagersperiodene uten tap` })
    : ring({ value: 0, size: 84, stroke: 8, center: "–", label: `trenger ${d} dager` }));
  root.append(card("Målet", "minst 75 % av periodene uten tap",
    h("div", { class: "rings" },
      h("div", { class: "ring-wrap" }, nl(a.no_loss_5, 5), h("div", { class: "ring-label" }, "5-dagers perioder uten tap")),
      h("div", { class: "ring-wrap" }, nl(a.no_loss_30, 30), h("div", { class: "ring-label" }, "30-dagers perioder uten tap")),
      h("div", { class: "ring-wrap" }, ring({ value: a.max_dd, size: 84, stroke: 8, color: "var(--down)", center: pctPlain(a.max_dd), label: `største fall ${pctPlain(a.max_dd)}` }),
        h("div", { class: "ring-label" }, "største fall fra topp"))),
    h("div", { class: "stat-row", style: "margin-top:14px" },
      h("div", { class: "stat" }, h("div", { class: "k" }, "Handler"), h("div", { class: "v num" }, `${a.trades}`)),
      h("div", { class: "stat" }, h("div", { class: "k" }, "Betalt i gebyr"), h("div", { class: "v num" }, kr(a.fees))))));
  // handlene
  const trades = [...a.events].reverse();
  root.append(card("Handler", trades.length ? `${trades.length} stk` : null,
    trades.length ? h("div", {}, trades.map((e) => h("div", { class: "trade" },
      h("div", { class: `ic ${e.action === "BUY" ? "buy" : "sell"}`, "aria-hidden": "true" }, e.action === "BUY" ? "▲" : "▼"),
      h("div", {}, h("div", { class: "t1" }, e.action === "BUY" ? "Kjøp" : "Salg", " ", h("span", { class: "tag" }, REASON[e.reason] || "handel")),
        h("div", { class: "t2" }, `${shortDate(e.day, true)} · kurs ${S.book === "firi" ? kr0(e.price) : `${nf0.format(e.price)} $`}`)),
      h("div", { class: "amt num" }, kr(e.amount), h("div", { class: "t2" }, `gebyr ${kr(e.fee)}`)))))
      : h("p", { class: "empty" }, "Ingen handler ennå.")));
  root.append(foot());
  return root;
}

// ---------------------------------------------------------------- ruting
function route() { const m = location.hash.match(/^#\/konto\/(.+)$/); return m ? { page: "konto", id: decodeURIComponent(m[1]) } : { page: "hjem" }; }

function render() {
  if (!S.doc) return;
  tip.hide();
  const r = route(), after = [];
  app.replaceChildren(r.page === "konto" ? accountPage(r.id, after) : overview(after));
  after.forEach((f) => f());
}

let last = route().page;
addEventListener("hashchange", () => {
  const r = route();
  if (last === "hjem" && r.page === "konto") { S.scroll = scrollY; S.range = "alt"; }
  render();
  scrollTo(0, r.page === "hjem" ? S.scroll : 0);
  last = r.page;
});
let lastW = innerWidth;
addEventListener("resize", () => { if (Math.abs(innerWidth - lastW) > 20) { lastW = innerWidth; const y = scrollY; render(); scrollTo(0, y); } });

loadDoc().then((doc) => {
  doc.familyNames = { A: "Modellens signal", B: "Trend", C: "Snitt med margin", D: "Signal med filter", E: "Rolig marked",
    F: "Kjøp etter fall", G: "Utbrudd", H: "Med stopp", MS: "Størrelse", BASE: "Grunnlinjer" };
  for (const f of doc.books[S.book]?.summary?.families || []) doc.familyNames[f.family] = f.name;
  S.doc = doc;
  render();
}).catch((e) => {
  app.replaceChildren(h("div", { class: "wrap" }, h("div", { class: "skeleton" }, e.message)));
});
