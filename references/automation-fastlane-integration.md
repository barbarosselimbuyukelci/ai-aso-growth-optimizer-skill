# Automation Fastlane Integration

## Goal

Move ASO operations from manual edits to repeatable, auditable automation.

## Core fastlane Components

1. iOS (`deliver`)
- Upload and manage App Store metadata and screenshots.

2. Android (`supply`)
- Upload and manage Google Play listing metadata and assets.

## Operational Pattern

1. Keep metadata in versioned files.
2. Run dry-run command generation first.
3. Validate metadata with guardrail scripts.
4. Execute fastlane only after compliance checks.
5. Store command output as release evidence.
6. Apply platform scope gate (`ios_only`, `android_only`, `dual`) before lane invocation.

## Minimum Environment

- Ruby
- Bundler
- fastlane
- App store credentials or API key setup

## Safety Rules

- Default to dry-run during planning.
- Keep platform credentials out of repository.
- Never bypass policy checks because automation exists.
- When scope and lane platform mismatch, prefer skip mode over blind execution.
