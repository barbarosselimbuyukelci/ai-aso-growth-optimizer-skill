---
name: aso-growth-optimizer
description: Build policy-safe, high-performance App Store Optimization workflows for Apple App Store and Google Play, including metadata strategy, creative testing, localization, review integrity, and experiment prioritization.
---

# ASO Growth Optimizer

## Overview

Use this skill when the user asks for App Store Optimization strategy, store listing improvements, download growth plans, metadata rewrites, keyword strategy, localization, or ASO experimentation for iOS and Android apps.

This skill is policy-first. It always checks Apple and Google official rules before recommending growth tactics.

## When To Use This Skill

Trigger this skill for requests like:

- "Optimize my App Store and Play Store listing"
- "Increase installs with ASO"
- "Find ASO tricks competitors use"
- "Create an ASO experiment plan"
- "Review metadata for policy risk"
- "Scale ASO for many locales/languages"
- "Automate store metadata sync with fastlane"
- "Mine App Store intent keywords from real listings"
- "Build a competitor ASO matrix and shared pattern map"

## Hard Constraints (Non-Negotiable)

1. Use official policy sources before giving optimization guidance.
2. Never propose fake installs, fake ratings, incentivized reviews, keyword stuffing, or misleading metadata.
3. Distinguish clearly between:
- Policy-compliant advanced tactics
- High-risk abuse patterns seen in the market
4. If guidance depends on recency (policy updates), verify with current official pages.
5. Treat localization quality as a conversion and trust problem, not only translation throughput.
6. At every stage (including analysis), inform the user, request approval, and ask for additional input before execution.

## Workflow

### 1. Intake And Context

Collect:

- App category and core jobs-to-be-done
- Platform scope (`ios_only`, `android_only`, `dual`) and store availability
- Target countries/languages
- Current metadata (title, subtitle, short/full description, keywords)
- Current conversion and retention baselines
- Creative assets (icon, screenshots, preview/video)
- Current localization process (manual/LLM/vendor/hybrid)
- Release operation mode (manual vs CI + fastlane)

### 2. Policy Baseline

Read policy references first:

- Apple: `references/apple-official-guidelines.md`
- Google: `references/google-play-official-guidelines.md`

Generate a quick compliance map:

- Allowed
- Risky/needs rewrite
- Blocked/non-compliant

### 3. Intent Intelligence (Human-Centered)

Model what users actually search and why:

- Problem-to-solution language used by real users
- Category and subcategory terms used by competitors
- Jobs-to-be-done phrases with high install intent

Use:

- `scripts/aso_itunes_intent_keyword_discovery.py`
- `scripts/aso_keyword_volume_estimator.py`
- `references/intent-keyword-intelligence.md`
- `references/keyword-volume-estimation.md`

### 4. Competitor Matrix And Shared Pattern Mining

Build a competitor matrix and extract what top apps do in common:

- Auto-build metadata and messaging matrix
- Quantify motif prevalence and common vocabulary
- Create pairwise similarity map
- Enrich with manual visual/localization observations
- Apply platform scope gate so iOS-only pipelines do not run Android-specific steps

Use:

- `scripts/aso_competitor_matrix_builder.py`
- `scripts/aso_play_export_normalizer.py`
- `scripts/aso_play_competitor_import_analyzer.py`
- `references/competitor-matrix-analysis-framework.md`
- `references/play-export-normalization.md`
- `assets/competitor-intake-template.csv`
- `assets/competitor-matrix-report-template.md`
- `assets/play-competitor-import-template.csv`
- `assets/play-raw-export-template.csv`
- `assets/play-export-mapping-template.json`

### 5. Metadata Architecture

Design metadata by intent clusters:

- Brand intent
- Category intent
- Problem/pain intent
- Competitor-switch intent (without trademark misuse)

Use:

- `scripts/aso_metadata_guardrail_check.py`
- `assets/aso-metadata-audit-template.md`

### 6. Global Localization And Semantic Integrity

For each target locale:

- Translate with glossary and protected terms
- Validate semantic parity, placeholders, and numeric tokens
- Check field-length limits after translation
- Flag suspicious literal copies and mistranslations

Use:

