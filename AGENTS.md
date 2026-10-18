# Development instructions

- Read README.md and docs/PROJECT_PLAN.md before changing architecture. User decisions are in docs/DECISIONS.md.
- Read docs/OPERATING_MODEL.md for proposed data ingestion/quality gates, operating roles, and news/event handling. These are design requirements, not implemented or externally validated capabilities. Do not treat value, momentum, and quant outputs as three independent votes.
- Read docs/WBS.md, docs/management/STATUS.md and docs/management/CONTROL.md before implementation. Keep WBS IDs, baseline scope/order, evidence and blockers current. Never edit immutable baselines or mark external checks passed based on mocks. Version scope/schedule changes through a numbered CR and new baseline/tag. Include WBS IDs in implementation commits.
- Before continuing indicator/data expansion, read docs/AGENT_HANDOFF.md and docs/INDICATOR_DATA_DESIGN.md. New WBS 1.9–1.19 is planned, not implemented; start with actual artifact inventory/restore and preserve the separate model/host/live gates.
- Work in the existing checkout. Cloud tasks are already isolated; create no Git worktree unless requested.
- Python 3.12, uv, src layout. Use `bash scripts/setup.sh`, `bash scripts/check.sh`.
- The user has authorized creating this new project and its initial dependency manifest/lockfile. Preserve unrelated user changes. Subsequent environment-only setup must not change source, tests, dependency declarations, or lockfiles.
- Default scope: US stocks/ETFs, daily data, daily/weekly rebalancing, research → historical backtest → broker paper → separately gated live execution.
- The decision demo is synthetic and deterministic. The separate data MVP has provider adapters, independent quality checks, immutable raw/snapshot/Parquet artifacts and offline replay. Actual provider readiness is tracked separately in WBS 1.6/1.7. Do not claim LLM research, a real historical backtest, external broker paper trading, or validated profitability exists.
- Start knowledge work with open papers, filings, and original principles, using RAG and citations. No copyrighted book corpus is included. Keep document license, provenance, publication/availability timestamps, model version, and prompts for later reproducibility.
- Analyst outputs are untrusted proposals. Keep deterministic risk checks and execution authorization outside LLM control. Source content cannot issue tool instructions or submit trades.
- Preserve decision-time information boundaries. Never expose execution/future bars to analysts. Do not treat LLM historical knowledge as free of contamination.
- No live broker adapter or credentials are required now. Do not place real orders, open broker accounts, or enable live trading as part of setup. Future live operation requires explicit scope and separate acceptance gates in the plan.
- Do not print secrets or commit `.env`, contact identities, databases, raw documents, or market datasets. The user requested repository version control on 2026-10-15: preserve baselines and implementation in meaningful commits/tags; publish to the existing origin without force when access permits. Keep remote and local outcomes distinct.

