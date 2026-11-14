"""
The execution layer (docs/platform/PLATFORM_PLAN.md): turns the newest saved prediction into a decision about how much
of the owner's capped capital to hold in BTC, checks every risk limit, and places at most one idempotent order per hour
through an exchange adapter.

It is a separate layer by design (docs/FUTURE_EXECUTION_ARCHITECTURE.md): it READS the prediction record and never
writes it, nothing in the prediction engine imports it, and it can be paused without touching the analysis. As of
2026-11-14 it has no real exchange adapter and is not wired into any job: the only exchange is the simulated one used
by the tests and the website's fictional demo data.
"""
