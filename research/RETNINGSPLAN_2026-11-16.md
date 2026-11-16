# Retningsplan: bedre retning, særlig når Bitcoin faller (2026-11-16)

**Eierens mål (2026-11-16):** forbedre hvilken vei Bitcoin går innenfor lyset vi bruker (timen), både opp og ned, men
først og fremst når Bitcoin faller, der systemet er svakt. Målet er at det går oppover og at systemet blir lønnsomt.
Vi tar oss tid, men jobber den veien. Planen skal også si hvordan vi finner ut hva som kan legges til eller endres.

Dette dokumentet er en plan. Ingenting live, frosset eller registrert er endret av det.

---

## 1. Hva vi vet nå

### 1.1 Diagnosen av det live signalet (beskrivende, 2026-11-16)

Det live BUY/HOLD/SELL-signalet (pipeline 0.2.0), 1 385 graderte timer fra 2026-09-19 til 2026-11-16 (kilde: `python
tools/falls_diagnosis.py`, kjørt 2026-11-16 ca. 18:20 UTC; tallene endrer seg når registeret vokser). Perioden var
mest rolig og litt fallende. Bare beskrivelse: ingenting er tunet på dette, og det blinde retningssporet er ikke lest.

| | 1 time | 24 timer (overlappende, ~57 uavhengige) |
|---|---|---|
| Andel som falt | 51,6 % | 53,5 % |
| Etter SELG: falt | 52,2 % [48,2, 56,3] | 49,0 % [44,9, 53,2] |
| Etter KJØP: steg | 50,2 % [44,5, 55,8] | **38,7 % [33,4, 44,4]**, mot 46,5 % for alle |
| SELG i timer som falt / steg | 42,6 % / 41,5 % | 37,6 % / 45,0 % |
| KJØP i timer som falt / steg | 20,7 % / 22,2 % | **25,0 % / 18,2 %** |
| SELG blant de 10 % største fallene / stigningene | 55,8 % / 51,4 % | 41,2 % / 40,4 % |

**Hva det betyr:**
- **På 1 time** treffer signalet ikke bedre enn tilfeldig, verken opp eller ned. SELG kommer nesten like ofte før
  timer som stiger som før timer som faller. SELG er litt vanligere rundt de største bevegelsene, men like mye ved
  store stigninger. Signalet reagerer altså på *store bevegelser*, ikke på *retning*.
- **På 24 timer** er eierens observasjon riktig i dette utvalget: KJØP kom oftere før fall enn før stigning. Utvalget
  er lite (~57 uavhengige døgn, ett rolig regime), så det er en observasjon, ikke et bevis.
- **Mekanismen er tydelig:**
  - Etter en time som falt mer enn 0,5 %, sier signalet SELG i 73 % av tilfellene, men neste time stiger i 50 %.
  - Etter en time som steg mer enn 0,5 %, sier det KJØP i 34 %, og neste time faller oftere (snitt −0,11 %).
  - **Signalet beskriver timen som var, ikke timen som kommer.** Det jager bevegelsen.
  - Kategorien «chart_pattern» dominerer: −0,90 i snitt ved SELG og +0,89 ved KJØP. Det er glidende snitt og
    topp/bunn-struktur, som henger etter kursen.
- **Dette stemmer med forskningen:** på 1 time er den målte strukturen en svak *tilbakevending* (E015, E032, E039).
  Signalet regner derimot bevegelse som *fortsettelse* (gjennomgangen 2026-10-21).

### 1.2 Forskningen så langt

- **Retning fra lysene alene er nesten tilfeldig.**
  - Den beste timemodellen (E032) har en ekte, men liten fordel: Brier-ferdighet +0,4 %.
  - E039 testet fra 1 time til 30 dager. Bare kortsiktig tilbakevending holdt seg stabil, og den er langt under
    kostnadene. Et nytt bredt søk i de samme lysene er avsluttet.
- **Bevegelsens størrelse er forutsigbar:** move-size-modellen er bedre enn den enkle regelen, også framover (500-timers
  avlesningen). Hvor stor en bevegelse blir, vet vi altså noe om. Hvilken vei den går, vet vi nesten ingenting om.
