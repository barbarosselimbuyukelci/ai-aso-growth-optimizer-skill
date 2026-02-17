#!/usr/bin/env python3
"""
Build Android/Play competitor matrix from imported CSV exports.

Expected workflow:
- Export or prepare competitor listing data from Play-focused sources.
- Run this script to extract shared patterns and strategy signals.

Outputs:
- <prefix>_matrix.csv
- <prefix>_common_patterns.csv
- <prefix>_term_coverage.csv
- <prefix>_similarity.csv
- <prefix>_semantic_themes.csv
- <prefix>_keyword_emphasis.csv
- <prefix>_phrase_patterns.csv
- <prefix>_report.md
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+_-]{1,}")
NUM_RE = re.compile(r"\d")
EXCLAIM_RE = re.compile(r"!")

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

ACTION_VERBS = {
    "organize",
    "plan",
    "track",
    "record",
    "capture",
    "summarize",
    "share",
    "sync",
    "manage",
    "build",
    "create",
    "save",
    "analyze",
    "focus",
    "study",
    "learn",
    "edit",
    "scan",
    "write",
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

FIELD_WEIGHTS = {
    "title": 3.0,
    "short_description": 2.0,
    "description": 1.0,
}


def read_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[List[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def tokenize(text: str, min_len: int) -> List[str]:
    out: List[str] = []
    for token in TOKEN_RE.findall(text.lower()):
        if len(token) < min_len:
            continue
        if token in STOPWORDS:
            continue
        out.append(token)
    return out


def motif_presence(tokens: Iterable[str]) -> Dict[str, int]:
    token_set = set(tokens)
    row: Dict[str, int] = {}
    for motif, terms in MOTIFS.items():
        row[motif] = 1 if token_set.intersection(terms) else 0
    return row


def summarize_motifs(rows: List[Dict[str, object]]) -> List[Tuple[str, float, int, int]]:
    n = len(rows)
    if n == 0:
        return []
    out: List[Tuple[str, float, int, int]] = []
    for motif in MOTIFS.keys():
        count = sum(int(r.get(motif, 0)) for r in rows)
        prevalence = count / n
        out.append((motif, prevalence, count, n))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def top_document_terms(token_sets: List[Set[str]], top_n: int, min_doc_freq: int) -> List[Tuple[str, int, float]]:
    n = len(token_sets)
    df: Counter[str] = Counter()
    for s in token_sets:
        for token in s:
            df[token] += 1
    ranked: List[Tuple[str, int, float]] = []
    for token, count in df.items():
        if count < min_doc_freq:
            continue
        ranked.append((token, count, count / n if n else 0.0))
    ranked.sort(key=lambda x: (x[1], x[2], x[0]), reverse=True)
    return ranked[:top_n]


def build_similarity(names: List[str], token_sets: List[Set[str]]) -> List[List[str]]:
    table: List[List[str]] = []
    table.append(["app"] + names)
    for i, name_i in enumerate(names):
        row = [name_i]
        for j in range(len(names)):
            a = token_sets[i]
            b = token_sets[j]
            denom = len(a.union(b))
            sim = 1.0 if denom == 0 else len(a.intersection(b)) / denom
            row.append(f"{sim:.3f}")
        table.append(row)
    return table


def to_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        s = str(value).strip().replace(",", "")
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def to_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        s = str(value).strip().replace(",", "")
        if not s:
            return default
        return int(float(s))
    except Exception:
        return default


def infer_scope(requested_scope: str) -> str:
    if requested_scope == "auto":
        return "android_only"
    return requested_scope


def write_skipped_outputs(output_dir: Path, prefix: str, app_scope: str, reason: str) -> None:
    matrix_path = output_dir / f"{prefix}_matrix.csv"
    patterns_path = output_dir / f"{prefix}_common_patterns.csv"
    terms_path = output_dir / f"{prefix}_term_coverage.csv"
    similarity_path = output_dir / f"{prefix}_similarity.csv"
    semantic_path = output_dir / f"{prefix}_semantic_themes.csv"
    emphasis_path = output_dir / f"{prefix}_keyword_emphasis.csv"
    phrases_path = output_dir / f"{prefix}_phrase_patterns.csv"
    report_path = output_dir / f"{prefix}_report.md"

    write_csv(matrix_path, [["status", "app_scope", "reason"], ["skipped", app_scope, reason]])
    write_csv(patterns_path, [["status", "app_scope", "reason"], ["skipped", app_scope, reason]])
    write_csv(terms_path, [["status", "app_scope", "reason"], ["skipped", app_scope, reason]])
    write_csv(similarity_path, [["status", "app_scope", "reason"], ["skipped", app_scope, reason]])
    write_csv(semantic_path, [["status", "app_scope", "reason"], ["skipped", app_scope, reason]])
    write_csv(emphasis_path, [["status", "app_scope", "reason"], ["skipped", app_scope, reason]])
    write_csv(phrases_path, [["status", "app_scope", "reason"], ["skipped", app_scope, reason]])

    report = [
        "# ASO Play Competitor Report (Skipped)",
        "",
        f"- App scope: `{app_scope}`",
        f"- Reason: {reason}",
        "",
        "## Next Step",
        "- Use iTunes-based analyzer for iOS-only products.",
    ]
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"Wrote: {matrix_path}")
    print(f"Wrote: {patterns_path}")
    print(f"Wrote: {terms_path}")
    print(f"Wrote: {similarity_path}")
    print(f"Wrote: {semantic_path}")
    print(f"Wrote: {emphasis_path}")
    print(f"Wrote: {phrases_path}")
    print(f"Wrote: {report_path}")


def find_col(row: Dict[str, str], candidates: List[str]) -> str:
    keys_lower = {k.lower(): k for k in row.keys()}
    for c in candidates:
        if c.lower() in keys_lower:
            return keys_lower[c.lower()]
    return ""


def strategic_implications(motif_stats: List[Tuple[str, float, int, int]]) -> List[str]:
    prevalence = {name: p for name, p, _, _ in motif_stats}
    lines: List[str] = []
    if prevalence.get("ai_positioning", 0.0) >= 0.6:
        lines.append("AI positioning is saturated. Differentiate with explicit user outcomes.")
    if prevalence.get("speed_positioning", 0.0) >= 0.5:
        lines.append("Speed claims are common. Use evidence-backed phrasing.")
    if prevalence.get("trust_privacy", 0.0) < 0.35:
        lines.append("Trust/privacy messaging is underused and can be a wedge if product support exists.")
    if prevalence.get("capture_ingest", 0.0) >= 0.5 and prevalence.get("productivity_outcome", 0.0) >= 0.5:
        lines.append("Competitors chain capture-to-outcome framing. Preserve this narrative in metadata hierarchy.")
    if not lines:
        lines.append("No highly dominant motif. Split positioning by intent cluster and locale.")
    return lines


def top_terms_from_tokens(tokens: List[str], top_n: int = 5) -> List[str]:
    if not tokens:
        return []
    return [term for term, _ in Counter(tokens).most_common(top_n)]


def dominant_theme(theme_hits: Dict[str, int]) -> str:
    if not theme_hits:
        return "none"
    theme, score = max(theme_hits.items(), key=lambda x: (x[1], x[0]))
    return theme if score > 0 else "none"


def build_theme_hits(token_set: Set[str]) -> Dict[str, int]:
    return {theme: len(token_set.intersection(terms)) for theme, terms in SEMANTIC_THEMES.items()}


def build_theme_summary(
    theme_app_counts: Dict[str, int],
    theme_terms: Dict[str, Counter[str]],
    theme_examples: Dict[str, List[str]],
    total_apps: int,
) -> List[List[object]]:
    rows: List[List[object]] = [["theme", "app_count", "prevalence", "top_terms", "example_apps"]]
    for theme in sorted(SEMANTIC_THEMES.keys(), key=lambda t: theme_app_counts.get(t, 0), reverse=True):
        count = theme_app_counts.get(theme, 0)
        prevalence = (count / total_apps) if total_apps else 0.0
        top_terms = ", ".join([term for term, _ in theme_terms.get(theme, Counter()).most_common(6)])
        examples = " | ".join(theme_examples.get(theme, [])[:5])
        rows.append([theme, count, f"{prevalence:.3f}", top_terms, examples])
    return rows


def build_keyword_emphasis_rows(
    keyword_stats: Dict[str, Dict[str, object]],
    total_apps: int,
    min_doc_freq: int,
    top_n: int,
) -> List[List[object]]:
    ranked: List[Tuple[str, float, int, int, int, int]] = []
    for keyword, stats in keyword_stats.items():
        app_coverage = int(stats.get("apps", 0))
        if app_coverage < min_doc_freq:
            continue
        title_count = int(stats.get("title", 0))
        short_count = int(stats.get("short_description", 0))
        desc_count = int(stats.get("description", 0))
        weighted = (
            (title_count * FIELD_WEIGHTS["title"])
            + (short_count * FIELD_WEIGHTS["short_description"])
            + (desc_count * FIELD_WEIGHTS["description"])
        )
        ranked.append((keyword, weighted, app_coverage, title_count, short_count, desc_count))

    ranked.sort(key=lambda x: (x[1], x[2], x[0]), reverse=True)
    rows: List[List[object]] = [[
        "keyword",
        "weighted_emphasis",
        "app_coverage",
        "coverage_ratio",
        "title_mentions",
        "short_description_mentions",
        "description_mentions",
        "dominant_field",
    ]]
    for keyword, weighted, app_coverage, title_count, short_count, desc_count in ranked[:top_n]:
        dominant_field = max(
            [("title", title_count), ("short_description", short_count), ("description", desc_count)],
            key=lambda x: (x[1], x[0]),
        )[0]
        rows.append(
            [
                keyword,
                f"{weighted:.2f}",
                app_coverage,
                f"{(app_coverage / total_apps) if total_apps else 0.0:.3f}",
                title_count,
                short_count,
                desc_count,
                dominant_field,
            ]
        )
    return rows


def make_ngrams(tokens: List[str], n: int) -> List[str]:
    if len(tokens) < n:
        return []
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def build_phrase_pattern_rows(
    phrase_stats: Dict[str, Dict[str, object]],
    total_apps: int,
    min_doc_freq: int,
    top_n: int,
) -> List[List[object]]:
    ranked: List[Tuple[str, float, int, int, int, int, int]] = []
    for phrase, stats in phrase_stats.items():
        app_count = len(stats.get("apps", set()))
        if app_count < min_doc_freq:
            continue
        title_mentions = int(stats.get("title_mentions", 0))
        short_mentions = int(stats.get("short_description_mentions", 0))
        desc_mentions = int(stats.get("description_mentions", 0))
        ngram_size = int(stats.get("ngram_size", 2))
        weighted = (
            (title_mentions * FIELD_WEIGHTS["title"])
            + (short_mentions * FIELD_WEIGHTS["short_description"])
            + (desc_mentions * FIELD_WEIGHTS["description"])
        )
        ranked.append((phrase, weighted, app_count, title_mentions, short_mentions, desc_mentions, ngram_size))

    ranked.sort(key=lambda x: (x[1], x[2], x[0]), reverse=True)
    rows: List[List[object]] = [[
        "phrase",
        "ngram_size",
        "weighted_emphasis",
        "document_frequency",
        "coverage_ratio",
        "title_mentions",
        "short_description_mentions",
        "description_mentions",
        "dominant_field",
    ]]
    for phrase, weighted, app_count, title_mentions, short_mentions, desc_mentions, ngram_size in ranked[:top_n]:
        dominant_field = max(
            [("title", title_mentions), ("short_description", short_mentions), ("description", desc_mentions)],
            key=lambda x: (x[1], x[0]),
        )[0]
        rows.append(
            [
                phrase,
                ngram_size,
                f"{weighted:.2f}",
                app_count,
                f"{(app_count / total_apps) if total_apps else 0.0:.3f}",
                title_mentions,
                short_mentions,
                desc_mentions,
                dominant_field,
            ]
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Play competitor analysis matrix from imported CSV data")
    parser.add_argument("--input", required=True, help="Input CSV path for competitor listing data")
    parser.add_argument("--min-token-len", type=int, default=3)
    parser.add_argument("--common-threshold", type=float, default=0.6)
    parser.add_argument("--top-terms", type=int, default=80)
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--prefix", default="play_competitor")
    parser.add_argument(
        "--app-scope",
        choices=["auto", "ios_only", "android_only", "dual"],
        default="auto",
        help="Platform scope gate. auto defaults to android_only for Play import pipeline.",
    )
    parser.add_argument("--on-mismatch", choices=["skip", "error"], default="skip")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    app_scope = infer_scope(args.app_scope)
    if app_scope == "ios_only":
        reason = "Play import analyzer is not applicable to ios_only scope."
        if args.on_mismatch == "error":
            print("ERROR: " + reason)
            return 2
        print("SKIP: " + reason)
        write_skipped_outputs(output_dir=output_dir, prefix=args.prefix, app_scope=app_scope, reason=reason)
        return 0

    try:
        rows = read_csv(args.input)
    except Exception as exc:
        print(f"ERROR: failed to read input csv: {exc}")
        return 2

    if not rows:
        print("ERROR: input csv is empty")
        return 2

    first = rows[0]
    col_app_name = find_col(first, ["app_name", "title", "name"])
    col_short = find_col(first, ["short_description", "short_desc"])
    col_full = find_col(first, ["full_description", "description", "long_description"])
    col_developer = find_col(first, ["developer", "seller", "developer_name"])
    col_category = find_col(first, ["category", "primary_genre", "genre"])
    col_locale = find_col(first, ["locale", "language"])
    col_country = find_col(first, ["country", "store_country"])
    col_rating = find_col(first, ["avg_rating", "rating"])
    col_rating_count = find_col(first, ["rating_count", "ratings_count", "user_ratings_total"])
    col_installs = find_col(first, ["installs", "install_count", "downloads"])
    col_price = find_col(first, ["price"])
    col_pkg = find_col(first, ["package_name", "bundle_id", "app_id"])
    col_url = find_col(first, ["url", "store_url", "play_url"])

    if not col_app_name:
        print("ERROR: could not find app name column (expected app_name/title/name)")
        return 2

    matrix_rows: List[Dict[str, object]] = []
    token_sets: List[Set[str]] = []
    names: List[str] = []

    theme_app_counts: Counter[str] = Counter()
    theme_terms: Dict[str, Counter[str]] = defaultdict(Counter)
    theme_examples: Dict[str, List[str]] = defaultdict(list)
    keyword_stats: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {"apps": 0, "title": 0, "short_description": 0, "description": 0}
    )
    phrase_stats: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {
            "apps": set(),
            "title_mentions": 0,
            "short_description_mentions": 0,
            "description_mentions": 0,
            "ngram_size": 2,
        }
    )

    for row in rows:
        app_name = str(row.get(col_app_name, "")).strip()
        short_desc = str(row.get(col_short, "")).strip() if col_short else ""
        full_desc = str(row.get(col_full, "")).strip() if col_full else ""
        developer = str(row.get(col_developer, "")).strip() if col_developer else ""
        category = str(row.get(col_category, "")).strip() if col_category else ""
        locale = str(row.get(col_locale, "")).strip() if col_locale else ""
        country = str(row.get(col_country, "")).strip() if col_country else ""
        rating = to_float(row.get(col_rating)) if col_rating else 0.0
        rating_count = to_int(row.get(col_rating_count)) if col_rating_count else 0
        installs = to_int(row.get(col_installs)) if col_installs else 0
        price = to_float(row.get(col_price)) if col_price else 0.0
        pkg = str(row.get(col_pkg, "")).strip() if col_pkg else ""
        url = str(row.get(col_url, "")).strip() if col_url else ""

        text = " ".join([app_name, short_desc, full_desc, developer, category])
        tokens = tokenize(text, args.min_token_len)
        token_set = set(tokens)
        motifs = motif_presence(tokens)

        title_tokens = tokenize(app_name, args.min_token_len)
        short_tokens = tokenize(short_desc, args.min_token_len)
        desc_tokens = tokenize(full_desc, args.min_token_len)
        metadata_token_set = set(title_tokens).union(short_tokens).union(desc_tokens)
        first_token = title_tokens[0] if title_tokens else ""

        app_theme_hits = build_theme_hits(metadata_token_set)
        app_dominant_theme = dominant_theme(app_theme_hits)
        for theme, hit_count in app_theme_hits.items():
            if hit_count <= 0:
                continue
            theme_app_counts[theme] += 1
            theme_terms[theme].update([t for t in metadata_token_set if t in SEMANTIC_THEMES[theme]])
            if app_name and len(theme_examples[theme]) < 5 and app_name not in theme_examples[theme]:
                theme_examples[theme].append(app_name)

        for token in metadata_token_set:
            keyword_stats[token]["apps"] = int(keyword_stats[token]["apps"]) + 1
        for token in set(title_tokens):
            keyword_stats[token]["title"] = int(keyword_stats[token]["title"]) + 1
        for token in set(short_tokens):
            keyword_stats[token]["short_description"] = int(keyword_stats[token]["short_description"]) + 1
        for token in set(desc_tokens):
            keyword_stats[token]["description"] = int(keyword_stats[token]["description"]) + 1

        app_key = pkg if pkg else app_name
        for n in (2, 3):
            for phrase in set(make_ngrams(title_tokens, n)):
                phrase_stats[phrase]["ngram_size"] = n
                phrase_stats[phrase]["title_mentions"] = int(phrase_stats[phrase]["title_mentions"]) + 1
                phrase_stats[phrase]["apps"].add(app_key)
            for phrase in set(make_ngrams(short_tokens, n)):
                phrase_stats[phrase]["ngram_size"] = n
                phrase_stats[phrase]["short_description_mentions"] = int(phrase_stats[phrase]["short_description_mentions"]) + 1
                phrase_stats[phrase]["apps"].add(app_key)
            for phrase in set(make_ngrams(desc_tokens, n)):
                phrase_stats[phrase]["ngram_size"] = n
                phrase_stats[phrase]["description_mentions"] = int(phrase_stats[phrase]["description_mentions"]) + 1
                phrase_stats[phrase]["apps"].add(app_key)

        matrix_row: Dict[str, object] = {
            "app_name": app_name,
            "package_name": pkg,
            "developer": developer,
            "category": category,
            "locale": locale,
            "country": country,
            "price": f"{price:.2f}",
            "avg_rating": f"{rating:.2f}",
            "rating_count": rating_count,
            "installs": installs,
            "title_len": len(app_name),
            "short_description_len": len(short_desc),
            "description_len": len(full_desc),
            "title_has_number": 1 if NUM_RE.search(app_name) else 0,
            "title_has_exclaim": 1 if EXCLAIM_RE.search(app_name) else 0,
            "title_starts_with_action_verb": 1 if first_token in ACTION_VERBS else 0,
            "dominant_theme": app_dominant_theme,
            "top_title_terms": ", ".join(top_terms_from_tokens(title_tokens, 4)),
            "top_short_terms": ", ".join(top_terms_from_tokens(short_tokens, 5)),
            "top_description_terms": ", ".join(top_terms_from_tokens(desc_tokens, 6)),
            "store_url": url,
        }
        matrix_row.update(motifs)
        matrix_rows.append(matrix_row)
        token_sets.append(token_set)
        names.append(app_name)

    if not matrix_rows:
        print("ERROR: no competitor rows processed")
        return 1

    motif_stats = summarize_motifs(matrix_rows)
    min_doc_freq = max(2, int(math.ceil(len(token_sets) * args.common_threshold)))
    top_terms = top_document_terms(token_sets, args.top_terms, min_doc_freq)
    similarity_table = build_similarity(names, token_sets)
    semantic_theme_csv = build_theme_summary(theme_app_counts, theme_terms, theme_examples, len(matrix_rows))
    keyword_emphasis_csv = build_keyword_emphasis_rows(keyword_stats, len(matrix_rows), min_doc_freq, args.top_terms)
    phrase_patterns_csv = build_phrase_pattern_rows(phrase_stats, len(matrix_rows), min_doc_freq, args.top_terms)

    matrix_headers = [
        "app_name",
        "package_name",
        "developer",
        "category",
        "locale",
        "country",
        "price",
        "avg_rating",
        "rating_count",
        "installs",
        "title_len",
        "short_description_len",
        "description_len",
        "title_has_number",
        "title_has_exclaim",
        "title_starts_with_action_verb",
        "dominant_theme",
        "top_title_terms",
        "top_short_terms",
        "top_description_terms",
    ] + list(MOTIFS.keys()) + ["store_url"]

    matrix_csv: List[List[object]] = [matrix_headers]
    for row in matrix_rows:
        matrix_csv.append([row.get(h, "") for h in matrix_headers])

    common_patterns_csv = [["motif", "prevalence", "count", "total", "is_common"]]
    for motif, prevalence, count, total in motif_stats:
        common_patterns_csv.append(
            [motif, f"{prevalence:.3f}", count, total, 1 if prevalence >= args.common_threshold else 0]
        )

    term_cov_csv = [["term", "document_frequency", "coverage_ratio"]]
    for token, df, cov in top_terms:
        term_cov_csv.append([token, df, f"{cov:.3f}"])

    matrix_path = output_dir / f"{args.prefix}_matrix.csv"
    patterns_path = output_dir / f"{args.prefix}_common_patterns.csv"
    terms_path = output_dir / f"{args.prefix}_term_coverage.csv"
    similarity_path = output_dir / f"{args.prefix}_similarity.csv"
    semantic_path = output_dir / f"{args.prefix}_semantic_themes.csv"
    emphasis_path = output_dir / f"{args.prefix}_keyword_emphasis.csv"
    phrases_path = output_dir / f"{args.prefix}_phrase_patterns.csv"
    report_path = output_dir / f"{args.prefix}_report.md"

    write_csv(matrix_path, matrix_csv)
    write_csv(patterns_path, common_patterns_csv)
    write_csv(terms_path, term_cov_csv)
    write_csv(similarity_path, similarity_table)
    write_csv(semantic_path, semantic_theme_csv)
    write_csv(emphasis_path, keyword_emphasis_csv)
    write_csv(phrases_path, phrase_patterns_csv)

    title_lengths = [int(r["title_len"]) for r in matrix_rows]
    short_lengths = [int(r["short_description_len"]) for r in matrix_rows]
    desc_lengths = [int(r["description_len"]) for r in matrix_rows]
    implications = strategic_implications(motif_stats)

    report_lines = [
        "# ASO Play Competitor Analysis Report",
        "",
        "## Dataset Summary",
        f"- App scope: `{app_scope}`",
        f"- Source file: `{args.input}`",
        f"- Competitor apps: `{len(matrix_rows)}`",
        f"- Common-pattern threshold: `{args.common_threshold:.2f}`",
        "",
        "## Structural Metadata Patterns",
        f"- Avg title length: `{statistics.mean(title_lengths):.1f}`",
        f"- Avg short description length: `{statistics.mean(short_lengths):.1f}`",
        f"- Avg full description length: `{statistics.mean(desc_lengths):.1f}`",
        "",
        "## Shared Motif Prevalence",
    ]

    for motif, prevalence, count, total in motif_stats:
        marker = " (common)" if prevalence >= args.common_threshold else ""
        report_lines.append(f"- `{motif}`: `{count}/{total}` ({prevalence:.1%}){marker}")

    report_lines.append("")
    report_lines.append("## Semantic Theme Prevalence")
    for row in semantic_theme_csv[1:8]:
        theme = str(row[0])
        app_count = int(row[1]) if str(row[1]).strip() else 0
        if app_count <= 0:
            continue
        report_lines.append(f"- `{theme}`: `{app_count}` apps ({float(row[2]):.1%}), terms: `{row[3]}`")

    report_lines.append("")
    report_lines.append("## Keyword Emphasis (Title vs Short vs Description)")
    for row in keyword_emphasis_csv[1:13]:
        report_lines.append(
            f"- `{row[0]}` score=`{row[1]}` coverage=`{row[3]}` dominant=`{row[7]}` title=`{row[4]}` short=`{row[5]}` desc=`{row[6]}`"
        )

    report_lines.append("")
    report_lines.append("## Recurring Phrase Patterns")
    for row in phrase_patterns_csv[1:11]:
        report_lines.append(
            f"- `{row[0]}` n=`{row[1]}` score=`{row[2]}` coverage=`{row[4]}` dominant=`{row[8]}`"
        )

    report_lines.append("")
    report_lines.append("## High-Coverage Vocabulary")
    for token, df, cov in top_terms[:20]:
        report_lines.append(f"- `{token}`: appears in `{df}` apps ({cov:.1%})")

    report_lines.append("")
    report_lines.append("## Strategic Implications")
    for item in implications:
        report_lines.append(f"- {item}")

    report_lines.append("")
    report_lines.append("## Output Files")
    report_lines.append(f"- `{matrix_path}`")
    report_lines.append(f"- `{patterns_path}`")
    report_lines.append(f"- `{terms_path}`")
    report_lines.append(f"- `{similarity_path}`")
    report_lines.append(f"- `{semantic_path}`")
    report_lines.append(f"- `{emphasis_path}`")
    report_lines.append(f"- `{phrases_path}`")

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Wrote: {matrix_path}")
    print(f"Wrote: {patterns_path}")
    print(f"Wrote: {terms_path}")
    print(f"Wrote: {similarity_path}")
    print(f"Wrote: {semantic_path}")
    print(f"Wrote: {emphasis_path}")
    print(f"Wrote: {phrases_path}")
    print(f"Wrote: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
