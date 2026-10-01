# Fantasy Football Analytics Platform — Shared Engineering Principles

This repo builds a comprehensive fantasy football **analytics and decision-support platform**.
Player projections are a core foundational component, but the platform also covers valuation,
rosters, transactions, waivers, drafts, league analytics, simulation, and historical decision
evaluation. These rules apply to every agent working in this repo, custom or default.

## Non-negotiable rules

- **No future leakage.** Never use information that was unavailable as of a given
  `prediction_timestamp` / `evaluation_timestamp` when generating or backtesting a projection,
  valuation, or historical ("ex-ante") decision evaluation.
- **Point-in-time correctness.** Historical transactions, rosters, injuries, depth charts, and
  projections must be reconstructible as of any past timestamp `T`. Never overwrite historical
  rows needed for point-in-time analysis — append/version instead.
- **Projection ≠ Valuation.** Projections are expected production. Valuation additionally
  accounts for replacement level, scarcity, league settings, roster requirements, risk, and
  dynasty horizon. Never conflate the two.
- **Ex-ante vs ex-post.** When scoring a historical transaction, always separate: ex-ante
  expected value, realized value, forecast error, and decision quality. An unexpectedly bad
  outcome does not prove the original decision was bad.
- **No hard-coding.** Do not hard-code scoring settings, league settings, or player IDs where a
  configuration/mapping layer should be used instead.
- **No monolithic files.** Keep data, feature, projection, valuation, roster, transaction, and
  evaluation logic in separate, modular, reusable components. Don't duplicate logic across agents.
- **Position-appropriate modeling.** Don't force one model architecture across all positions, and
  don't reach for ML simply because it's available — understand prediction vs forecasting vs
  valuation vs optimization vs causal inference vs decision analysis before choosing a method.
- **Structured objects over free text.** Agents communicate via typed objects (e.g.
  `PlayerProjection`, `PlayerValuation`, `RosterSnapshot`, `TransactionEvent`,
  `TransactionEvaluation`, `ModelPrediction`, `ModelEvaluation`) carrying IDs, timestamps,
  versions, assumptions, and source/model metadata.
- **Reproducibility.** Every analytical result should be traceable to `model_version`,
  `feature_version`, `data_version`, `season`, `week`, `horizon`, `scoring_format`, `league_id`.

## Layered architecture

```
DATA LAYER → REFERENCE/IDENTITY LAYER → FEATURE ENGINEERING → PLAYER/TEAM INTELLIGENCE
  → PROJECTION ENGINE → VALUATION ENGINE → ROSTER/TRANSACTION/DRAFT/WAIVER ANALYTICS
  → SIMULATION/DECISION ENGINE → HISTORICAL EVALUATION → APPLICATION/API/UI
```

Prefer a Databricks medallion style for data (`RAW → BRONZE → SILVER → GOLD/ANALYTICS`) and keep
reference data separate from analytical facts.

## Which agent handles what

This repo defines specialized agents under `.github/agents/`. Route work instead of reinventing
specialized logic inline:

| Task involves... | Use agent |
|---|---|
| Cross-domain requests, combining multiple systems | `orchestrator` |
| Scoring formats, dynasty/redraft, roster rules, domain definitions | `domain-expert` |
| Ingestion, schemas, ID mapping, Sleeper/nflverse/Databricks | `data-engineering` |
| Player-level features (usage, role, trends, comps) | `player-intelligence` |
| Projection models/services (weekly, ROS, distributions) | `projection-engine` |
| Converting projections into fantasy value | `player-valuation` |
| Roster/portfolio analysis and optimization | `roster-analytics` |
| Trade/waiver/FAAB/draft transaction structure | `transaction-analytics` |
| Reconstructing what was knowable at time T | `point-in-time-decision` |
| Grading transaction decision quality | `transaction-scoring` |
| Waiver/free-agent recommendations | `waiver-free-agent` |
| Draft and draft-pick valuation | `draft-pick` |
| League-wide standings/activity/competitive balance | `league-analytics` |
| What-if scenarios, Monte Carlo | `simulation-whatif` |
| Model/feature methodology choices | `modeling-statistics` |
| Backtesting and model accuracy evaluation | `backtesting-evaluation` |
| Leakage/bias/data-quality auditing | `data-quality-auditor` |
| Explaining "why" behind a number | `explanation-insight` |

## Development approach

Build incrementally in phases (data/identity → historical datasets → features → projections →
projection backtesting → valuation → roster analytics → league analytics → transactions →
point-in-time transaction evaluation → waiver/draft/trade → simulation → historical decision
quality → application/API/UI). Inspect existing code before adding new code; don't discard
working code without an architectural reason.
