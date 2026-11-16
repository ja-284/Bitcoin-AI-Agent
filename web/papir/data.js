// Datakilden. Med config.js (laget ved publisering, aldri committet): det ekte dokumentet («paper-state 1») fra
// databasen, bak innloggingen med to trinn. Uten config.js (lokalt, i repoet): den oppdiktede demoen
// (python -m agent.papertrade.demo, merket "fictional": true). Sidene ser bare objektet som kommer herfra.
import { Auth } from "./auth.js";

export const SCHEMA = "paper-state 1";

let config = null;
try {
  config = await import("./config.js");
} catch {
  config = null; // ingen innstillinger: demo
}

export const auth = config ? new Auth(config.SUPABASE_URL, config.SUPABASE_KEY) : null;

export async function loadDoc() {
  if (!auth) {
    const res = await fetch("demo.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`Kunne ikke hente dataene (${res.status}).`);
    return check(await res.json());
  }
  const doc = await auth.document();
  if (doc === null) return { needsLogin: true };
  if (doc.empty) return { empty: true };
  return check(doc);
}

function check(doc) {
  if (doc.schema !== SCHEMA) throw new Error(`Ukjent dataformat: ${doc.schema}.`);
  return doc;
}
