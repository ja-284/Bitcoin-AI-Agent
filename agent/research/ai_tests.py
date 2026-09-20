"""
E009: test the two LLM components in their narrow roles (research brief Part M).

News scorer (Haiku): schema completeness, repeat stability, relevance separation,
sentiment sign on unambiguous headlines, order sensitivity.
Explainer (Sonnet): names the given signal, contains no forbidden content, and a few
adversarial cases are written out for hand inspection.

Costs a handful of API calls. Writes research/results/<experiment>/{results.json, summary.md}.

    python -m agent.research.ai_tests --experiment E009
"""

import argparse
import json
import logging
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from agent.ai import explainer, news_scorer
from agent.shared.types import CategoryScore, ConfidenceBreakdown, NewsItem

logger = logging.getLogger(__name__)

BITCOIN_HEADLINES = [
    "Bitcoin climbs above $80,000 as spot ETF inflows hit a record",
    "US regulator approves new rules for Bitcoin custody at banks",
    "Bitcoin miners sell reserves as hashrate reaches all-time high",
    "MicroStrategy adds another 5,000 BTC to its treasury",
]
NON_BITCOIN_HEADLINES = [
    "Manchester United appoint new manager after poor start to the season",
    "New study links coffee consumption to longer sleep duration",
    "Ethereum developers delay the next network upgrade by two months",
    "Apple unveils thinner laptop with a new chip",
]
BULLISH = ["Bitcoin ETF sees record $2 billion of inflows in a single day", "Major pension fund announces first Bitcoin allocation"]
BEARISH = ["Bitcoin falls 15% after large exchange halts withdrawals following hack", "Regulators propose ban on Bitcoin trading for retail investors"]
FIXED_SET = BITCOIN_HEADLINES + NON_BITCOIN_HEADLINES + BULLISH + BEARISH

FORBIDDEN_PATTERNS = [
    r"\byou should (buy|sell)\b", r"\b(buy|sell) now\b", r"\bI am (confident|certain)\b", r"\bI('m| am) \d+% (sure|confident)\b",
    r"\bguarantee", r"\binvest(ment)? advice\b(?! -)",  # 'not investment advice' is fine; the prompt asks for that framing
]


def _items(headlines: list[str]) -> list[NewsItem]:
    return [NewsItem(headline=h, source="test", url=f"https://example.test/{i}", published_at=None) for i, h in enumerate(headlines)]


def test_news_scorer(repeats: int) -> dict:
    out: dict = {"schema_ok": 0, "schema_calls": 0, "aggregate_scores": [], "per_headline": {h: {"relevance": [], "sentiment": []} for h in FIXED_SET}}
    for _ in range(repeats):
        out["schema_calls"] += 1
        score = news_scorer.score_news(_items(FIXED_SET))
        assessments = score.detail.get("assessments", [])
        if len(assessments) == len(FIXED_SET):
            out["schema_ok"] += 1
        out["aggregate_scores"].append(score.score)
        for a in assessments:
            h = a.get("headline", "")
            key = next((k for k in FIXED_SET if k == h or k in h or h in k), None)
            if key:
                out["per_headline"][key]["relevance"].append(a["relevance_to_bitcoin"])
                out["per_headline"][key]["sentiment"].append(a["sentiment"])

    # order sensitivity: shuffled set, compared against the mean of the repeats
    shuffled = FIXED_SET[:]
    random.Random(7).shuffle(shuffled)
    out["schema_calls"] += 1
    shuffled_score = news_scorer.score_news(_items(shuffled))
    if len(shuffled_score.detail.get("assessments", [])) == len(FIXED_SET):
        out["schema_ok"] += 1
    out["shuffled_aggregate"] = shuffled_score.score

    agg = np.array(out["aggregate_scores"])
    out["aggregate_mean"] = float(agg.mean())
    out["aggregate_std"] = float(agg.std())
    sent_stds = [float(np.std(v["sentiment"])) for v in out["per_headline"].values() if len(v["sentiment"]) > 1]
    out["mean_per_headline_sentiment_std"] = float(np.mean(sent_stds)) if sent_stds else float("nan")
    rel = lambda hs: float(np.mean([np.mean(out["per_headline"][h]["relevance"]) for h in hs if out["per_headline"][h]["relevance"]]))  # noqa: E731
    out["mean_relevance_bitcoin"] = rel(BITCOIN_HEADLINES)
    out["mean_relevance_non_bitcoin"] = rel(NON_BITCOIN_HEADLINES)
    out["bullish_sentiments"] = {h: out["per_headline"][h]["sentiment"] for h in BULLISH}
    out["bearish_sentiments"] = {h: out["per_headline"][h]["sentiment"] for h in BEARISH}
    out["sentiment_sign_correct_every_repeat"] = all(s > 0 for h in BULLISH for s in out["per_headline"][h]["sentiment"]) and all(
        s < 0 for h in BEARISH for s in out["per_headline"][h]["sentiment"]
    )
    out["order_shift"] = abs(out["shuffled_aggregate"] - out["aggregate_mean"])
    out["verdicts"] = {
        "S1_schema": out["schema_ok"] == out["schema_calls"],
        "S2_stability": out["aggregate_std"] <= 0.05 and out["mean_per_headline_sentiment_std"] <= 0.15,
        "S3_relevance": out["mean_relevance_non_bitcoin"] <= 0.30 and out["mean_relevance_bitcoin"] >= 0.70,
        "S4_sentiment_sign": out["sentiment_sign_correct_every_repeat"],
        "S5_order": out["order_shift"] <= max(2 * out["aggregate_std"], 0.02),
    }
    return out


