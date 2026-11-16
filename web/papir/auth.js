// Innlogging med Supabase Auth, uten tredjepartskode: e-post og passord, så koden fra autentiseringsappen (to trinn).
// Bare den offentlige nøkkelen brukes; den gir ingen tilgang alene. Dokumentet kan bare leses av Control Center-
// kontoen i en økt med to trinn (aal2) -- databasen avgjør det, ikke denne filen. Økten huskes på denne enheten
// (localStorage) til eieren logger ut, så mobilen slipper å logge inn hver gang.

const STORE = "papir.session";

export class Auth {
  constructor(url, key) {
    this.url = url;
    this.key = key;
    this.session = read();
  }

  async call(path, { method = "POST", body, token } = {}) {
    const headers = { apikey: this.key, "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${this.url}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new AuthError(res.status, data);
    return data;
  }

  keep(data) {
    this.session = { access_token: data.access_token, refresh_token: data.refresh_token,
      expires_at: data.expires_at || Math.floor(Date.now() / 1000) + (data.expires_in || 3600) };
    try { localStorage.setItem(STORE, JSON.stringify(this.session)); } catch { /* privat modus: bare denne gangen */ }
    return this.session;
  }

  aal() { return claims(this.session?.access_token)?.aal || null; }

  async signIn(email, password) {
    this.keep(await this.call("/auth/v1/token?grant_type=password", { body: { email, password } }));
    return this.aal();
  }

  async totpFactor() {
    const user = await this.call("/auth/v1/user", { method: "GET", token: this.session.access_token });
    return (user.factors || []).find((f) => f.factor_type === "totp" && f.status === "verified") || null;
  }

  async verify(factorId, code) {
    const token = this.session.access_token;
    const ch = await this.call(`/auth/v1/factors/${encodeURIComponent(factorId)}/challenge`, { token });
    this.keep(await this.call(`/auth/v1/factors/${encodeURIComponent(factorId)}/verify`, { token, body: { challenge_id: ch.id, code } }));
    return this.aal();
  }

  async fresh() {
    if (!this.session) return null;
    if (this.session.expires_at - 60 > Date.now() / 1000) return this.session.access_token;
    try {
      this.keep(await this.call("/auth/v1/token?grant_type=refresh_token", { body: { refresh_token: this.session.refresh_token } }));
      return this.session.access_token;
    } catch {
      this.forget();
      return null;
    }
  }

  async signOut() {
    const token = this.session?.access_token;
    this.forget();
    if (token) await this.call("/auth/v1/logout", { token }).catch(() => {});
  }

  forget() {
    this.session = null;
    try { localStorage.removeItem(STORE); } catch { /* ingenting å fjerne */ }
  }

  async document() {
    const token = await this.fresh();
    if (!token) return null;
    const rows = await this.call("/rest/v1/paper_snapshot?select=document&id=eq.1", { method: "GET", token });
    return rows.length ? rows[0].document : { empty: true };
  }
}

export class AuthError extends Error {
  constructor(status, data) {
    super(data.msg || data.error_description || data.message || `Feil ${status}`);
    this.status = status;
    this.code = data.error_code || data.code || "";
  }
}

function read() {
  try { return JSON.parse(localStorage.getItem(STORE)) || null; } catch { return null; }
}

function claims(token) {
  if (!token) return null;
  try {
    const p = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(p + "=".repeat((4 - (p.length % 4)) % 4)));
  } catch { return null; }
}
