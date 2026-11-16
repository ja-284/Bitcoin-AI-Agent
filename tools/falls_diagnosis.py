"""
Diagnose av det live BUY/HOLD/SELL-signalet i timer og døgn der Bitcoin falt, mot timer der den steg
(research/RETNINGSPLAN_2026-11-16.md, avsnitt 1.1). Bare lesing, på en tilkobling satt til bare lesing; skriver
ingenting. Beskrivende: tallene brukes aldri til å tune noe, og det blinde retningssporet (shadow_direction) leses ikke.

    python tools/falls_diagnosis.py
"""
import math
import sys
from collections import Counter

sys.path.insert(0, ".")
from agent.database.db import get_connection


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


with get_connection() as conn:
    conn.read_only = True
    with conn.cursor() as cur:
        cur.execute("""SELECT p.as_of, p.signal, p.overall_score, p.close_price, p.category_scores,
                              o1.pct_change_from_prediction, o24.pct_change_from_prediction
                       FROM predictions p
                       LEFT JOIN prediction_outcomes o1 ON o1.prediction_id = p.id AND o1.horizon_hours = 1 AND o1.status = 'ok'
                       LEFT JOIN prediction_outcomes o24 ON o24.prediction_id = p.id AND o24.horizon_hours = 24 AND o24.status = 'ok'
                       WHERE p.pipeline_version = '0.2.0' ORDER BY p.as_of""")
        rows = cur.fetchall()
    conn.rollback()

print(f"timer: {len(rows)}  fra {rows[0][0]:%Y-%m-%d %H} til {rows[-1][0]:%Y-%m-%d %H} UTC")
by_time = {r[0]: r for r in rows}

for label, idx in (("1 time", 5), ("24 timer", 6)):
    xs = [(r[1], r[idx]) for r in rows if r[idx] is not None]
    n = len(xs)
    down = [s for s, x in xs if x < 0]
    up = [s for s, x in xs if x > 0]
    print(f"\n=== {label}: {n} graderte timer; falt {len(down)} ({len(down)/n:.1%}), steg {len(up)} ({len(up)/n:.1%})"
          + ("  [overlappende vinduer: ~n/24 uavhengige]" if idx == 6 else ""))
    cd, cu, ca = Counter(down), Counter(up), Counter(s for s, _ in xs)
    print("  signal i timer som FALT :", {k: f"{cd[k]/len(down):.1%}" for k in ("SELL", "HOLD", "BUY")})
    print("  signal i timer som STEG :", {k: f"{cu[k]/len(up):.1%}" for k in ("SELL", "HOLD", "BUY")})
    print("  signal totalt           :", {k: f"{ca[k]/n:.1%}" for k in ("SELL", "HOLD", "BUY")})
    for sig, want in (("SELL", "falt"), ("BUY", "steg")):
        sel = [x for s, x in xs if s == sig]
        k = sum(1 for x in sel if (x < 0 if sig == "SELL" else x > 0))
        p, lo, hi = wilson(k, len(sel))
        base = len(down) / n if sig == "SELL" else len(up) / n
        mean = sum(sel) / len(sel) if sel else float("nan")
        print(f"  etter {sig:4s} (n={len(sel):4d}): {want} {p:.1%} [{lo:.1%}, {hi:.1%}]  (alle timer: {base:.1%});"
              f" snitt {mean*100:+.3f} %")
    hold = [x for s, x in xs if s == "HOLD"]
    print(f"  etter HOLD (n={len(hold)}): snitt {sum(hold)/len(hold)*100:+.3f} %;  alle timer snitt {sum(x for _, x in xs)/n*100:+.3f} %")
    big = sorted(x for _, x in xs)[: max(1, n // 10)]
    cut = big[-1]
    cb = Counter(s for s, x in xs if x <= cut)
    nb = sum(cb.values())
    print(f"  de 10 % største fallene (≤ {cut*100:.2f} %, n={nb}):", {k: f"{cb[k]/nb:.1%}" for k in ("SELL", "HOLD", "BUY")})
    bigu = sorted(x for _, x in xs)[-max(1, n // 10):]
    cutu = bigu[0]
    cbu = Counter(s for s, x in xs if x >= cutu)
    nbu = sum(cbu.values())
    print(f"  de 10 % største stigningene (≥ {cutu*100:.2f} %, n={nbu}):", {k: f"{cbu[k]/nbu:.1%}" for k in ("SELL", "HOLD", "BUY")})

# Mekanisme: hva sier signalet rett etter en time som falt, og hva skjer timen etter?
print("\n=== Rett etter en time som falt / steg (forrige times endring i sluttkurs)")
from datetime import timedelta
groups = {"forrige time falt > 0,5 %": [], "forrige time falt 0–0,5 %": [], "forrige time steg 0–0,5 %": [], "forrige time steg > 0,5 %": []}
for r in rows:
    prev = by_time.get(r[0] - timedelta(hours=1))
    if prev is None or r[5] is None:
        continue
    pr = r[3] / prev[3] - 1
    key = ("forrige time falt > 0,5 %" if pr < -0.005 else "forrige time falt 0–0,5 %" if pr < 0
           else "forrige time steg 0–0,5 %" if pr <= 0.005 else "forrige time steg > 0,5 %")
    groups[key].append((r[1], r[5]))
for k, g in groups.items():
    if not g:
        continue
    c = Counter(s for s, _ in g)
    nxt = sum(x for _, x in g) / len(g)
    upshare = sum(1 for _, x in g if x > 0) / len(g)
    print(f"  {k:28s} n={len(g):4d}  signal SELL {c['SELL']/len(g):.0%} HOLD {c['HOLD']/len(g):.0%} BUY {c['BUY']/len(g):.0%}"
          f"  | neste time: snitt {nxt*100:+.3f} %, steg {upshare:.0%}")

# Hvilke kategorier driver SELL?
print("\n=== Kategorienes snitt-score når signalet var SELL / BUY")
acc = {}
for r in rows:
    for c in r[4] or []:
        if c.get("score") is None:
            continue
        acc.setdefault((r[1], c["name"]), []).append(c["score"])
names = sorted({k[1] for k in acc})
for sig in ("SELL", "HOLD", "BUY"):
    print(f"  {sig:4s}: " + "  ".join(f"{nm} {sum(acc.get((sig, nm), [0]))/max(len(acc.get((sig, nm), [])),1):+.2f}" for nm in names))
