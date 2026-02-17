#!/usr/bin/env python3
"""
Build CPP/PSL manifests from generated metadata bundle.

This script prepares operational manifests that can be used by:
- App Store Connect API workflows (CPP)
- Play listing workflows (PSL/CSL operational plan)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    return data


def grouped_by_intent(locales: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in locales:
        cluster = str(item.get("intent_cluster", "general-intent")).strip() or "general-intent"
        groups[cluster].append(item)
    return groups


def build_cpp_manifest(locales: List[Dict[str, Any]], max_pages: int) -> Dict[str, Any]:
    groups = grouped_by_intent(locales)
    pages: List[Dict[str, Any]] = []
    for idx, (cluster, items) in enumerate(groups.items(), start=1):
        if len(pages) >= max_pages:
            break
        pages.append(
            {
                "page_id": f"cpp-{idx:02d}",
                "reference_name": cluster.replace("_", "-"),
                "intent_cluster": cluster,
                "locales": [
                    {
                        "locale": str(i.get("locale", "")),
                        "title": i.get("apple", {}).get("title", ""),
                        "subtitle": i.get("apple", {}).get("subtitle", ""),
                        "description": i.get("apple", {}).get("description", ""),
                        "keywords": i.get("apple", {}).get("keywords", ""),
                    }
                    for i in items
                ],
                "creative_brief": {
                    "hook": f"Primary hook for {cluster.replace('-', ' ')}",
                    "screenshot_story": [
                        "Problem framing",
                        "Feature proof",
                        "Outcome and trust",
                    ],
                },
            }
        )
    return {"type": "cpp_manifest", "pages": pages}


def build_psl_manifest(locales: List[Dict[str, Any]], max_pages: int) -> Dict[str, Any]:
    groups = grouped_by_intent(locales)
    listings: List[Dict[str, Any]] = []
    for idx, (cluster, items) in enumerate(groups.items(), start=1):
        if len(listings) >= max_pages:
            break
        listings.append(
            {
                "listing_id": f"psl-{idx:02d}",
                "intent_cluster": cluster,
                "locales": [
                    {
                        "locale": str(i.get("locale", "")),
                        "title": i.get("google", {}).get("title", ""),
                        "short_description": i.get("google", {}).get("short_description", ""),
                        "description": i.get("google", {}).get("description", ""),
                    }
                    for i in items
                ],
                "targeting_hint": {
                    "query_theme": cluster.replace("-", " "),
                    "audience": "intent-matched acquisition",
                },
            }
        )
    return {"type": "psl_manifest", "listings": listings}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def infer_scope(app_scope: str) -> str:
    scope = str(app_scope or "").strip().lower()
    if scope in {"ios_only", "android_only", "dual"}:
        return scope
    return "dual"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CPP/PSL manifests from metadata bundle")
    parser.add_argument("--input-bundle", required=True, help="Path to metadata_bundle.json")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--app-scope", choices=["auto", "ios_only", "android_only", "dual"], default="auto")
    parser.add_argument("--max-pages", type=int, default=10, help="Max CPP/PSL pages/listings")
    args = parser.parse_args()

    try:
        bundle = load_json(args.input_bundle)
    except Exception as exc:
        print(f"ERROR: failed to load bundle: {exc}")
        return 2

    locales = bundle.get("locales", [])
    if not isinstance(locales, list) or not locales:
        print("ERROR: bundle has no locales")
        return 2

    inferred = infer_scope(bundle.get("app_scope", "")) if args.app_scope == "auto" else args.app_scope
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {"app_scope": inferred}

    if inferred in {"ios_only", "dual"}:
        cpp = build_cpp_manifest(locales, args.max_pages)
        cpp_path = out / "cpp_manifest.json"
        write_json(cpp_path, cpp)
        summary["cpp_manifest"] = str(cpp_path)
        summary["cpp_pages"] = len(cpp.get("pages", []))
        print(f"Wrote: {cpp_path}")
    else:
        summary["cpp_manifest"] = "skipped"
        summary["cpp_pages"] = 0

    if inferred in {"android_only", "dual"}:
        psl = build_psl_manifest(locales, args.max_pages)
        psl_path = out / "psl_manifest.json"
        write_json(psl_path, psl)
        summary["psl_manifest"] = str(psl_path)
        summary["psl_listings"] = len(psl.get("listings", []))
        print(f"Wrote: {psl_path}")
    else:
        summary["psl_manifest"] = "skipped"
        summary["psl_listings"] = 0

    summary_path = out / "cpp_psl_summary.json"
    write_json(summary_path, summary)
    print(f"Wrote: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