- **Det frosne retningssporet** (E034, `direction_1h_v1`) samler blindt.
  - Første titt etter 1 000 timer, ≈ 2026-11-26.
  - Dommen kommer etter 6 500 timer, ≈ 2027-07.
- **Kostnadsmuren på Firi:**
  - Gebyret er 0,7 % per side, og gapet mellom kjøp og salg er ~1,1–1,3 % (målt hver time siden i dag). En hel runde
    koster altså ~2,5 %.
  - 80 % av timene beveger seg mindre enn ~0,4 % (diagnosen over).
  - **Ingen enkelttime kan betale en hel runde.** Lønnsomhet krever færre og større beslutninger (dager til uker),
    der kunnskap om retning time for time brukes som *byggestein*, ikke handles direkte (E038, E040).
- **Slitasje:** utviklingsårene er undersøkt av 31 eksperimenter, og holdout-perioden kan brukes én gang. Nye ideer
  må derfor stort sett prøves på **ny informasjon** eller **framover i tid**.

---

## 2. Hva «bedre» betyr: det samme målebåndet hver gang

Hver idé måles på det samme, og alltid mot enkle sammenligninger. Statistikk og økonomi rapporteres hver for seg.

**Retning (statistikk), opp og ned hver for seg:**
1. *Treff ved fall:* P(falt | SELG) mot andelen som falt i alle timer, med usikkerhetsintervall. Det samme for
   P(steg | KJØP).
2. *Varsling av fall:* andelen av de 10 % største fallene som var varslet, **minus** andelen av de 10 % største
   stigningene som fikk det samme varselet. Uten minus-leddet belønnes et signal som bare reagerer på uro.
3. *Sannsynligheter:* Brier og log loss mot grunnraten, og kalibrering (sier 60 % = skjer 60 %).

**Penger (økonomi), med Firis ekte kostnader:**
4. *Fallfangst:* hvor stor del av de samlede fallene systemet sto utenfor. *Stigningsfangst:* hvor stor del av
   stigningene det var med på.
5. Netto avkastning mot kjøp og hold og mot kontanter, største fall fra topp, og eierens mål: minst 75 % av 5- og
   30-dagersperiodene uten tap, med positivt snitt.
6. Alltid mot **tilfeldig timing med samme eksponering**, så vi skiller timing fra «var bare mer inne i markedet».

**Grunnlinjer:** grunnraten (andelen som stiger), «alltid opp», move-size-regelen uten tilpasning (E019), det frosne
retningssporet, og det live signalet slik det er nå.

---

## 3. Hvordan vi vet hva som kan legges til eller endres: trakten

Hver idé går gjennom de samme portene, i denne rekkefølgen. De fleste ideer skal stoppe tidlig; det er meningen.

| Port | Spørsmål | Stopper hvis |
|---|---|---|
| 1. Idé | **Hvorfor** skulle dette varsle fall? En mekanisme, skrevet ned før vi ser på data. | Ingen mekanisme, bare «kanskje det korrelerer». |
| 2. Data | Gratis? Riktig tidsstemplet (punkt i tid)? Historikk? Kan vi nå den fra våre servere? | Betalt, etterjustert eller uten pålitelige tider. |
| 3. Registrering | Mål, horisont, grunnlinjer, terskel for suksess og stoppregler, skrevet i `research/experiments/` **før** test. | Ikke registrert, ikke testet. |
| 4. Rask test | Hvis data har historikk: én test på utviklingsdata, på de samme radene som grunnlinjene. Gir bare en hypotese (slitasje). | Under terskelen: lukket, ikke prøvd igjen i ny drakt. |
| 5. Skygge framover | Egen tabell, blind til avlesningen, antall timer bestemt på forhånd av en styrkeberegning (som E033). **Den eneste rene dommeren nå.** | Ikke bedre enn grunnlinjene ved avlesningen. |
| 6. Papirhandel | Som E042: med Firis ekte priser og gebyr, mot kjøp og hold og tilfeldig timing. | Ikke lønnsom etter kostnader. |
| 7. Ekte penger | Bare med en **egen, uttrykkelig godkjenning** fra eieren. | – |

