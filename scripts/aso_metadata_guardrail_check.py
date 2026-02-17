#!/usr/bin/env python3
"""
ASO metadata guardrail checker.

Checks platform-specific metadata limits and flags common policy-risk patterns.
This script is heuristic and should be used alongside manual policy review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Tuple

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

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "]",
    flags=re.UNICODE,
)

RANKING_CLAIM_RE = re.compile(r"\b(#\s?1|number\s?1|no\.?\s?1|top\s?1|best)\b", re.IGNORECASE)
PROMO_RE = re.compile(r"\b(free|discount|sale|deal|%\s?off|limited\s?time)\b", re.IGNORECASE)
REPEATED_PUNCT_RE = re.compile(r"([!?.])\1{1,}")
TOKEN_RE = re.compile(r"[a-z0-9]+")


def load_input(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig") as f:
        payload = json.load(f)
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return payload
    raise ValueError("Input must be a JSON object or array of objects")


def text_len(value: Any) -> int:
    return len(str(value or ""))


def utf8_len(value: Any) -> int:
    return len(str(value or "").encode("utf-8"))


def repeated_tokens(text: str, threshold: int = 3) -> List[Tuple[str, int]]:
    counts: Dict[str, int] = {}
    for token in TOKEN_RE.findall(text.lower()):
        if len(token) < 3:
            continue
        counts[token] = counts.get(token, 0) + 1
    return sorted([(t, c) for t, c in counts.items() if c >= threshold], key=lambda x: (-x[1], x[0]))


def contains_competitor_terms(text: str, terms: List[str]) -> List[str]:
    found = []
    low = text.lower()
    for term in terms:
        t = term.strip().lower()
        if t and t in low:
            found.append(term)
    return found


def check_limits(item: Dict[str, Any], errors: List[str]) -> None:
    platform = str(item.get("platform", "")).strip().lower()
    if platform == "apple":
        for field, max_len in APPLE_LIMITS.items():
            if text_len(item.get(field, "")) > max_len:
                errors.append(f"{field} exceeds Apple limit ({max_len})")
        keywords = item.get("keywords", "")
        if isinstance(keywords, list):
            keywords = ",".join(str(x) for x in keywords)
        if utf8_len(keywords) > 100:
            errors.append("keywords exceeds Apple 100-byte limit")
    elif platform == "google":
        for field, max_len in GOOGLE_LIMITS.items():
            if text_len(item.get(field, "")) > max_len:
                errors.append(f"{field} exceeds Google Play limit ({max_len})")
    else:
        errors.append("platform must be 'apple' or 'google'")


def check_risks(item: Dict[str, Any], warnings: List[str]) -> None:
    title = str(item.get("title", ""))
    subtitle = str(item.get("subtitle", ""))
    short_description = str(item.get("short_description", ""))
    description = str(item.get("description", ""))
    developer_name = str(item.get("developer_name", ""))

    condensed = " ".join([title, subtitle, short_description, description])

    if RANKING_CLAIM_RE.search(title) or RANKING_CLAIM_RE.search(developer_name):
        warnings.append("Potential ranking claim in title/developer_name")

    if PROMO_RE.search(title) or PROMO_RE.search(developer_name):
        warnings.append("Potential pricing/promo claim in title/developer_name")

    if EMOJI_RE.search(title) or EMOJI_RE.search(developer_name):
        warnings.append("Emoji detected in title/developer_name")

    if REPEATED_PUNCT_RE.search(title):
        warnings.append("Repeated punctuation in title")

    repeats = repeated_tokens(condensed)
    if repeats:
        warnings.append(
            "Possible keyword stuffing tokens: "
            + ", ".join(f"{token}({count})" for token, count in repeats[:8])
        )

    competitor_terms = item.get("competitor_terms", [])
    if isinstance(competitor_terms, list) and competitor_terms:
        found = contains_competitor_terms(condensed, [str(t) for t in competitor_terms])
        if found:
            warnings.append("Competitor terms present: " + ", ".join(found))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ASO metadata guardrails from JSON input")
    parser.add_argument("--input", required=True, help="Path to metadata JSON file")
    parser.add_argument("--output", help="Optional path to write JSON report")
    args = parser.parse_args()

    try:
        entries = load_input(args.input)
    except Exception as exc:
        print(f"ERROR: failed to read input: {exc}")
        return 2

    report: Dict[str, Any] = {"items": [], "summary": {"total": 0, "error_items": 0, "warning_items": 0}}

    for idx, item in enumerate(entries, start=1):
        errors: List[str] = []
        warnings: List[str] = []

        check_limits(item, errors)
        check_risks(item, warnings)

        status = "pass"
        if errors:
            status = "fail"
        elif warnings:
            status = "warn"

        report["items"].append(
            {
                "index": idx,
                "platform": item.get("platform"),
                "app": item.get("app_name"),
                "status": status,
                "errors": errors,
                "warnings": warnings,
            }
        )

    report["summary"]["total"] = len(report["items"])
    report["summary"]["error_items"] = sum(1 for i in report["items"] if i["errors"])
    report["summary"]["warning_items"] = sum(1 for i in report["items"] if i["warnings"])

    output = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")

    print(output)

    if report["summary"]["error_items"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


