// Shared formatting, icons and small UI helpers. Numbers and dates are shown the Norwegian way (kr 1 234,56;
// Europe/Oslo time); the interface text is English.
const TZ = "Europe/Oslo";
const nb = (o) => new Intl.NumberFormat("nb-NO", o);

export const fmt = {
  nok: (v, d = 2) => nb({ style: "currency", currency: "NOK", minimumFractionDigits: d, maximumFractionDigits: d }).format(v),
  nokSigned: (v, d = 2) => nb({ style: "currency", currency: "NOK", minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: "exceptZero" }).format(v),
  pct: (v, d = 1) => nb({ style: "percent", minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: "exceptZero" }).format(v),
  pctPlain: (v, d = 0) => nb({ style: "percent", minimumFractionDigits: d, maximumFractionDigits: d }).format(v),
  num: (v, d = 0) => nb({ minimumFractionDigits: d, maximumFractionDigits: d }).format(v),
  btc: (v) => nb({ minimumFractionDigits: 6, maximumFractionDigits: 8 }).format(v) + " BTC",
  time: (d) => new Intl.DateTimeFormat("nb-NO", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(d),
  day: (d) => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" }).format(d),
  date: (d) => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" }).format(d),
  dateTime: (d) => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(d),
  hourLabel: (d) => new Intl.DateTimeFormat("nb-NO", { timeZone: TZ, hour: "2-digit" }).format(d) + ":00",
  dayKey: (d) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d),
};

export const cls = (v) => (v > 0 ? "gain" : v < 0 ? "loss" : "");

const P = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
  chart: '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  flask: '<path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.5L14 9V3"/><path d="M7 15h10"/>',
  wallet: '<path d="M20 7V5a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a2 2 0 0 1-2-2V6"/><circle cx="17" cy="13.5" r="1.2"/>',
  pulse: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  more: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
  pause: '<path d="M9 5v14M15 5v14"/>',
  play: '<path d="M7 5v14l12-7z"/>',
  download: '<path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/>',
  back: '<path d="M15 5 8 12l7 7"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
};

export const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ""}</svg>`;

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export function toast(text) {
  const t = document.createElement("div");
  t.className = "toast";
  t.setAttribute("role", "status");
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

export function confirmDialog(title, body, okLabel = "Confirm", danger = false) {
  return new Promise((resolve) => {
    const back = document.createElement("div");
    back.className = "dlg-back";
    back.innerHTML = `<div class="dlg" role="dialog" aria-modal="true" aria-labelledby="dlg-t">
      <h3 id="dlg-t">${esc(title)}</h3><p>${esc(body)}</p>
      <div class="dlg-actions"><button class="btn" data-a="no">Cancel</button>
      <button class="btn ${danger ? "danger" : "primary"}" data-a="ok">${esc(okLabel)}</button></div></div>`;
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener("click", (e) => {
      if (e.target === back) close(false);
      const a = e.target.closest("[data-a]");
      if (a) close(a.dataset.a === "ok");
    });
    document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { document.removeEventListener("keydown", k); close(false); } });
    document.body.appendChild(back);
    back.querySelector('[data-a="ok"]').focus();
  });
}

export function sigChip(s) {
  return `<span class="sig ${esc(s)}">${s === "NONE" ? "NO TRADE" : esc(s)}</span>`;
}
