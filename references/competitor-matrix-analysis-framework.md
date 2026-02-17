# Competitor Matrix Analysis Framework

## Objective

Identify shared ASO patterns across competitors and convert them into actionable direction.

## Analysis Layers

1. Metadata Layer
- Title patterns (length, numeric claims, punctuation)
- Description length and narrative style
- Pricing and monetization cues

2. Messaging Layer
- Dominant value proposition motifs (speed, AI, trust, collaboration, productivity)
- Semantic theme prevalence (which narrative clusters dominate the category)
- Field-level emphasis (title vs short description vs long description)
- Frequent vocabulary and claim structures
- Common CTA style

3. Market Signal Layer
- Ratings and rating volume distribution
- Category concentration
- Query-seed overlap patterns

4. Visual Layer (manual enrichment)
- Screenshot #1 hook type
- Feature flow sequencing across screenshots
- Design style saturation (minimal, dense, enterprise, playful)

5. Localization Layer (manual + automated)
- Locale coverage breadth
- Translation quality and semantic consistency
- Local-market adaptation depth

## Matrix Method

1. Build auto matrix with:
- iOS path: `aso_competitor_matrix_builder.py`
- Android path: `aso_play_competitor_import_analyzer.py` (CSV import based)
and set `--app-scope`.
2. For Android imports with non-standard headers, run `aso_play_export_normalizer.py` first.
3. Fill manual columns using `assets/competitor-intake-template.csv`.
4. Mark each pattern as:
- common: prevalence >= 60%
- emerging: prevalence 30% to 59%
- niche: prevalence < 30%
5. Decide strategy by combining:
- common patterns to match (table stakes)
- whitespace patterns to differentiate (underused but relevant)

Scope note:

- `ios_only` and `dual`: iTunes-based auto matrix is applicable.
- `android_only`: iTunes-based script should skip; use Play import analyzer with Play-specific exports.

## Decision Rules

- Do not fight on generic claims only.
- Preserve table-stakes patterns users expect.
- Differentiate on a small number of high-credibility claims.
- Tie each claim to product-proof and measurable conversion hypothesis.

## Deliverables

- Competitor matrix (auto + manual)
- Shared pattern summary
- Semantic theme + keyword emphasis summary
- Strategic direction memo:
  - Keep
  - Improve
  - Differentiate
  - Avoid
