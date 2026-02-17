#!/usr/bin/env python3
"""
Semantic and structural QA for translated ASO metadata.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Set

APPLE_LIMITS = {
    "title": 30,
    "subtitle": 30,
    "description": 4000,
}

GOOGLE_LIMITS = {
    "title": 30,
    "short_description": 80,
    "description": 4000,
}

PLACEHOLDER_RE = re.compile(r"(\{[a-zA-Z0-9_]+\}|\{\{[a-zA-Z0-9_]+\}\}|%[sd])")
NUMBER_RE = re.compile(r"\d+")
ALPHA_RE = re.compile(r"[A-Za-z]{4,}")
WORD_RE = re.compile(r"[A-Za-z]{3,}")

COMMON_ENGLISH_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "your",
    "track",
    "easy",
    "fast",
    "daily",
    "results",
    "weight",
    "health",
    "timer",
    "plan",
    "goals",
    "habit",
    "meal",
    "smart",
    "quick",
    "simple",
    "best",
    "new",
    "improve",
    "progress",
    "analytics",
}


def load_payload(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    return data


def get_limit(platform: str, field: str) -> int:
    if platform == "apple":
        return APPLE_LIMITS.get(field, 999999)
    if platform == "google":
        return GOOGLE_LIMITS.get(field, 999999)
    return 999999


def placeholders(text: str) -> Set[str]:
    return set(PLACEHOLDER_RE.findall(text))


def numbers(text: str) -> List[str]:
    return NUMBER_RE.findall(text)


def words(text: str) -> List[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def main() -> int:
    parser = argparse.ArgumentParser(description="ASO translation semantic audit")
    parser.add_argument("--input", required=True, help="Input translated JSON path")
    parser.add_argument("--platform", choices=["apple", "google"], default="apple")
    parser.add_argument("--output", help="Optional output JSON report path")
    parser.add_argument("--fail-on-warn", action="store_true", help="Return non-zero when warnings exist")
    args = parser.parse_args()

    try:
        payload = load_payload(args.input)
    except Exception as exc:
        print(f"ERROR: failed to read input: {exc}")
        return 2

    entries = payload.get("entries", [])
    protected_terms = [str(x) for x in payload.get("protected_terms", [])]
    target_locales = [str(x) for x in payload.get("target_locales", [])]

    if not isinstance(entries, list) or not entries:
        print("ERROR: entries must be a non-empty list")
        return 2

    report: Dict[str, Any] = {
        "platform": args.platform,
        "summary": {"entries": len(entries), "locales": len(target_locales), "warnings": 0, "errors": 0},
        "locale_report": {},
    }

    for locale in target_locales:
        report["locale_report"][locale] = {"errors": [], "warnings": []}

    for entry in entries:
        entry_id = str(entry.get("id", ""))
        field = str(entry.get("field", ""))
        source_text = str(entry.get("source_text", ""))
        source_placeholders = placeholders(source_text)
        source_numbers = numbers(source_text)
        translations = entry.get("translations", {})

        if not isinstance(translations, dict):
            continue

        for locale in target_locales:
            target = str(translations.get(locale, "")).strip()
            loc_report = report["locale_report"][locale]

            if not target:
                loc_report["errors"].append(f"{entry_id}: missing translation")
                continue

            limit = get_limit(args.platform, field)
            if len(target) > limit:
                loc_report["errors"].append(
                    f"{entry_id}: {field} exceeds {args.platform} limit ({len(target)}/{limit})"
                )

            target_placeholders = placeholders(target)
            if source_placeholders != target_placeholders:
                loc_report["errors"].append(
                    f"{entry_id}: placeholder mismatch source={sorted(source_placeholders)} target={sorted(target_placeholders)}"
                )

            target_numbers = numbers(target)
            if source_numbers != target_numbers:
                loc_report["warnings"].append(
                    f"{entry_id}: numeric token mismatch source={source_numbers} target={target_numbers}"
                )

            # If source has substantial alphabetic text and target equals source, likely untranslated.
            if target == source_text and ALPHA_RE.search(source_text):
                loc_report["warnings"].append(f"{entry_id}: translation identical to source text")

            # Literal translation risk: excessively high lexical overlap with source in non-English locales.
            if not locale.lower().startswith("en"):
                source_words = set(words(source_text))
                target_words = set(words(target))
                if source_words:
                    overlap = len(source_words.intersection(target_words)) / max(1, len(source_words))
                    if overlap >= 0.85:
                        loc_report["warnings"].append(
                            f"{entry_id}: high source-target lexical overlap ({overlap:.2f}), possible literal translation"
                        )

                # Cultural adaptation risk proxy: target copy remains heavily English.
                target_word_list = words(target)
                if target_word_list:
                    english_hits = sum(1 for w in target_word_list if w in COMMON_ENGLISH_WORDS)
                    english_ratio = english_hits / len(target_word_list)
                    if english_ratio >= 0.40:
                        loc_report["warnings"].append(
                            f"{entry_id}: high English word ratio ({english_ratio:.2f}) for locale {locale}"
                        )

            for term in protected_terms:
                if term and term in source_text and term not in target:
                    loc_report["warnings"].append(f"{entry_id}: protected term '{term}' missing")

    for locale in target_locales:
        loc_report = report["locale_report"][locale]
        report["summary"]["warnings"] += len(loc_report["warnings"])
        report["summary"]["errors"] += len(loc_report["errors"])

    output = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")

    print(output)

    if report["summary"]["errors"] > 0:
        return 1
    if args.fail_on_warn and report["summary"]["warnings"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