**Faste regler underveis:**
- én endring om gangen;
- det live signalet og de frosne modellene står urørt som referanse (nye ideer kjører *ved siden av*);
- aldri tuning på resultater framover eller på holdout;
- hvert forsøk skrives ned, også de som feilet;
- en overbevisende forklaring er ikke bevis (prinsipp 8).

**Hvordan vi velger rekkefølgen:** hver idé får en enkel vurdering på
1. mekanisme for fall (sterk, middels eller svak);
2. data (gratis og punkt i tid: ja eller nei);
3. tid til dom (uker eller måneder);
4. kostnad (NOK 0 er et krav).

**Ny informasjon slår alltid en ny vri på de gamle lysene.**

---

## 4. Kandidatene, rangert

### A. Rette opp logikken i signalet (en endring, ikke et tillegg)

Signalet jager bevegelsen (1.1). Det kan erstattes av et beslutningslag som bruker:
- det vi faktisk har målt: svak tilbakevending på 1 time, og størrelsen fra move-size-modellen;
- en sannsynlighet i stedet for en håndsatt poengsum;
- en handling bare når forventet bevegelse er større enn kostnaden (som `lf-1.0` i `docs/platform/LOW_FREQUENCY_PLAN.md`).

Dette står allerede i veikartet etter 2 000-timers avlesningen (≈ 2026-12-14): først **på papir og registrert**, så
som skygge ved siden av det live signalet. Det live signalet erstattes ikke før en skygge har vunnet.

### B. Ny informasjon om fall (tillegg), samlet framover fra nå

Store fall i Bitcoin er ofte tvangssalg: belånte posisjoner som avvikles i kjede. Det synes i andre data enn
lysene:

| | Hva | Hvorfor for fall | Å sjekke |
|---|---|---|---|
| B1 | **Terminmarkedet**: funding rate, åpne posisjoner (open interest), likvidasjoner, long/short-forhold, basis | belåning bygger seg opp før kjedefall; funding er allerede registrert for ny test ≈ 2027-03 | Binance' terminmarked stenger trolig amerikanske adresser (GitHubs servere); alternativer: OKX, Bybit, Deribit, eller innsamling fra Supabase i EU |
| B2 | **Opsjoner**: Deribits volatilitetsindeks (DVOL) og skjevhet mellom salgs- og kjøpsopsjoner | markedets frykt for fall, prissatt | om historikken er punkt i tid; om API-et er åpent fra våre servere |
| B3 | **Ordrebok og ordreflyt**: ubalanse mellom kjøps- og salgssiden (Binance) og Firis bok (logges hver time siden i dag) | tynn kjøpsside før fall | bare framover; Binance-speilet nås allerede |
| B4 | **Nyheter**: kjører allerede | dårlige nyheter før fall | dom ≈ 2027-02 (E030: ingen tegn ennå) |
| B5 | **Stablecoin- og kjedestrømmer**: penger inn på børsene | salgspress | gratis kilder med pålitelige tider er trolig ikke tilgjengelige; sjekkes, aldri antas |

Det meste av dette finnes gratis bare **framover**. Derfor er det viktigste tiltaket å **starte klokka**: samle det
nå, i egne tabeller og uten å kunne stoppe timesjobben, akkurat som Firi-loggen. Da kan det testes ordentlig om
noen måneder.

### C. Lengre beslutninger, timebasert kunnskap

Retning time for time blir byggestein for beslutninger over dager, som papirhandelen allerede tester (E042, 118
strategier). Det er der kostnadene kan bæres.

### D. Det vi ikke gjør
- et nytt bredt søk i de samme lysene (E039 lukket det);
- tunge maskinlæringsmodeller på slitte data;
- å justere de frosne vektene etter det live registeret;
- å kopiere publiserte modeller.

---

## 5. Tidsplan

