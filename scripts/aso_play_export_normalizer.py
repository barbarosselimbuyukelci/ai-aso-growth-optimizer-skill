#!/usr/bin/env python3
"""
Normalize heterogeneous Play competitor export CSV files into a standard schema
consumed by aso_play_competitor_import_analyzer.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from typing import Dict, List, Optional

TARGET_COLUMNS = [
    "app_name",
    "package_name",
    "developer",
    "category",
    "locale",
    "country",
    "short_description",
    "full_description",
    "avg_rating",
    "rating_count",
    "installs",
    "price",
    "url",
]

ALIASES = {
    "app_name": ["app_name", "app", "title", "name", "app title", "app_title"],
    "package_name": ["package_name", "package", "package id", "bundle_id", "app_id", "id"],
    "developer": ["developer", "developer_name", "seller", "publisher", "company"],
    "category": ["category", "genre", "primary_genre", "app_category"],
    "locale": ["locale", "language", "lang"],
    "country": ["country", "store_country", "market", "region"],
    "short_description": ["short_description", "short_desc", "tagline", "subtitle", "short text"],
    "full_description": ["full_description", "long_description", "description", "desc"],
    "avg_rating": ["avg_rating", "rating", "average_rating", "score"],
    "rating_count": ["rating_count", "ratings_count", "reviews_count", "user_ratings_total", "votes"],
    "installs": ["installs", "install_count", "downloads", "download_count"],
    "price": ["price", "app_price", "list_price"],
    "url": ["url", "store_url", "play_url", "listing_url", "app_url"],
}


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def read_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pick_source_column(headers: List[str], candidates: List[str]) -> Optional[str]:
    normalized_map = {normalize_header(h): h for h in headers}
    for c in candidates:
        key = normalize_header(c)
        if key in normalized_map:
            return normalized_map[key]
    return None


def build_mapping(headers: List[str], override: Dict[str, str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for target in TARGET_COLUMNS:
        if target in override and override[target]:
            mapping[target] = override[target]
            continue
        source = pick_source_column(headers, ALIASES.get(target, [target]))
        if source:
            mapping[target] = source
    return mapping


def clean_numeric(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    s = s.replace(",", "")
    return s


def normalize_value(target: str, value: str) -> str:
    raw = str(value or "").strip()
    if target in {"avg_rating", "rating_count", "installs", "price"}:
        return clean_numeric(raw)
    return raw


def load_override_mapping(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("mapping json must be an object")
    out: Dict[str, str] = {}
    for k, v in data.items():
        if k in TARGET_COLUMNS and isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize Play competitor export CSV columns")
    parser.add_argument("--input", required=True, help="Raw input CSV path")
    parser.add_argument("--output", required=True, help="Normalized output CSV path")
    parser.add_argument("--mapping-json", help="Optional JSON mapping override: {\"target\":\"source\"}")
    parser.add_argument("--strict", action="store_true", help="Fail if core columns cannot be resolved")
    parser.add_argument("--print-columns", action="store_true", help="Print detected input columns and mapping")
    args = parser.parse_args()

    try:
        rows = read_csv(args.input)
    except Exception as exc:
        print(f"ERROR: failed to read input csv: {exc}")
        return 2

    if not rows:
        print("ERROR: input csv is empty")
        return 2

    headers = list(rows[0].keys())

    try:
        override = load_override_mapping(args.mapping_json)
    except Exception as exc:
        print(f"ERROR: failed to load mapping override: {exc}")
        return 2

    mapping = build_mapping(headers, override)

    core_targets = ["app_name", "full_description"]
    missing_core = [t for t in core_targets if t not in mapping]
    if args.strict and missing_core:
        print("ERROR: missing required mapped columns: " + ", ".join(missing_core))
        return 2

    output_rows: List[Dict[str, str]] = []
    for row in rows:
        out: Dict[str, str] = {}
        for target in TARGET_COLUMNS:
            source_col = mapping.get(target, "")
            value = row.get(source_col, "") if source_col else ""
            out[target] = normalize_value(target, value)
        output_rows.append(out)

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TARGET_COLUMNS)
        writer.writeheader()
        for row in output_rows:
            writer.writerow(row)

    if args.print_columns:
        print("INPUT_COLUMNS:")
        for c in headers:
            print(f"- {c}")
        print("MAPPING:")
        for t in TARGET_COLUMNS:
            print(f"- {t}: {mapping.get(t, '')}")

    print(f"Wrote normalized csv: {args.output}")
    print(f"Rows: {len(output_rows)}")
    if missing_core:
        print("WARNING: missing core mapped columns: " + ", ".join(missing_core))
    return 0


if __name__ == "__main__":
    sys.exit(main())