- `scripts/aso_translator_bridge.py`
- `scripts/aso_translation_semantic_audit.py`
- `assets/translation-batch-template.json`
- `references/localization-semantic-integrity.md`

### 7. Creative And Listing Experiments

Build test backlog for:

- Icon
- First screenshots
- Short message hierarchy
- Localized listing variants

Use:

- `scripts/aso_experiment_prioritizer.py`
- `assets/aso-experiment-backlog-template.csv`

### 8. Abuse Pattern Risk Scan

Document risky market behavior and avoid it:

- Fake ratings/reviews/install bursts
- Misleading claims in metadata or creatives
- Spammy keyword repetition and unrelated terms

See:

- `references/abuse-patterns-and-enforcement-risks.md`

### 9. Max-Download Strategy (Policy-Safe)

Produce a structured growth plan:

- Baseline fixes (metadata quality + policy hygiene)
- Intent-matched custom pages/listings
- Localization and seasonal/event loop
- Experiment cadence and stopping rules
- Retention-aware ASO metrics

See:

- `references/max-download-aso-strategy.md`

### 10. Automation Bridge (fastlane + CI)

Automate metadata/screenshot synchronization and release-safe operations:

- iOS metadata sync via `deliver`
- Android listing sync via `supply`
- Dry-run first, then execute in CI
- Scope-gated invocation to avoid running the wrong platform lane

Use:

- `scripts/aso_fastlane_bridge.py`
- `assets/fastlane-lane-template.rb`
- `references/automation-fastlane-integration.md`

### 11. Approval-Gated End-To-End Run

Run the pipeline with mandatory user checkpoints at every step:

- Analysis steps
- Metadata generation
- CPP/PSL preparation
- Optional fastlane push

Use:

- `scripts/run_aso_pipeline.py`
- `scripts/aso_metadata_generator.py`
- `scripts/aso_cpp_psl_builder.py`
- `references/approval-gated-execution.md`
- `assets/metadata-generation-input-template.json`

## Outputs

For each run, produce:

1. Compliance risk report
2. Competitor matrix and shared-pattern summary
3. Keyword demand estimate table with confidence bands
4. Metadata recommendation set (Apple + Google)
5. Experiment backlog with priority scores
6. Abuse-risk prevention checklist
7. 30/60 day ASO execution plan with success metrics
8. Localization semantic QA report by locale
9. Automation handoff notes for fastlane/CI

## Scripts

### `scripts/aso_metadata_guardrail_check.py`

Purpose:

- Validate metadata limits and obvious policy risk patterns for Apple/Google.

Usage:

```bash
python scripts/aso_metadata_guardrail_check.py --input metadata.json
```

### `scripts/aso_experiment_prioritizer.py`

Purpose:

- Rank ASO hypotheses with ICE scoring (Impact, Confidence, Ease).

Usage:

```bash
python scripts/aso_experiment_prioritizer.py --input assets/aso-experiment-backlog-template.csv
```

### `scripts/aso_itunes_intent_keyword_discovery.py`

Purpose:

- Collect App Store listing language from iTunes Search API and suggest intent-aligned keyword candidates.

Usage:

```bash
python scripts/aso_itunes_intent_keyword_discovery.py --seeds "note taking,voice notes" --country us --output keywords.csv
```

### `scripts/aso_competitor_matrix_builder.py`

Purpose:

- Build competitor matrix, common pattern prevalence, term coverage, and similarity map.

Usage:

```bash
python scripts/aso_competitor_matrix_builder.py --seeds "note taking,meeting notes" --app-scope ios_only --country us --output-dir out --prefix notes_competitors
```

### `scripts/aso_play_competitor_import_analyzer.py`

Purpose:

- Build Play/Android competitor matrix from imported CSV data when app scope includes Android.

Usage:

```bash
python scripts/aso_play_competitor_import_analyzer.py --input assets/play-competitor-import-template.csv --app-scope android_only --output-dir out --prefix play_competitors
```

### `scripts/aso_play_export_normalizer.py`

Purpose:

- Normalize heterogeneous Play export CSV columns into the standard analyzer schema.

Usage:

