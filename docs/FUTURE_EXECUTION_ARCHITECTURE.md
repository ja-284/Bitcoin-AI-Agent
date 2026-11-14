# Execution architecture — APPROVED 2026-11-14, NOT YET LIVE

**Status (2026-11-14):** the owner approved real-money automatic trading (CLAUDE.md principle 10 and the decisions
log). The execution layer is being built in `agent/execution`, and the plan, the evidence and the progress live in
`docs/platform/PLATFORM_PLAN.md`. **Nothing trades yet:** no job runs the layer, no exchange key exists, and
`docs/ops/status.json` records `"trading_capability": false` until the hourly workflow runs it (a test keeps the two
in agreement).

## The user's statement of 2026-09-26 (verbatim), whose requirements the layer keeps

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

**What changed on 2026-11-14:** the owner decided not to wait for the prospective evaluation to finish, and not to run
a paper-trading phase as a product ("this is not paper trading"). Every other requirement above is kept:

| requirement | how it is met |
|---|---|
| the prediction system can be evaluated independently | the layer only reads the prediction record (tested); the frozen models, checkpoints and holdout are untouched |
| execution cannot alter predictive behaviour | nothing in the prediction engine imports the layer (tested) |
| testing before live execution | unit tests, a simulated exchange, a dry run with no order, then one minimum-size order the owner watches |
| risk controls can reject a prediction before any order | the pure strategy checks every limit before an order exists (`agent/execution/strategy.py`) |
| every execution can be audited | every decision, including "no trade", is recorded with its inputs and checks |
| an independent kill switch | the owner's pause in the app and a repository variable, either one stops every order |
| the exchange can be changed without a rewrite | one small adapter interface (`agent/execution/exchange.py`); Firi is one implementation |

## Facts to keep next to it

- **The BUY/HOLD/SELL signal has no demonstrated predictive value** at any horizon tested (E001, E017; scoring 0.2.0).
  Since go-live, the owner's rule would have lost 12.3% at a 0.10% fee in a market that fell 18.8%
  (`docs/platform/PLATFORM_PLAN.md` section 2.1).
- **Costs decide the result while there is no edge.** On Firi a buy and a later sell cost about 2.7% at the spread and
  fee seen on 2026-11-14 (one snapshot). The strategy is built to trade rarely.
- **The one validated output says nothing about direction.** `move_size_1h_v1` estimates how likely the next hour's
  move is to exceed 0.25%; the strategy uses it only to size positions down.
