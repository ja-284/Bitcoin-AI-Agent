"""
Runs one full analysis cycle by hand and prints the result. Same code path the hourly
schedule will use -- this is just the manual entry point.

    python run.py            # run and save to the database
    python run.py --no-save  # run without writing anything
"""

import argparse
import logging

from agent.orchestrator import run_once


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-save", action="store_true", help="run the analysis without writing to the database")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    prediction = run_once(save=not args.no_save)
    if prediction is None:
        print("A prediction for this hour is already saved -- nothing to do.")
        return

    print()
    print(f"As of (last closed hour): {prediction.as_of.isoformat()}")
    print(f"Price source:             {prediction.price_source} (synthetic={prediction.price_is_synthetic})")
    print(f"Close price:              ${prediction.close_price:,.2f}")
    print()
    print("Category scores:")
    for c in prediction.category_scores:
        suffix = "  (no data this run)" if c.weight == 0 else ""
        print(f"  {c.name:15s} score={c.score:+.2f}  weight={c.weight:.2f}  independent={c.is_independent}{suffix}")
    print()
    print(f"Overall score:  {prediction.overall_score:+.3f}")
    print(f"Signal:         {prediction.signal}")
    print(
        f"Confidence:     {prediction.confidence.overall_confidence:.0%}  "
        f"(agreement={prediction.confidence.agreement_score:.0%}, "
        f"completeness={prediction.confidence.completeness_score:.0%})"
    )
    print()
    print(f"News items used: {len(prediction.news_items)}")
    print()
    print("Explanation:")
    print(prediction.explanation or "  (none -- the explanation step failed this run)")


if __name__ == "__main__":
    main()
