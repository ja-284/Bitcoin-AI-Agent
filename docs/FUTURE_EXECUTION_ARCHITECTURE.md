# Future execution architecture — NOT ACTIVE

**Status: NOT ACTIVE. Nothing described here exists in the code, and none of it may be built during the
current prospective evaluation.** Recorded 2026-09-26 on the user's instruction, as a statement of the
long-term direction. Project principle 10 in `CLAUDE.md` ("No real trading") remains binding: the system
is analysis-only, it has no order, wallet, exchange-account or payment code anywhere, and
`docs/ops/status.json` records `"trading_capability": false`.

## The user's statement (verbatim)

> FUTURE EXECUTION ARCHITECTURE — NOT ACTIVE
>
> The long-term goal is for the system to be capable of automatically
> executing BUY/HOLD/SELL decisions.
>
> This is intentionally NOT part of the current prospective evaluation.
>
> Future execution must remain a separate layer from the prediction/
> research engine so that:
>
> - the current prediction system can be evaluated independently
> - execution cannot alter predictive behavior
> - paper trading can be tested before live execution
> - risk controls can reject a prediction before any order
> - every execution can be audited
> - the system has an independent emergency/kill switch
> - exchange/account integration can be changed without rewriting the
>   research and prediction engine
>
> No automated trading capability is to be implemented before the
> current prospective-validation and safety work has been completed
> and a separate execution architecture has been designed and tested.

## Facts to keep next to it (so the goal is never read as a green light)

- **The BUY/HOLD/SELL signal has no demonstrated predictive value** at any horizon tested (E001, E017;
  scoring 0.2.0). A system that executed it today would be executing a measuring instrument under test.
- **The one validated output says nothing about direction.** `move_size_1h_v1` estimates how likely the
  next hour's move is to exceed 0.25%, not which way it goes. It is itself still under prospective test
  (500 / 2,000 / 5,000-hour checkpoints, `research/LIVE_EVALUATION.md`).
- The separation the statement asks for already has a foundation: the prediction engine only reads
  public data and writes its own append-only record, the research shadow cannot write to the live record
  (tested), and the backend contract (`docs/api/contract_v1.md`) is read-only. A future execution layer
  would consume that record from outside; it would not live inside the engine.

## What would have to happen first (in this order, none of it started)

1. The current prospective evaluation finishes as registered, followed by the strict final readiness audit.
2. A signal with demonstrated, pre-registered, out-of-sample predictive value exists, which is not the case today.
3. A separate execution architecture is designed, reviewed with the user and approved in `CLAUDE.md`'s
   decisions log, with its own risk limits, audit log, kill switch and paper-trading stage.
4. Paper trading is run and evaluated before any real account is connected.

Until then this file is the only place the topic lives.
