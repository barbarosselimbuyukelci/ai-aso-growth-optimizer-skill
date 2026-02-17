# Localization Semantic Integrity

## Goal

Ensure each translated listing keeps meaning, persuasion quality, and policy safety.

## Quality Dimensions

1. Semantic parity
- Translation should preserve core promise and user outcome.

2. Terminology consistency
- Product terms, feature names, and glossary terms stay stable.

3. Structural integrity
- Placeholders (`{name}`, `%s`, `%d`) and numbers remain correct.

4. Constraint fit
- Title/subtitle/short-description limits remain valid post-translation.

5. Conversion language quality
- Copy sounds native for target market, not literal and robotic.

## Recommended Process

1. Generate translation drafts.
2. Run `aso_translation_semantic_audit.py` on all locales.
3. Route warning-heavy locales to human linguist review.
4. Re-test metadata limits and policy guardrails after edits.
5. Promote only locales that pass semantic and length checks.

## Risk Signals

- Literal source copy for complex phrases
- Missing protected terms or brand terms
- Broken placeholders
- Numerically inconsistent claims
- Over-length fields causing truncation