def _cats(trend, momentum, volume, chart, news) -> list[CategoryScore]:
    return [
        CategoryScore("trend", trend, 0.25, False), CategoryScore("momentum", momentum, 0.25, True),
        CategoryScore("volume", volume, 0.20, True), CategoryScore("chart_pattern", chart, 0.15, False),
        CategoryScore("news", news, 0.15, True),
    ]


EXPLAINER_CASES = [
    {"name": "plain_buy", "signal": "BUY", "overall": 0.31, "conf": (0.9, 1.0, 0.95), "cats": _cats(0.5, 0.1, 0.2, 1.0, 0.3)},
    {"name": "plain_sell", "signal": "SELL", "overall": -0.28, "conf": (0.8, 1.0, 0.9), "cats": _cats(-0.6, -0.2, -0.1, -1.0, -0.2)},
    {"name": "plain_hold", "signal": "HOLD", "overall": 0.02, "conf": (0.5, 0.85, 0.675), "cats": _cats(0.1, -0.1, 0.0, 0.0, 0.05)},
    {"name": "adversarial_buy_with_negative_news", "signal": "BUY", "overall": 0.2, "conf": (0.3, 1.0, 0.65), "cats": _cats(0.9, 0.4, 0.3, 1.0, -0.9)},
    {"name": "adversarial_hold_all_missing_but_trend", "signal": "HOLD", "overall": 0.1, "conf": (0.5, 0.25, 0.375), "cats": [CategoryScore("trend", 0.1, 0.25, False)] + [CategoryScore(n, 0.0, 0.0, i, {"reason": "unavailable"}) for n, i in (("momentum", True), ("volume", True), ("chart_pattern", False), ("news", True))]},
    {"name": "adversarial_sell_low_confidence", "signal": "SELL", "overall": -0.16, "conf": (0.1, 0.6, 0.35), "cats": _cats(-0.2, 0.8, -0.9, -1.0, 0.0)},
]


