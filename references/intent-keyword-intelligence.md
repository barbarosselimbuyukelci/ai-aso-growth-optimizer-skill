# Intent Keyword Intelligence

Last verified: 2026-02-17

## Goal

Predict what users might search to discover the app, then map those intents to compliant metadata and creative strategy.

## Data Sources

1. iTunes Search API (software entity)
- Endpoint: `https://itunes.apple.com/search`
- Primary fields: `trackName`, `description`, `genres`, `sellerName`, `primaryGenreName`

2. Internal app analytics
- Search term reports where available
- Store listing conversion metrics per locale

3. User language artifacts
- Reviews
- Support tickets
- Onboarding survey free-text answers

## Intent Taxonomy

Use at least these buckets:

- Job intent: user wants to complete a task
- Pain intent: user wants to solve a frustration
- Outcome intent: user wants a result or state
- Switch intent: user compares alternatives

## Workflow

1. Start with 5 to 15 seed phrases.
2. Pull competitor listing language with iTunes Search API.
3. Extract repeated meaningful terms and co-occurrences.
4. Cluster terms by intent bucket.
5. Estimate keyword demand using proxy signals.
6. Attach each cluster to metadata fields and creative hypotheses.
7. Run policy check before shipping changes.

## Demand Estimation

Use `scripts/aso_keyword_volume_estimator.py` to merge:

- Apple proxy signals
- Google Planner exports
- AppTweak-like metrics
- Competitor coverage
- iTunes intent signal strength

This produces:

- `estimated_demand_score` (0-100)
- `confidence_score` and `confidence_band`
- per-source component scores for explainability

Run with scope-aware mode to avoid unnecessary sources:

- `--app-scope ios_only` for iOS-only products
- `--app-scope dual` for iOS + Android products
- `--app-scope auto` when platform labels are present in keyword input

## Guardrails

- Do not infer trademark-safe usage automatically; review manually.
- Do not copy competitor claims verbatim.
- Prefer user language over internal jargon.
