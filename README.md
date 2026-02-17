# AI ASO Growth Optimizer Skill

Ship higher-converting App Store and Play Store listings faster, with policy-safe automation.

This repository gives you a complete ASO operating system:

- Strategy + analysis
- Metadata generation
- CPP/PSL preparation
- Approval-gated execution
- Fastlane-ready publishing flow

## Why This Repo

Most ASO workflows break in one of three places:

1. Good ideas, weak execution
2. Fast execution, policy risk
3. Strong analysis, no shipping path

This skill closes all three gaps.  
You get an end-to-end flow from intent discovery to production-ready metadata artifacts.

## What It Does

The skill runs an end-to-end ASO workflow:

1. Keyword demand estimation
2. Competitor pattern analysis (iOS + Android paths)
3. Metadata generation
4. CPP/PSL manifest preparation
5. Optional fastlane publishing (scope-gated)
6. Approval-gated execution at every step (including analysis)

## What Makes It Different

- **Policy-first by design**: Apple/Google guardrails are built into the workflow.
- **Scope-aware execution**: iOS-only, Android-only, dual mode. No wasted steps.
- **Real competitor intelligence**: matrix, motif prevalence, similarity, shared vocabulary.
- **Operational outputs**: not just advice, but files you can run and publish.
- **Human-in-the-loop control**: every major step can require explicit approval.

## Repo Structure

- `SKILL.md`: Core skill behavior for Codex
- `scripts/`: Executable automation scripts
- `assets/`: Input/output templates
- `references/`: Process and policy documentation

## Requirements

- Python 3.9+
- (Optional for publishing) Ruby + Bundler + fastlane

## Quick Start (5 Minutes)

Run a full sample pipeline:

```bash
python scripts/run_aso_pipeline.py \
  --keyword-input assets/keyword-volume-keywords-template.csv \
  --apple-proxy assets/keyword-volume-apple-proxy-template.csv \
  --google-planner assets/keyword-volume-google-planner-template.csv \
  --apptweak assets/keyword-volume-apptweak-template.csv \
  --competitor-terms assets/keyword-volume-competitor-template.csv \
  --itunes-signals assets/keyword-volume-itunes-signals-template.csv \
  --ios-seeds "note taking,meeting notes" \
  --play-raw-export assets/play-raw-export-template.csv \
  --play-mapping-json assets/play-export-mapping-template.json \
  --metadata-input assets/metadata-generation-input-template.json \
  --output-dir run-artifacts/my-run \
  --app-scope dual
```

By default, the pipeline asks for approval at every step (including analysis).

For non-interactive runs:

```bash
python scripts/run_aso_pipeline.py ... --auto-approve
```

## Common Use Cases

### 1) iOS-Only App Teams

- Analyze iOS keyword demand
- Build iOS competitor matrix
- Generate App Store metadata + CPP manifest
- Push with `deliver` (optional)

### 2) Cross-Platform Teams

- Run iOS + Play competitor analysis
- Build keyword scoring with multiple sources
- Generate Apple + Google metadata variants
- Prepare CPP + PSL artifacts
- Push with fastlane (optional)

## iOS-Only Example

```bash
python scripts/run_aso_pipeline.py \
  --keyword-input assets/keyword-volume-keywords-ios-only-template.csv \
  --apple-proxy assets/keyword-volume-apple-proxy-template.csv \
  --apptweak assets/keyword-volume-apptweak-template.csv \
  --competitor-terms assets/keyword-volume-competitor-template.csv \
  --itunes-signals assets/keyword-volume-itunes-signals-template.csv \
  --ios-seeds "note taking,meeting notes" \
  --metadata-input assets/metadata-generation-input-template.json \
  --output-dir run-artifacts/ios-run \
  --app-scope ios_only
```

## Optional Publishing (Fastlane)

Add publish flags to the pipeline:

- `--push-ios --app-identifier com.example.app`
- `--push-android --package-name com.example.app`
- `--execute-push` to actually execute (otherwise dry-run)

Example:

```bash
python scripts/run_aso_pipeline.py ... \
  --push-ios --app-identifier com.example.app \
  --push-android --package-name com.example.app \
  --execute-push
```

## Core Scripts

- `scripts/run_aso_pipeline.py`: Approval-gated orchestrator
- `scripts/aso_keyword_volume_estimator.py`: Multi-source demand scoring
- `scripts/aso_competitor_matrix_builder.py`: iOS competitor matrix (iTunes data)
- `scripts/aso_play_export_normalizer.py`: Normalize raw Play exports
- `scripts/aso_play_competitor_import_analyzer.py`: Android competitor matrix from CSV
- `scripts/aso_metadata_generator.py`: Generate metadata + fastlane files
- `scripts/aso_cpp_psl_builder.py`: Build CPP/PSL manifests
- `scripts/aso_fastlane_bridge.py`: Scope-aware fastlane command bridge

## Outputs You Can Use Immediately

Each run writes outputs under your chosen `--output-dir`, typically:

- `analysis/` (keyword + competitor analysis outputs)
- `metadata_bundle.json`
- `cpp_manifest.json`
- `psl_manifest.json`
- `fastlane/metadata/...`
- `pipeline_run_log.json`
- `pipeline_human_summary.md` (human-readable run explanation)

## Notes

- This system uses demand proxies (not exact store-native keyword volume).
- Scope gating prevents unnecessary iOS/Android steps.
- See `references/` for detailed methodology and policy guidance.

## If You Want To Contribute

1. Fork the repo
2. Add or improve a script/template/reference
3. Open a PR with sample input/output

Contributions that improve reliability, policy safety, and execution speed are especially welcome.
