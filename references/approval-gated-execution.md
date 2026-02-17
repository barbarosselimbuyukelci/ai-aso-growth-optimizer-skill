# Approval-Gated Execution

## Goal

Ensure the user is informed and approves every step, including analysis stages.

## Runner

Use:

`scripts/run_aso_pipeline.py`

The runner enforces per-step gating:

1. Shows step summary and command
2. Asks user approval
3. Asks if the user wants to add/modify anything
4. Executes only after approval
5. Writes run log with command outputs

## Covered Stages

- Keyword demand analysis
- iOS competitor analysis
- Android export normalization
- Android competitor analysis
- Metadata generation
- CPP/PSL manifest creation
- iOS fastlane push (optional)
- Android fastlane push (optional)

## Non-Interactive Mode

For CI use:

`--auto-approve`

This bypasses prompts but still logs each step output.

## Example

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
  --output-dir run-artifacts/sample-run
```
