#!/usr/bin/env python3
"""
Generate platform-ready ASO metadata from structured input.

Outputs:
- metadata_bundle.json
- fastlane/metadata/<locale>/* for iOS
- fastlane/metadata/android/<locale>/* for Android
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

APPLE_LIMITS = {"title": 30, "subtitle": 30, "description": 4000, "keywords_bytes": 100}
GOOGLE_LIMITS = {"title": 30, "short_description": 80, "description": 4000}


def truncate_text(text: str, limit: int) -> str:
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip()


def fit_title(brand: str, primary_keyword: str, limit: int) -> str:
    candidates = [
        f"{brand} {primary_keyword}".strip(),
        f"{primary_keyword} {brand}".strip(),
        brand.strip(),
        primary_keyword.strip(),
    ]
    for c in candidates:
        if len(c) <= limit and c:
            return c
    return truncate_text(candidates[0], limit)


def unique_ordered(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in values:
        k = item.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(item.strip())
    return out


def extract_keyword_tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9][a-z0-9+_-]{1,}", str(text or "").lower())


def build_apple_keywords(primary_keyword: str, secondary_keywords: List[str], global_keywords: List[str]) -> str:
    seeds = unique_ordered([primary_keyword] + secondary_keywords + global_keywords + extract_keyword_tokens(primary_keyword))
    accepted: List[str] = []
    for k in seeds:
        candidate = ",".join(accepted + [k]) if accepted else k
        if len(candidate.encode("utf-8")) <= APPLE_LIMITS["keywords_bytes"]:
            accepted.append(k)
        else:
            break
    return ",".join(accepted)


def join_value_props(value_props: List[str], fallback: str) -> str:
    clean = [v.strip() for v in value_props if v.strip()]
    if not clean:
        return fallback
    if len(clean) == 1:
        return clean[0]
    return f"{clean[0]} and {clean[1]}"


def build_description(app_name: str, primary_keyword: str, value_props: List[str], feature_points: List[str], intent_cluster: str, limit: int) -> str:
    vp = join_value_props(value_props, f"improve {primary_keyword}")
    lines = [
        f"{app_name} helps you {vp.lower()}.",
        "",
        "Key capabilities:",
    ]
    for fp in feature_points[:5]:
        if fp.strip():
            lines.append(f"- {fp.strip()}")
    lines.extend(
        [
            "",
            f"Built for {intent_cluster.replace('-', ' ')} workflows.",
            f"Designed around {primary_keyword} intent and real user actions.",
        ]
    )
    return truncate_text("\n".join(lines), limit)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_input(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ASO metadata and fastlane metadata files")
    parser.add_argument("--input", required=True, help="Metadata generation JSON input")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--bundle-out", help="Optional output bundle path")
    args = parser.parse_args()

    try:
        data = load_input(args.input)
    except Exception as exc:
        print(f"ERROR: failed to load input: {exc}")
        return 2

    app_name = str(data.get("app_name", "")).strip()
    brand_name = str(data.get("brand_name", app_name)).strip()
    app_scope = str(data.get("app_scope", "dual")).strip().lower()
    global_keywords = [str(x) for x in data.get("global_keywords", []) if str(x).strip()]
    locales = data.get("locales", [])

    if not app_name:
        print("ERROR: app_name is required")
        return 2
    if not isinstance(locales, list) or not locales:
        print("ERROR: locales must be a non-empty list")
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = Path(args.bundle_out) if args.bundle_out else output_dir / "metadata_bundle.json"

    bundle: Dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "app_name": app_name,
        "brand_name": brand_name,
        "app_scope": app_scope,
        "locales": [],
    }

    for item in locales:
        if not isinstance(item, dict):
            continue
        locale = str(item.get("locale", "")).strip()
        if not locale:
            continue
        primary_keyword = str(item.get("primary_keyword", "")).strip()
        if not primary_keyword:
            primary_keyword = "productivity app"
        intent_cluster = str(item.get("intent_cluster", "general-intent")).strip() or "general-intent"
        secondary_keywords = [str(x) for x in item.get("secondary_keywords", []) if str(x).strip()]
        value_props = [str(x) for x in item.get("value_props", []) if str(x).strip()]
        feature_points = [str(x) for x in item.get("feature_points", []) if str(x).strip()]

        apple_title = fit_title(brand_name, primary_keyword, APPLE_LIMITS["title"])
        apple_subtitle = truncate_text(join_value_props(value_props, f"Better {primary_keyword}"), APPLE_LIMITS["subtitle"])
        apple_keywords = build_apple_keywords(primary_keyword, secondary_keywords, global_keywords)
        apple_description = build_description(
            app_name=app_name,
            primary_keyword=primary_keyword,
            value_props=value_props,
            feature_points=feature_points,
            intent_cluster=intent_cluster,
            limit=APPLE_LIMITS["description"],
        )

        google_title = fit_title(brand_name, primary_keyword, GOOGLE_LIMITS["title"])
        google_short = truncate_text(join_value_props(value_props, f"Improve {primary_keyword}"), GOOGLE_LIMITS["short_description"])
        google_description = build_description(
            app_name=app_name,
            primary_keyword=primary_keyword,
            value_props=value_props,
            feature_points=feature_points,
            intent_cluster=intent_cluster,
            limit=GOOGLE_LIMITS["description"],
        )

        locale_payload = {
            "locale": locale,
            "intent_cluster": intent_cluster,
            "primary_keyword": primary_keyword,
            "apple": {
                "title": apple_title,
                "subtitle": apple_subtitle,
                "keywords": apple_keywords,
                "description": apple_description,
            },
            "google": {
                "title": google_title,
                "short_description": google_short,
                "description": google_description,
            },
        }
        bundle["locales"].append(locale_payload)

        ios_base = output_dir / "fastlane" / "metadata" / locale
        write_text(ios_base / "name.txt", apple_title)
        write_text(ios_base / "subtitle.txt", apple_subtitle)
        write_text(ios_base / "keywords.txt", apple_keywords)
        write_text(ios_base / "description.txt", apple_description)

        android_base = output_dir / "fastlane" / "metadata" / "android" / locale
        write_text(android_base / "title.txt", google_title)
        write_text(android_base / "short_description.txt", google_short)
        write_text(android_base / "full_description.txt", google_description)

    with bundle_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote metadata bundle: {bundle_path}")
    print(f"Wrote fastlane metadata root: {output_dir / 'fastlane' / 'metadata'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