| Når | Hva |
|---|---|
| **Nå (uke 47)** | Diagnosen (1.1) er gjort. Neste: en ren lesesjekk av kildene i B1–B3 (gratis, punkt i tid, nåbare fra GitHub og Supabase), med en anbefaling. Ingen endring i drift. |
| **På eierens ja** | Innsamling framover av de beste kildene, i egne tabeller, ett steg om gangen, testet. |
| ≈ 2026-11-26 | Retningssporets første titt (1 000 timer; ingen dom). |
| ≈ 2026-12-14 | 2 000-timers avlesningen av move-size. Deretter kandidat A, beslutningslaget, på papir og registrert. |
| Når nok er samlet | Det første registrerte «fall»-eksperimentet med de nye dataene. Hvor lenge vi må samle, bestemmes av en styrkeberegning på forhånd. |
| ≈ 2027-02 | Nyhetsdommen; papirhandelen 90 dager (2027-02-13); retningssporet 3 000 timer. |
| ≈ 2027-03 | Funding-testen, som registrert. |
| ≈ 2027-07 | Retningssporets dom (6 500 timer). |

## 6. Det eieren bestemmer

1. **Innsamling framover** av terminmarked, opsjoner og ordrebok (B1–B3), når lesesjekken er ferdig: ja eller nei per
   kilde. Kostnad NOK 0; egne tabeller; kan ikke stoppe timesjobben.
2. **Horisonten for handel:** at retning time for time forbedres som byggestein, mens selve handelen skjer over dager,
   fordi en enkelttime ikke kan betale Firis kostnader.

Alt annet i planen gjør jeg selv, i rekkefølgen over, og rapporterer underveis.

---

## 7. Status

**2026-11-16 (kveld), eierens ja til A, B og C** («slik vil vi ha det»), også til at handelen skjer over dager mens
timeprediksjonen forbedres som byggestein.

**Kildesjekken** (`python tools/source_probe.py`, og arbeidsflyten «Kildeprøve» på GitHubs servere i USA):

| Kilde | Herfra (Norge) | Fra GitHub (USA) | Historikk bakover (sett herfra) |
|---|---|---|---|
| OKX: funding, åpne posisjoner, long/short, likvidasjoner | ✅ | ✅ | long/short og OI ~30 dager; likvidasjoner bare de siste |
| Deribit: DVOL, opsjoner, funding | ✅ | ✅ | DVOL time for time fra 2021 |
| Kraken Futures: funding, åpne posisjoner | ✅ | ✅ | funding ~1 år |
| Hyperliquid: funding, åpne posisjoner, premie | ✅ | ✅ | funding fra 2023 |
| Bitfinex: funding, belånte long/short | ✅ | ✅ | belånte posisjoner fra 2021 |
| Binance-ordreboken (speilet) | ✅ | ✅ | bare nå |
| Binance-termin | ✅ | ❌ HTTP 451 | funding fra 2019, basis fra 2020 |
| Bybit | ✅ | ❌ HTTP 403 | åpne posisjoner fra 2021 |
| BitMEX | ❌ 403 | ❌ 403 | – |

**Innsamlingen framover** (`agent/context`, tabellene `context_hourly` og `context_errors`):
- **Kildene:** de seks som svarer fra GitHub, med én rad per kilde og time.
- **Hvordan:** hentes i timesjobben og bare der det mangler. Raden er et kort sammendrag (~2,5 kB i timen, ~22 MB i året) med kildens egne tidsstempler og `fetched_at`. Tabellene får bare nye rader og kan ikke leses utenfra. Steget kan aldri stoppe timesjobben.
- **Punkt i tid:** en rad kan bare brukes for prediksjoner med informasjonsgrense etter `fetched_at`.
- **Blind til registreringen:** dataene ses ikke mot utfall før et registrert eksperiment (port 3).
- **Historikken bakover** (Deribit, Bybit, Binance-termin, Bitfinex) kan hentes herfra til en rask test (port 4).
  - Den må registreres som et øyeblikksbilde gjennom datagrensen (`agent/research/snapshots.py`).
  - Den tas bare til 2025-06-30, så holdout-perioden aldri lastes ned.
