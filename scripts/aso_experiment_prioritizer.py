#!/usr/bin/env python3
"""
Prioritize ASO experiments with ICE scoring.

Input CSV columns:
- hypothesis
- impact (1-10)
- confidence (1-10)
- ease (1-10)
- optional extra columns are preserved
"""

from __future__ import annotations

import argparse
import csv
import sys
from typing import Dict, List


def parse_float(value: str, field: str, row_idx: int) -> float:
    try:
        v = float(value)
    except Exception:
        raise ValueError(f"Row {row_idx}: invalid {field} '{value}'")
    if v < 0:
        raise ValueError(f"Row {row_idx}: {field} must be >= 0")
    return v


def load_rows(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    required = {"hypothesis", "impact", "confidence", "ease"}
    missing = required - set(fieldnames)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="ASO experiment prioritizer (ICE)")
    parser.add_argument("--input", required=True, help="Input CSV path")
    parser.add_argument("--output", help="Optional output CSV path")
    args = parser.parse_args()

    try:
        rows = load_rows(args.input)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2

    scored = []
    for idx, row in enumerate(rows, start=2):
        try:
            impact = parse_float(row.get("impact", ""), "impact", idx)
            confidence = parse_float(row.get("confidence", ""), "confidence", idx)
            ease = parse_float(row.get("ease", ""), "ease", idx)
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 2

        ice = impact * confidence * ease
        enriched = dict(row)
        enriched["ice_score"] = f"{ice:.2f}"
        scored.append((ice, enriched))

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [item for _, item in scored]

    if args.output:
        fieldnames = list(ranked[0].keys()) if ranked else ["hypothesis", "impact", "confidence", "ease", "ice_score"]
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in ranked:
                writer.writerow(row)

    print("rank,hypothesis,impact,confidence,ease,ice_score")
    for i, row in enumerate(ranked, start=1):
        print(
            f"{i},{row.get('hypothesis','').replace(',', ';')},{row.get('impact','')},{row.get('confidence','')},{row.get('ease','')},{row.get('ice_score','')}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
