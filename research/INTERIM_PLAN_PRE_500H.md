# Pre-500h checkpoint — the active interim execution plan

**Adopted 2026-09-26 on the user's instruction. This is the single active work plan until the registered
500-hour prospective checkpoint.** It is not a research phase and not permission to redesign or tune. The
research methodology, the registered checkpoints (`research/LIVE_EVALUATION.md`), the sealed holdout and
the prospective-validation rules remain authoritative. The user's text is kept below, condensed (every
section and rule preserved); this header is the working summary every session reads first.

> **Status 2026-09-26 (evening): the plan's work is complete.** Every section of its audit
> (`research/INTERIM_PLAN_AUDIT.md`) is COMPLETE or CONTINUOUS, and the project is in **PRE-500H
> MONITORING-ONLY MODE**, defined in `docs/ops/STATUS.md`. This plan remains the rulebook until the
> 500-hour checkpoint. Its rules still bind, but there is no open task left in it. Work before 500 hours
> happens only for a real production problem, a security / data-integrity / reliability problem, a
> scheduled audit, genuinely new live evidence, or the checkpoint itself.

## Working summary

**Core rule:** do not change the system's predictive behaviour because we want a better result. Use the
wait for monitoring, security, testing, hardening, documentation, operational reliability, and research
that cannot contaminate the upcoming evaluation.

**Absolute rules:** (1) prospective outcomes are observations, never a tuning set; (2) the holdout stays
sealed; (3) the live predictive path is frozen — only a genuine correctness / security / data-integrity
defect may change it, versioned, tested and with its effect on the evaluation documented; (4) no frontend;
(5) no ML / retraining / online learning; (6) no busywork — every change answers *what real problem, why
now, could it affect the evaluation, how is it tested, how is it rolled back*; (7) never hide problems;
(8) never assume success — verify; (9) a task is done only when tested, regression-checked, verified live
where relevant, documented, committed and pushed; (10) preserve reproducibility — version any change to
definitions, timestamps, features, identifiers, registered experiments, checkpoint rules or scoring;
(11) research stays isolated from production.

**Priority order each session:** A live health → B security and database hardening → C reliability and
failure recovery → D observability that detects real problems → E performance only on evidence →
F research integrity. Safe research (historical/development data only, pre-stated hypothesis, logged,
never auto-promoted) comes after these.

**Change control:** 1 observability/docs (safe) · 2 security (justified + tested) · 3 reliability (real
problem) · 4 data integrity (necessary) · 5 performance (evidence) · **6 predictive behaviour — FROZEN** ·
**7 ML — out of scope** · **8 frontend — out of scope**.

**Session loop:** rebuild state from the repository and the live system → git status → recent runs →
prospective hour count → heartbeat / watchdog → was the last task truly finished? → highest-priority
unfinished task → work it to completion → continue. "Waiting for 500 hours" is not a reason to idle; no
justified work left *is* a reason to stop.

**Standing follow-ups (section 8):** watchdog verified under `bitcoin_agent`; drift check still compares
the real repository role configuration and still detects manual drift; runtime trend (no optimisation
without evidence); heartbeat and run reliability; backup and primary schedule paths; missing hours,
timestamp anomalies, fallback use, dependency failures; live/research parity; shadow isolation; database
permissions; repository cleanliness and reproducibility after each significant change.

**User absence (section 7):** before the user is away (~1 week), everything needed for unattended
operation is confirmed, and `docs/ops/STATUS.md` (with `docs/ops/status.json`) states the production
state, prospective hours, known non-critical issues, monitoring, expected automatic behaviour,
emergency-only conditions, the next checkpoint and what happens after it.

**Success is trustworthiness, not excitement:** the 500-hour result must measure the system that was
registered, not one tuned while watching the answers.

---

## The user's text, condensed (2026-09-26) — every section and rule kept, wording shortened