```bash
python scripts/aso_play_export_normalizer.py --input assets/play-raw-export-template.csv --output assets/play-competitor-import-normalized.csv --print-columns
python scripts/aso_play_export_normalizer.py --input assets/play-raw-export-template.csv --mapping-json assets/play-export-mapping-template.json --output assets/play-competitor-import-normalized.csv
```

### `scripts/aso_keyword_volume_estimator.py`

Purpose:

- Blend Apple/Google/AppTweak/competitor/iTunes proxy signals into a normalized keyword demand estimate.

Usage:

```bash
python scripts/aso_keyword_volume_estimator.py --keywords assets/keyword-volume-keywords-template.csv --app-scope auto --apple-proxy assets/keyword-volume-apple-proxy-template.csv --google-planner assets/keyword-volume-google-planner-template.csv --apptweak assets/keyword-volume-apptweak-template.csv --competitor-terms assets/keyword-volume-competitor-template.csv --itunes-signals assets/keyword-volume-itunes-signals-template.csv --output keyword-volume-estimates.csv
```

### `scripts/aso_metadata_generator.py`

Purpose:

- Generate new metadata variants and fastlane metadata files from structured intent input.

Usage:

```bash
python scripts/aso_metadata_generator.py --input assets/metadata-generation-input-template.json --output-dir run-artifacts/metadata-run
```

### `scripts/aso_cpp_psl_builder.py`

Purpose:

- Build CPP/PSL manifests from generated metadata bundle.

Usage:

```bash
python scripts/aso_cpp_psl_builder.py --input-bundle run-artifacts/metadata-run/metadata_bundle.json --output-dir run-artifacts/metadata-run --app-scope dual
```

### `scripts/aso_translator_bridge.py`

Purpose:

- Generate per-locale translations via external translator command or LibreTranslate-compatible endpoint.

Usage:

```bash
python scripts/aso_translator_bridge.py --input assets/translation-batch-template.json --provider command --command-template "mytranslator --source {source_locale} --target {target_locale} --text \"{text}\"" --output translated.json
```

### `scripts/aso_translation_semantic_audit.py`

Purpose:

- Validate translation completeness, placeholders, numeric tokens, protected terms, and length constraints.

Usage:

```bash
python scripts/aso_translation_semantic_audit.py --input translated.json --platform apple --output qa-report.json
```

### `scripts/aso_fastlane_bridge.py`

Purpose:

- Generate or execute policy-safe fastlane commands for listing metadata operations (dry-run by default).

Usage:

```bash
python scripts/aso_fastlane_bridge.py --platform ios --lane deliver --app-scope ios_only --app-identifier com.example.app --metadata-path fastlane/metadata
python scripts/aso_fastlane_bridge.py --platform android --lane supply --app-scope dual --package-name com.example.app --metadata-path fastlane/metadata/android --execute
```

### `scripts/run_aso_pipeline.py`

Purpose:

- Execute analysis + generation + CPP/PSL + optional push with per-step user approval and notes.

Usage:

```bash
python scripts/run_aso_pipeline.py --keyword-input assets/keyword-volume-keywords-template.csv --apple-proxy assets/keyword-volume-apple-proxy-template.csv --google-planner assets/keyword-volume-google-planner-template.csv --apptweak assets/keyword-volume-apptweak-template.csv --competitor-terms assets/keyword-volume-competitor-template.csv --itunes-signals assets/keyword-volume-itunes-signals-template.csv --ios-seeds "note taking,meeting notes" --play-raw-export assets/play-raw-export-template.csv --play-mapping-json assets/play-export-mapping-template.json --metadata-input assets/metadata-generation-input-template.json --output-dir run-artifacts/sample-run
```

## Notes On Tooling

Useful tool set for agents using this skill:

- Reliable web browsing for official policy verification
- CSV handling for experiment backlog and scoring
- Optional analytics connectors (App Store Connect / Play Console exports)
- Text linting scripts for metadata guardrails
- Translation provider integration (LLM, vendor API, or in-house service)
- Release automation stack (`ruby`, `bundler`, `fastlane`)
- iTunes Search API data ingestion for intent discovery and competitor mapping

If connectors are unavailable, continue with offline templates and manual metric inputs.
