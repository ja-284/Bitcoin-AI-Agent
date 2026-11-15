# Beskyttelsesmålet: resultat av E040 (2026-11-15)

**Eierens mål (alternativ 2, 2026-11-15):** med Firis kostnader skal systemet ikke tape penger, altså stå på
startverdien eller høyere, i minst 75 % av periodene. Det skal gjelde uansett om Bitcoin stiger eller faller, og
systemet skal helst tjene når Bitcoin stiger.

**Slik ble det målt:**
- 300 kr i kontanter ved en fersk start, hver dag.
- Perioder på 5 og 30 dager.
- Stigende og fallende perioder telles hver for seg.
- I tillegg kreves positiv snittavkastning, så et system som aldri handler, ikke kan bestå.

**Gjennomføringen:**
- 104 daglige regler, alle fastsatt i registreringen (`b223385`) før det fantes kode.
- Koden er `87bd199`, og den kjørte én gang.
- Bare utviklingsdata 2018–2025. Den forseglede holdout-perioden er ikke rørt.
- Porten mot E038 passerte 10 av 10, med avvik 0,0.

## Resultat

**Én regel når målet i begge periodene: utbruddsregelen 55/20.** Den kjøper når sluttkursen er høyere enn alle de 55
foregående dagene, og selger når den er lavere enn alle de 20 foregående. Dette er en kjent regel fra litteraturen
(«Turtle»-systemet fra 1980-tallet), ikke noe vi har tilpasset til dataene. Den er også den eneste regelen som kom
gjennom både utforskingen (2018–23) og valideringen (2024–25). Den samme regelen med stop-loss på 10 % består også,
men gir ikke noe ekstra.

**Med Firis realistiske kostnad (1,25 % per side):**

| | 2018–23 | 2024–25 |
|---|---|---|
| 5-dagersperioder uten tap | **87 %** | **85 %** |
| 30-dagersperioder uten tap [95 % KI] | **78 %** [71, 84] | **75 %** [58, 89] |
| – av dem der Bitcoin falt | 77 % | 76 % |
| 30-dagersperioder med **gevinst** | 28 % | 28 % |
| Snittavkastning per 30 dager | +2,9 % | +3,2 % |
| Netto over hele perioden | +580 % | +44 % |
| Kjøp og hold, netto | +562 % | +139 % |
| Største fall | 43 % | 23 % |
| Kjøp og hold, største fall | 77 % | 28 % |
| Handler i året | 6 | 8 |
| Andel av tiden i Bitcoin | 37 % | 39 % |

Ved den konservative kostnaden (1,6 %) består regelen fortsatt: 77 % og 75 % av 30-dagersperiodene uten tap.

**År for år**, regelen sammenlignet med Bitcoin:

| År | Regelen | Bitcoin |
|---|---|---|
| 2018 | 0 % | −41 % |
| 2019 | +104 % | +94 % |
| 2020 | +132 % | +302 % |
| 2021 | +29 % | +60 % |
| 2022 | −30 % | −64 % |
| 2023 | +59 % | +156 % |
| 2024 | +64 % | +121 % |
| 2025 (til 30.06) | −7 % | +16 % |

## Hva tallene betyr

1. **Målet nås, men mest ved å stå utenfor markedet.** Regelen eier Bitcoin bare 37–39 % av tiden. Når den står i
   kontanter, er perioden «uten tap». En regel med tilfeldig timing, men samme eksponering, ville havnet på 71–74 %. Den
   egne timingen legger altså til bare noen få prosentpoeng på andelen.
   - Timing-testen ga 94. og 81. persentil for andelen, og 99. og 93,5. for snittavkastningen. Det holder ikke til
     merkelappen «timing», som krevde 95. persentil i begge periodene. Regelen er derfor merket **«eksponering»**.
2. **Gevinsten kommer fra noen få store trender.** Bare 28 % av 30-dagersperiodene ender med gevinst. Resten står i
   ro. Snittet (+3 % per 30 dager) kommer av at regelen fanger de store oppgangene.
3. **Den beskytter i fall, men taper mot kjøp og hold når Bitcoin stiger mye.** I 2018 sto den utenfor, og i 2022
   tapte den halvparten av det Bitcoin tapte. Men i 2020, 2023 og 2024 fikk den bare halvparten av oppgangen.
4. **Marginen er tynn.** I 2024–25 havnet regelen på nøyaktig 75 %, og intervallet går fra 58 % til 89 %.
   Utviklingsdataene domineres av et kraftig stigende marked og er brukt i 34 eksperimenter. Dette er et lovende
   funn, ikke et bevis.
5. **Dagens modell er langt unna målet.**
   - På timesnivå ender den uten tap i bare 7–10 % av 30-dagersperiodene, med snitt −18 til −19 % per 30 dager.
   - Én beslutning om dagen gir 29–36 %.
   - Utbruddsregelen er en helt annen tilnærming: få handler, lange posisjoner og mye tid i kontanter.

## Neste steg (krever eierens godkjenning)

**Papirhandel framover med utbruddsregelen 55/20.** Ingen ekte penger.

- Regelen trenger bare 55 dagers historikk. Det live registeret har nå 57 dager, så den kan starte straks uten å røre
  den forseglede perioden.
- Testen registreres før den begynner, og måles på eierens mål med Firis kostnader og helst Firis egne priser.
- **Varighet:** papirhandel beviser programvaren og kostnadene i løpet av uker. Målet selv (75 % av 30-dagersperiodene)
  trenger mer enn et år før intervallet blir smalt.
- **Ekte penger** kommer først etter det, og bare etter en egen, uttrykkelig godkjenning (regelen fra
  `docs/platform/LOW_FREQUENCY_PLAN.md`).

Hele tabellen over alle 104 regler ligger i `research/results/E040/protection_goal.md`.
