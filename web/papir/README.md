# Papirhandel: mobilsiden

Eierens ønske 2026-11-16: en enkel, myk side for mobilen der papirhandelen (E042) kan følges. Den viser alle de
118 «kontoene» (strategiene), hvem som går best og svakest, og et tydelig kursdiagram når du trykker på en konto.

**Ingen ekte penger.** Siden viser papirhandel og sier alltid at signalet ikke har noen påvist evne til å forutsi
kursen, og at den beste av 118 strategier vil se bedre ut enn den er. Svaret kommer ved de registrerte avlesningene
(90, 180 og 365 dager). Siden endrer ingenting; den bare viser.

## Hva siden har

- **Oversikten:** dager til neste avlesning (ring), kontoene i pluss / uendret / i minus (smultring), hvor mange som
  eier bitcoin, slår kjøp og hold og når målet så langt (ringer), bitcoinkursen, de fem beste og svakeste,
  sammenligningene (kjøp og hold, kontanter), grupper, alle kontoer (søk, sortering, filter per gruppe),
  Firi-markedet (gap nå, hva 500 kr koster, tålmodige ordrer, gap per time på døgnet, handler per dag) og drift.
- **Kontosiden:** verdi og endring, regelen i én setning, diagram over verdien med «kjøp og hold» som stiplet linje,
  kjøp ▲ og salg ▼ i diagrammet, trådkors med verdier, periodene 7 / 30 / 90 dager / alt, ringer for målet
  (5- og 30-dagersperioder uten tap) og største fall, og alle handlene med grunnen (signal, stopp, justering …).
- **Firi-priser eller modellpriser:** bryteren øverst bytter mellom de to regnskapsbøkene.
- Mørkt som standard, lyst ved et trykk. Laget for mobil først (375 px), virker også på PC.

## Filer

| Fil | Hva |
|---|---|
| `index.html`, `app.css`, `app.js`, `charts.js` | siden; ingen avhengigheter, ingen eksterne skript eller fonter |
| `data.js` | henter dokumentet; i dag den oppdiktede demoen |
| `demo.json` | OPPDIKTET (2030), laget av `python -m agent.papertrade.demo`: den ekte motoren på syntetiske kurser |
| `manifest.webmanifest`, `icon.svg` | så siden kan legges på hjemskjermen |

Dataene er ett dokument, «paper-state 1», bygget av `agent/papertrade/snapshot.py` (testet i
`tests/test_papertrade_snapshot.py`). Siden regner ingenting selv; den viser dokumentet.

Forhåndsvisning lokalt: `python -m http.server 8765 --directory web`, så `http://localhost:8765/papir/`.

## Slik henger det sammen (eierens godkjenning 2026-11-16)

- **Tallene:** papirsteget i timesjobben regner dokumentet ut på nytt hver time og legger det i `paper_snapshot`
  (én rad). Den tabellen kan bare leses av Control Center-kontoen i en økt med to trinn; alt annet i papirhandelen er
  stengt (`docs/api/stats_access.md`, tillegget 2026-11-16).
- **Innloggingen** (`auth.js`): e-post og passord, så koden fra autentiseringsappen, rett mot Supabase sin innlogging
  uten tredjepartskode. Økten huskes på telefonen til du logger ut (⏻ øverst).
- **Publiseringen** (`.github/workflows/pages.yml`): gratis på GitHub Pages. `tools/pages_config.py` skriver
  `config.js` med prosjektets adresse og den offentlige nøkkelen fra repository-variablene (aldri committet, og den
  nekter en hemmelig nøkkel). Demoen og denne filen tas ut av det som publiseres.
- **Uten `config.js`** (lokalt, i repoet) viser siden den oppdiktede demoen.

## Plan videre

1. **Gjort:** dokumentet, demoen, siden, tabellen med den ene åpningen (live 2026-11-16 17:23 UTC), innloggingen og
   publiseringsjobben; alt testet.
2. **Eierens steg:** `docs/ops/open_user_actions.md` punkt 9 (skru av nye registreringer i Supabase, slå på Pages,
   legg inn de to offentlige verdiene, kjør publiseringen).
3. **Så:** jeg sjekker publiseringen, og eieren logger inn på mobilen og legger siden på hjemskjermen.