> PRE-500H CHECKPOINT — ACTIVE INTERIM EXECUTION PLAN
>
> This is the SINGLE ACTIVE WORK PLAN for the period while we wait for the registered 500-hour
> prospective checkpoint. This is NOT a new research phase. This is NOT permission to redesign the
> system. This is NOT permission to tune the live predictor toward better results. This is an execution
> queue for safe work that can be done during the waiting period.
>
> **1. Primary objective.** Keep the live system running reliably and collect clean prospective data
> until the 500-hour checkpoint; monitor closely; find and fix real reliability, security, correctness,
> data-integrity and operational problems; safe hardening and regression testing; better observability
> and documentation; research that does not use future 500-hour outcomes for tuning; candidate ideas only
> in isolated research environments; prepare to run unattended during the user's absence; no work merely
> to stay busy. The most important thing is preserving the integrity of the prospective evaluation.
>
> **2. Absolute rules.** (1) Prospective data must remain clean — monitor descriptively, never tune,
> select or rewrite rules on it. (2) Keep the holdout sealed. (3) Freeze predictive behaviour — except a
> genuine correctness, security, data-integrity or safety defect: identify it, preserve the old version,
> version the change, test it, determine and document its effect on the evaluation, and never tune the
> new version on the resulting outcomes. (4) No frontend work yet. (5) No ML program yet. (6) No
> busywork. (7) Never hide problems — reproduce, find the cause, fix when safe, test, document, check
> for regressions. (8) Never assume success. (9) Test before advancing. (10) Preserve reproducibility.
> (11) Keep live and research separated.
>
> **3. Work priority.** A live system health (runs, missing hours, candles, timestamps, newest closed
> candle, source failures, fallback, writes, database role, parity, shadow separation, heartbeat,
> watchdog, self-checks, runtime, repeated failures, behaviour changes, cost, workflow reliability) —
> fix real breakage before research. B security and database hardening (least privilege, grants,
> public access, drift, append-only, roles, secrets, workflow permissions, protection of new objects,
> privilege expansion, stale assumptions; never weaken checks to pass tests). C reliability and failure
> recovery (missing/malformed data, timeouts, partial failures, garbage news, short history, delays,
> duplicates, retries, rate limits, failed publish/save, watchdog and heartbeat failure — fail safely
> and visibly). D observability only where it detects real problems. E performance only on evidence.
> F research integrity (leakage, ordering, availability timestamps, targets, separation, reproducibility,
> baselines, registration, logging, loaders, precision, intervals, checkpoint reproducibility).
>
> **4. Safe research while waiting.** Only information that cannot contaminate the prospective
> evaluation: historical development data, data quality, robustness, anomaly and regime detection,
> uncertainty and calibration diagnostics, sandboxed deterministic alternatives, historical ablations
> and baselines, availability and latency studies, monitoring and fault-detection algorithms. Not
> allowed: tuning or selecting on future 500-hour outcomes, or testing repeatedly until something looks
> good. Every non-trivial experiment: hypothesis first, permitted data, established temporal validation,
> frozen baseline, logged, sample size, uncertainty, exploratory vs robust stated, never auto-promoted.
>
> **5. Candidate algorithms — research only**, isolated, with a concrete hypothesis; never introduced
> into live predictions because of historical performance.
>
> **6. Session loop** as summarised above; continue through the queue; stop only for a user-only
> decision, an irreversible action needing authorisation, a credential step, a change to the registered
> methodology, a real blocker, the session limit, or genuinely no justified work.
>
> **7. User absence (~1 week):** A least-privilege user used by all automated paths; B watchdog ran
> under it; C heartbeat working; D failure detection verified where safe and reversible; E hourly and
> backup scheduling; F no routine manual action needed; G writes, role use and self-checks; H no secret
> or configuration issue that would interrupt operation; I the 500-hour machinery ready to run by the
> registered rules; J no task depends on the user being present; K a concise status document (current
> production state, prospective hours, known non-critical issues, monitoring, expected automatic
> behaviour, emergency-only conditions, the next checkpoint, the next actions after it).
>
> **8. Current follow-ups** (the ten listed in the working summary).
>
> **9. Change control** (the eight categories above; 6, 7, 8 not implemented under this plan except the
> stated defect exception).
>
> **10. Quality gate:** the backend should become increasingly boring — predictable, observable,
> reproducible, secure, recoverable, well-tested, correctly versioned, monitored, free of known critical
> defects, able to run unattended. "More sophisticated" is not the goal; "more trustworthy" is.
>
> **11. Success** is clean prospective data, an uncontaminated evaluation, failures detected and handled,
> a secured database, healthy monitoring, acceptable runtime, reproducible and honest research, isolated
> experiments, no pointless complexity, no hidden problems, and a user who can be away for a week.
>
> **12. Final rule: do not optimise the waiting period for excitement; optimise it for trustworthiness.**
> Protect the experiment. Monitor, collect, fix real problems, test everything, research safely, keep
> experiments isolated, never tune on future outcomes, never add features for activity, never change
> predictive behaviour for a better result. When nothing safe and useful remains, stop rather than
> inventing work. Always leave the repository clean, understandable and reproducible.