def test_explainer(repeats_plain: int) -> dict:
    out: dict = {"cases": [], "signal_named": 0, "wrong_signal_named": 0, "forbidden_hits": 0, "n": 0}
    for case in EXPLAINER_CASES:
        n_runs = repeats_plain if case["name"].startswith("plain") else 1
        for _ in range(n_runs):
            conf = ConfidenceBreakdown(*case["conf"])
            text = explainer.write_explanation(signal=case["signal"], overall_score=case["overall"], confidence=conf, category_scores=case["cats"], close_price=81000.0)
            out["n"] += 1
            names = {s for s in ("BUY", "SELL", "HOLD") if re.search(rf"\b{s}\b", text)}
            named_correct = case["signal"] in names
            named_wrong = bool(names - {case["signal"]})
            forbidden = [p for p in FORBIDDEN_PATTERNS if re.search(p, text, flags=re.IGNORECASE)]
            given_numbers = {f"{v:.0%}" for v in case["conf"]} | {f"{case['overall']:+.2f}", f"{case['overall']:+.3f}"}
            stray_pct = [m for m in re.findall(r"\b\d{1,3}%", text) if m not in given_numbers]
            out["signal_named"] += int(named_correct)
            out["wrong_signal_named"] += int(named_wrong)
            out["forbidden_hits"] += int(bool(forbidden))
            out["cases"].append({"case": case["name"], "signal": case["signal"], "named_correct": named_correct, "other_signals_mentioned": sorted(names - {case["signal"]}),
                                 "forbidden": forbidden, "percentages_not_given": stray_pct, "text": text})
    out["verdicts"] = {"X1_signal": out["signal_named"] == out["n"] and out["wrong_signal_named"] == 0, "X2_forbidden": out["forbidden_hits"] == 0}
    return out


def run(experiment: str) -> Path:
    results = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "models": {"news": news_scorer.MODEL, "explainer": explainer.MODEL},
               "news_scorer": test_news_scorer(repeats=5), "explainer": test_explainer(repeats_plain=2)}
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(render(results), encoding="utf-8")
    return out_dir


def render(res: dict) -> str:
    ns, ex = res["news_scorer"], res["explainer"]
    L = [f"# {res['experiment']} — AI component tests", "", f"news: {res['models']['news']} · explainer: {res['models']['explainer']}", "",
         "## News scorer", "",
         f"- S1 schema: {ns['schema_ok']}/{ns['schema_calls']} calls returned one assessment per headline → {'PASS' if ns['verdicts']['S1_schema'] else 'FAIL'}",
         f"- S2 stability: aggregate score mean {ns['aggregate_mean']:+.3f}, std {ns['aggregate_std']:.3f}; mean per-headline sentiment std {ns['mean_per_headline_sentiment_std']:.3f} → {'PASS' if ns['verdicts']['S2_stability'] else 'FAIL'}",
         f"- S3 relevance: Bitcoin headlines {ns['mean_relevance_bitcoin']:.2f}, non-Bitcoin {ns['mean_relevance_non_bitcoin']:.2f} → {'PASS' if ns['verdicts']['S3_relevance'] else 'FAIL'}",
         f"- S4 sentiment sign on unambiguous headlines, every repeat → {'PASS' if ns['verdicts']['S4_sentiment_sign'] else 'FAIL'}",
         f"- S5 order: shuffled aggregate {ns['shuffled_aggregate']:+.3f} vs mean {ns['aggregate_mean']:+.3f} (shift {ns['order_shift']:.3f}) → {'PASS' if ns['verdicts']['S5_order'] else 'FAIL'}",
         "", "Per-headline (mean relevance / mean sentiment / sentiment std):", ""]
    for h, v in ns["per_headline"].items():
        if v["relevance"]:
            L.append(f"- {h[:70]}: {np.mean(v['relevance']):.2f} / {np.mean(v['sentiment']):+.2f} / {np.std(v['sentiment']):.2f}")
    L += ["", "## Explainer", "",
          f"- X1 signal named, never another: {ex['signal_named']}/{ex['n']} named, {ex['wrong_signal_named']} mentioned another signal → {'PASS' if ex['verdicts']['X1_signal'] else 'FAIL'}",
          f"- X2 forbidden content: {ex['forbidden_hits']}/{ex['n']} → {'PASS' if ex['verdicts']['X2_forbidden'] else 'FAIL'}",
          "- X3 adversarial cases (read by hand):", ""]
    for c in ex["cases"]:
        if c["case"].startswith("adversarial"):
            L += [f"### {c['case']} (signal {c['signal']}; stray percentages: {c['percentages_not_given'] or 'none'})", "", c["text"], ""]
    return "\n".join(L)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    out = run(args.experiment)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print((out / "summary.md").read_text(encoding="utf-8"))
