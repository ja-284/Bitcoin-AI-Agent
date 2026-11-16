// Datakilden. I dag: den oppdiktede demoen (python -m agent.papertrade.demo, merket "fictional": true).
// Senere: det samme dokumentet («paper-state 1», agent/papertrade/snapshot.py) hentet fra databasen bak eierens
// innlogging med to trinn. Sidene ser bare objektet som kommer herfra.

export const SCHEMA = "paper-state 1";

export async function loadDoc() {
  const res = await fetch("demo.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`Kunne ikke hente dataene (${res.status}).`);
  const doc = await res.json();
  if (doc.schema !== SCHEMA) throw new Error(`Ukjent dataformat: ${doc.schema}.`);
  return doc;
}
