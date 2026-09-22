"""
The second of the project's two narrow AI calls: writes the final plain-English
explanation. This runs strictly *after* the deterministic decision has already been
made -- it narrates the score, signal, and confidence it's handed, and is never asked
to judge, restate, or second-guess any of them. That boundary is what keeps a
persuasive-sounding paragraph from ever being mistaken for evidence the call was
right (CLAUDE.md rule 8), and stops confidence from getting silently re-invented by
the AI (CLAUDE.md rule 6).
"""

from anthropic import Anthropic

from agent.config.settings import AI_MAX_RETRIES, AI_TIMEOUT_S, ANTHROPIC_API_KEY
from agent.shared.types import CategoryScore, ConfidenceBreakdown

MODEL = "claude-sonnet-5"  # a person reads this text directly, so it gets a bit more nuance than the news step

# Explanations run 170-265 tokens in practice (measured over the live record on 2026-09-22),
# so 1024 leaves ~4x headroom. The cap matters anyway: unlike the news call, where truncation
# breaks the JSON and fails loudly, a truncated explanation is still readable text and would be
# stored as if it were complete. stop_reason is therefore checked below. Only generated tokens
# are billed, so the headroom itself is free.
MAX_TOKENS = 1024

SYSTEM_PROMPT = (
    "You write short, plain-English explanations of a Bitcoin analysis system's output "
    "for a beginner audience. You are given a signal, an overall score, a confidence "
    "breakdown, and the individual category scores that produced them -- all already "
    "decided by deterministic code before you saw them. Your only job is to narrate why "
    "these particular numbers point where they do, in 3-5 sentences. Never state your "
    "own confidence, never second-guess the signal, and never suggest the reader take "
    "any real trading action -- this is analysis only, not investment advice.\n\n"
    "Be precise about what the two confidence components actually mean, and do not "
    "describe them loosely:\n"
    "- 'agreement' measures only how closely the INDEPENDENT categories agree with each "
    "other. Categories marked as not independent are excluded from it, because they are "
    "built from overlapping math and would agree with each other by construction. Never "
    "say or imply that agreement reflects all categories.\n"
    "- 'completeness' measures how much of the scoring weight had usable data this run."
)


def _format_scores(category_scores: list[CategoryScore]) -> str:
    lines = []
    for c in category_scores:
        if c.weight == 0:
            lines.append(f"- {c.name}: no data this run")
        else:
            independence = "independent" if c.is_independent else "NOT independent, shares math with another category"
            lines.append(f"- {c.name}: score {c.score:+.2f} (weight {c.weight:.2f}, {independence})")
    return "\n".join(lines)


def write_explanation(
    signal: str,
    overall_score: float,
    confidence: ConfidenceBreakdown,
    category_scores: list[CategoryScore],
    close_price: float,
) -> str:
    user_content = (
        f"Close price: ${close_price:,.2f}\n"
        f"Signal: {signal}\n"
        f"Overall score: {overall_score:+.3f} (range -1 to +1)\n"
        f"Confidence: {confidence.overall_confidence:.0%} "
        f"(agreement={confidence.agreement_score:.0%}, completeness={confidence.completeness_score:.0%})\n\n"
        f"Category scores:\n{_format_scores(category_scores)}"
    )

    client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=AI_TIMEOUT_S, max_retries=AI_MAX_RETRIES)  # bounded: an hourly job cannot wait the SDK's 10-minute default
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text = next((block.text for block in response.content if block.type == "text"), "").strip()
    if not text:
        raise ValueError("explanation model returned no text")  # recorded as explanation_error; the decision is untouched
    if getattr(response, "stop_reason", None) == "max_tokens":
        # Half an explanation reads like a whole one. Better no text than a sentence that stops
        # mid-thought and is stored as if the model had finished (cf. the news truncation, 2026-09-21).
        raise ValueError(f"explanation truncated at max_tokens={MAX_TOKENS} ({len(text)} characters produced)")
    return text
