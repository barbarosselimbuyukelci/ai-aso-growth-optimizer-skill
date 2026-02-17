# Keyword Volume Estimation (Proxy Model)

## Why A Proxy Model Is Needed

Exact store-native keyword volume is not fully exposed as a public, universal metric.
For ASO operations, demand must be estimated by combining multiple signals.

## Supported Inputs

1. Apple proxy signals
- `apple_popularity`
- `apple_rank` (inverse signal)
- `apple_ttr` (tap-through style proxy)

2. Google Planner signals
- `avg_monthly_searches`
- `competition_index` (or low/medium/high)
- `top_of_page_bid_low/high`

3. AppTweak-like signals
- `apptweak_volume`
- `apptweak_installs`

4. Competitor saturation signals
- `coverage_ratio`
- `document_frequency`

5. iTunes intent mining signals
- `score`
- `app_coverage`

## Scoring Method

The estimator normalizes each metric to 0-100, then builds component scores:

- `apple_score`
- `google_score`
- `apptweak_score`
- `competitor_score`
- `itunes_score`

Final score:

- Weighted average of available components only
- Default weights:
  - Apple: 0.30
  - Google: 0.30
  - AppTweak: 0.25
  - Competitor: 0.10
  - iTunes: 0.05

If a source is missing, remaining weights are re-normalized dynamically.

## Platform Scope Gate (Resource Efficiency)

The estimator supports `--app-scope`:

- `auto`
- `ios_only`
- `android_only`
- `dual`

Behavior:

- `ios_only`: Google component weight is forced to zero.
- `android_only`: Apple and iTunes components are forced to zero.
- `dual`: all components remain eligible.
- `auto`: inferred from keyword platform labels and available sources.

Per-row platform logic in `dual` mode:

- row platform `apple` -> Google component skipped
- row platform `google` -> Apple and iTunes components skipped
- empty row platform -> all scope-eligible components considered

## Confidence Model

`confidence_score` depends on:

- How much total model weight is covered by available sources
- How many source families are present

Use `confidence_band` as:

- `high` >= 75
- `medium` 45 to 74.99
- `low` < 45

## Recommended Usage Pattern

1. Start with all available sources.
2. Filter out keywords with low confidence.
3. Prioritize keywords by:
- high demand score
- medium to high confidence
- intent relevance to product promise
4. Validate top candidates with listing experiments and conversion data.

## Script

Use:

```bash
python scripts/aso_keyword_volume_estimator.py \
  --keywords assets/keyword-volume-keywords-template.csv \
  --app-scope auto \
  --apple-proxy assets/keyword-volume-apple-proxy-template.csv \
  --google-planner assets/keyword-volume-google-planner-template.csv \
  --apptweak assets/keyword-volume-apptweak-template.csv \
  --competitor-terms assets/keyword-volume-competitor-template.csv \
  --itunes-signals assets/keyword-volume-itunes-signals-template.csv \
  --output assets/keyword-volume-estimates.csv \
  --output-json assets/keyword-volume-estimates.json
```
