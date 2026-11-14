// The data source. Today: the fictional demo document produced by the real execution engine
// (python -m agent.execution.demo). Later: the same shape read from the database through the owner's two-factor
// login (docs/platform/PLATFORM_PLAN.md section 7). Pages only ever see the object returned here.

export const PERIODS = [
  ["6h", 6], ["12h", 12], ["1d", 24], ["3d", 72], ["5d", 120], ["7d", 168], ["14d", 336], ["21d", 504],
  ["1m", 720], ["3m", 2160], ["6m", 4320], ["9m", 6480], ["1y", 8760],
];

let cached = null;

export async function loadState() {
  if (cached) return cached;
  const res = await fetch("fixtures/demo.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`could not load the data (${res.status})`);
  const doc = await res.json();
  cached = enrich(doc);
  return cached;
}

function enrich(doc) {
  const start = new Date(doc.series.start).getTime();
  const step = doc.series.step_hours * 3600e3;
  const n = doc.series.equity.length;
  const times = Array.from({ length: n }, (_, i) => start + i * step);
  const now = new Date(doc.generated_at);
  const at = (hoursAgo) => {
    const i = n - 1 - hoursAgo;
    return i >= 0 ? doc.series.equity[i] : null;
  };
  const eq = doc.portfolio.equity;
  const change = (h) => {
    const past = at(h);
    return past == null ? null : { abs: eq - past, rel: eq / past - 1 };
  };
  const decisionsByHour = new Map(doc.decisions.map((d) => [d.as_of, d]));
  const tradesByHour = new Map(doc.trades.map((t) => [t.as_of, t]));
  return {
    ...doc, now, times,
    change: { "24h": change(24), "7d": change(168), "30d": change(720) },
    sinceDeposit: { abs: eq - doc.account.deposited, rel: eq / doc.account.deposited - 1 },
    vsBuyHold: eq - doc.portfolio.buy_hold,
    decisionsByHour, tradesByHour,
    lastDecision: doc.decisions[doc.decisions.length - 1],
    lastTrade: doc.trades[doc.trades.length - 1],
    window(hours) {
      const from = Math.max(0, n - 1 - hours);
      const equity = doc.series.equity.slice(from);
      const raw = doc.series.buy_hold.slice(from);
      // Buy-and-hold over the same period, started from the portfolio's value at the period's start, so the two lines
      // answer "what if I had just held Bitcoin since then" on one scale.
      const bench = raw.map((v) => (v / raw[0]) * equity[0]);
      return {
        times: times.slice(from), equity, bench,
        trades: doc.trades.filter((t) => new Date(t.as_of).getTime() >= times[from]),
      };
    },
  };
}
