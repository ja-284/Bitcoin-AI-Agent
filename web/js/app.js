// The app shell: the theme, the navigation, a hash router and the service worker. All pages live in pages.js.
import { loadState } from "./data.js";
import { icon, esc } from "./ui.js";
import * as pages from "./pages.js";

const ROUTES = {
  home: ["Home", "home", pages.home],
  portfolio: ["Portfolio", "chart", pages.portfolio],
  activity: ["Activity", "list", pages.activity],
  decision: ["Decision", "list", pages.decision],
  risk: ["Risk", "shield", pages.risk],
  signals: ["Signals & research", "flask", pages.signals],
  funding: ["Funding", "wallet", pages.funding],
  settings: ["Settings", "gear", pages.settings],
  system: ["System", "pulse", pages.system],
  about: ["About", "info", pages.about],
  more: ["More", "more", pages.more],
};
const SIDE = [["Overview", ["home", "portfolio", "activity"]], ["Control", ["risk", "funding", "settings"]], ["Insight", ["signals", "system", "about"]]];
const TABS = ["home", "portfolio", "activity", "settings", "more"];

// ---------- theme (a per-viewer convenience: storage may be missing, so every access is guarded)
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode: the choice lasts for this visit */ } },
};
const getTheme = () => store.get("theme") || "system";
function applyTheme(t) {
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0a0c11" : "#f5f6f8");
  const b = document.getElementById("theme-btn");
  if (b) b.innerHTML = icon(dark ? "sun" : "moon");
}
function setTheme(t) { store.set("theme", t); applyTheme(t); }
applyTheme(getTheme());
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme(getTheme()));

// ---------- shell
function shell(state) {
  document.getElementById("side-nav").innerHTML = SIDE.map(([g, items]) =>
    `<div class="nav-group">${g}</div>` + items.map((r) => `<a href="#/${r}" data-r="${r}">${icon(ROUTES[r][1])}${ROUTES[r][0]}</a>`).join("")).join("");
  document.getElementById("tabbar").innerHTML = TABS.map((r) =>
    `<a href="#/${r}" data-r="${r}">${icon(ROUTES[r][1])}<span>${ROUTES[r][0]}</span></a>`).join("");
  document.getElementById("side-foot").innerHTML = state.fictional
    ? "Demo data · every value is fictional" : `Strategy ${esc(state.account.strategy_version)}`;
  document.getElementById("theme-btn").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    setTheme(dark ? "light" : "dark");
  });
  applyTheme(getTheme());
}

let cleanup = null;
async function route() {
  const state = await loadState();
  const [name, ...rest] = (location.hash.replace(/^#\/?/, "") || "home").split("/");
  const key = ROUTES[name] ? name : "home";
  const [title, , page] = ROUTES[key];
  cleanup?.();
  cleanup = null;
  document.getElementById("title").textContent = title;
  document.title = `${title} · Bitcoin Agent`;
  document.querySelectorAll("[data-r]").forEach((a) =>
    a.classList.toggle("active", a.dataset.r === key || (key === "decision" && a.dataset.r === "activity")));
  const view = page(state, key === "decision" ? decodeURIComponent(rest.join("/")) : { getTheme, setTheme });
  const root = document.getElementById("content");
  root.innerHTML = (state.fictional ? `<div class="banner demo">${icon("alert")}<div><strong>Demo data.</strong> Every value on this page is invented
    (2030), produced by the real trading engine on a made-up price path. It shows how the app works, not how it will perform.</div></div>` : "") + view.html;
  if (view.after) cleanup = view.after(root) || null;
  window.scrollTo(0, 0);
}

loadState().then((state) => { shell(state); route(); }).catch((e) => {
  document.getElementById("content").innerHTML = `<div class="card"><strong>Could not load the data.</strong><p class="muted">${esc(e.message)}</p></div>`;
});
window.addEventListener("hashchange", route);

if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* the app works without it */ });
}
