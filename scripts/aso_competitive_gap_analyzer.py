#!/usr/bin/env python3
"""
Compare current app metadata against competitor analysis outputs.

Inputs:
- analysis dir from competitor analyzers
- current app fastlane metadata root

Outputs:
- <prefix>_gap_report.md
- <prefix>_gap_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+_-]{1,}")

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "this",
    "to",
    "use",
    "using",
    "with",
    "you",
    "your",
    "app",
    "apps",
    "best",
    "new",
    "more",
    "all",
    "can",
    "will",
    "not",
    "now",
    "free",
    "get",
    "one",
    "any",
    "make",
    "helps",
    "help",
    "built",
    "every",
    "across",
    "over",
}

MOTIFS = {
    "ai_positioning": {"ai", "assistant", "gpt", "smart", "intelligent", "copilot"},
    "speed_positioning": {"fast", "instant", "quick", "seconds", "immediately"},
    "trust_privacy": {"secure", "privacy", "private", "encrypted", "safe", "trusted"},
    "collaboration": {"team", "collaborate", "share", "workspace", "sync"},
    "productivity_outcome": {"productivity", "focus", "organize", "tasks", "project", "workflow", "efficient"},
    "capture_ingest": {"record", "capture", "scan", "import", "transcribe", "voice"},
    "monetization_cues": {"premium", "pro", "trial", "subscription", "upgrade"},
    "social_proof_cues": {"millions", "users", "top", "award", "trusted", "leading"},
}

SEMANTIC_THEMES = {
    "automation_ai": {"ai", "assistant", "copilot", "smart", "intelligent", "auto", "automate"},
    "speed_simplicity": {"fast", "quick", "instant", "simple", "easy", "effortless", "seconds"},
    "outcome_performance": {"results", "progress", "improve", "optimize", "efficient", "success", "achieve"},
    "planning_organization": {"plan", "organize", "schedule", "tasks", "workflow", "manage", "calendar"},
    "tracking_visibility": {"track", "monitor", "insights", "analytics", "history", "report", "dashboard"},
    "trust_safety": {"secure", "privacy", "private", "encrypted", "safe", "compliant", "trusted"},
    "team_collaboration": {"team", "share", "collaborate", "workspace", "together", "sync", "group"},
    "engagement_habit": {"daily", "routine", "streak", "habit", "reminder", "consistent", "goals"},
    "monetization_upsell": {"premium", "pro", "subscription", "trial", "upgrade", "unlimited", "plus"},
    "social_proof": {"millions", "users", "reviews", "rating", "top", "award", "leading"},
}


def tokenize(text: str, min_len: int) -> List[str]:
    out: List[str] = []
    for token in TOKEN_RE.findall(text.lower()):
        if len(token) < min_len:
            continue
        if token in STOPWORDS:
            continue
        out.append(token)
    return out


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_locales(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def collect_app_tokens(metadata_root: Path, locales: List[str], app_scope: str, min_token_len: int) -> Dict[str, Any]:
    ios_texts: List[str] = []
    android_texts: List[str] = []

    if app_scope in {"auto", "ios_only", "dual"}:
        for loc in locales:
            base = metadata_root / loc
            ios_texts.extend(
                [
                    read_text(base / "name.txt"),
                    read_text(base / "subtitle.txt"),
                    read_text(base / "keywords.txt").replace(",", " "),
                    read_text(base / "description.txt"),
                ]
            )

    if app_scope in {"auto", "android_only", "dual"}:
        for loc in locales:
            base = metadata_root / "android" / loc
            android_texts.extend(
                [
                    read_text(base / "title.txt"),
                    read_text(base / "short_description.txt"),
                    read_text(base / "full_description.txt"),
                ]
            )

    ios_tokens = set(tokenize(" ".join(ios_texts), min_token_len))
    android_tokens = set(tokenize(" ".join(android_texts), min_token_len))
    return {"ios": ios_tokens, "android": android_tokens}


def motif_presence(tokens: Set[str]) -> Dict[str, int]:
    return {m: 1 if tokens.intersection(terms) else 0 for m, terms in MOTIFS.items()}


def theme_hits(tokens: Set[str]) -> Dict[str, int]:
    return {t: len(tokens.intersection(terms)) for t, terms in SEMANTIC_THEMES.items()}


def top_missing_keywords(
    keyword_rows: List[Dict[str, str]], app_tokens: Set[str], top_n: int, min_coverage: float
) -> List[Dict[str, str]]:
    ranked: List[Tuple[float, float, Dict[str, str]]] = []
    for row in keyword_rows:
        keyword = str(row.get("keyword", "")).strip().lower()
        if not keyword:
            continue
        coverage = float(str(row.get("coverage_ratio", "0") or "0"))
        if coverage < min_coverage:
            continue
        if keyword in app_tokens:
            continue
        emphasis = float(str(row.get("weighted_emphasis", "0") or "0"))
        ranked.append((emphasis, coverage, row))
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r[2] for r in ranked[:top_n]]


def build_platform_gap(
    *,
    platform_label: str,
    app_tokens: Set[str],
    common_patterns_path: Path,
    semantic_path: Path,
    emphasis_path: Path,
    common_threshold: float,
    min_keyword_coverage: float,
    top_keywords: int,
) -> Dict[str, Any]:
    pattern_rows = read_csv_rows(common_patterns_path)
    semantic_rows = read_csv_rows(semantic_path)
    keyword_rows = read_csv_rows(emphasis_path)

    app_motifs = motif_presence(app_tokens)
    app_themes = theme_hits(app_tokens)

    motif_gaps: List[Dict[str, Any]] = []
    for row in pattern_rows:
        motif = str(row.get("motif", ""))
        if not motif:
            continue
        prevalence = float(str(row.get("prevalence", "0") or "0"))
        if prevalence < common_threshold:
            continue
        if app_motifs.get(motif, 0) == 0:
            motif_gaps.append({"motif": motif, "prevalence": prevalence})
    motif_gaps.sort(key=lambda x: x["prevalence"], reverse=True)

    theme_gaps: List[Dict[str, Any]] = []
    for row in semantic_rows:
        theme = str(row.get("theme", ""))
        if not theme:
            continue
        prevalence = float(str(row.get("prevalence", "0") or "0"))
        if prevalence < common_threshold:
            continue
        if app_themes.get(theme, 0) == 0:
            theme_gaps.append(
                {
                    "theme": theme,
                    "prevalence": prevalence,
                    "top_terms": str(row.get("top_terms", "")),
                }
            )
    theme_gaps.sort(key=lambda x: x["prevalence"], reverse=True)

    keyword_gaps = top_missing_keywords(keyword_rows, app_tokens, top_keywords, min_keyword_coverage)

    return {
        "platform": platform_label,
        "motif_gaps": motif_gaps,
        "theme_gaps": theme_gaps,
        "keyword_gaps": keyword_gaps,
        "app_motif_presence": app_motifs,
    }


def write_outputs(output_json: Path, output_md: Path, payload: Dict[str, Any]) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines: List[str] = [
        "# ASO Competitive Gap Report",
        "",
        "## Scope",
        f"- App scope: `{payload.get('app_scope', '')}`",
        f"- Locales analyzed: `{', '.join(payload.get('locales', []))}`",
        "",
    ]

    for platform in ("ios", "android"):
        data = payload.get("platforms", {}).get(platform)
        if not isinstance(data, dict):
            continue
        lines.append(f"## {platform.upper()} Gap Summary")
        motif_gaps = data.get("motif_gaps", [])
        theme_gaps = data.get("theme_gaps", [])
        keyword_gaps = data.get("keyword_gaps", [])

        if motif_gaps:
            lines.append("- Missing common motifs:")
            for item in motif_gaps[:8]:
                lines.append(f"  - `{item.get('motif','')}` prevalence `{float(item.get('prevalence',0)):.1%}`")
        else:
            lines.append("- Missing common motifs: none")

        if theme_gaps:
            lines.append("- Missing common semantic themes:")
            for item in theme_gaps[:8]:
                lines.append(
                    f"  - `{item.get('theme','')}` prevalence `{float(item.get('prevalence',0)):.1%}` terms `{item.get('top_terms','')}`"
                )
        else:
            lines.append("- Missing common semantic themes: none")

        if keyword_gaps:
            lines.append("- Suggested missing high-emphasis keywords:")
            for row in keyword_gaps[:12]:
                lines.append(
                    "  - "
                    + f"`{row.get('keyword','')}` score `{row.get('weighted_emphasis','')}` "
                    + f"coverage `{row.get('coverage_ratio','')}` dominant `{row.get('dominant_field','')}`"
                )
        else:
            lines.append("- Suggested missing high-emphasis keywords: none")
        lines.append("")

    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze gaps between app metadata and competitor patterns")
    parser.add_argument("--analysis-dir", required=True, help="Directory containing competitor analysis csv outputs")
    parser.add_argument("--app-metadata-root", required=True, help="fastlane metadata root for current app")
    parser.add_argument("--locales", default="en-US", help="Comma-separated locales to inspect in app metadata")
    parser.add_argument("--app-scope", choices=["auto", "ios_only", "android_only", "dual"], default="auto")
    parser.add_argument("--common-threshold", type=float, default=0.6)
    parser.add_argument("--min-keyword-coverage", type=float, default=0.3)
    parser.add_argument("--top-keywords", type=int, default=25)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--min-token-len", type=int, default=3)
    args = parser.parse_args()

    analysis_dir = Path(args.analysis_dir).resolve()
    app_metadata_root = Path(args.app_metadata_root).resolve()
    locales = parse_locales(args.locales)
    if not locales:
        print("ERROR: locales must not be empty")
        return 2

    app_tokens = collect_app_tokens(app_metadata_root, locales, args.app_scope, args.min_token_len)

    ios_gap = build_platform_gap(
        platform_label="ios",
        app_tokens=app_tokens.get("ios", set()),
        common_patterns_path=analysis_dir / "ios_competitor_common_patterns.csv",
        semantic_path=analysis_dir / "ios_competitor_semantic_themes.csv",
        emphasis_path=analysis_dir / "ios_competitor_keyword_emphasis.csv",
        common_threshold=args.common_threshold,
        min_keyword_coverage=args.min_keyword_coverage,
        top_keywords=args.top_keywords,
    )
    android_gap = build_platform_gap(
        platform_label="android",
        app_tokens=app_tokens.get("android", set()),
        common_patterns_path=analysis_dir / "play_competitor_common_patterns.csv",
        semantic_path=analysis_dir / "play_competitor_semantic_themes.csv",
        emphasis_path=analysis_dir / "play_competitor_keyword_emphasis.csv",
        common_threshold=args.common_threshold,
        min_keyword_coverage=args.min_keyword_coverage,
        top_keywords=args.top_keywords,
    )

    payload: Dict[str, Any] = {
        "app_scope": args.app_scope,
        "locales": locales,
        "analysis_dir": str(analysis_dir),
        "app_metadata_root": str(app_metadata_root),
        "platforms": {"ios": ios_gap, "android": android_gap},
    }

    output_json = Path(args.output_json).resolve()
    output_md = Path(args.output_md).resolve()
    write_outputs(output_json, output_md, payload)

    print(f"Wrote: {output_json}")
    print(f"Wrote: {output_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
