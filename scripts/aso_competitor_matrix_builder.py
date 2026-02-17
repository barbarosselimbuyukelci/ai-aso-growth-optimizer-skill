#!/usr/bin/env python3
"""
Build a detailed ASO competitor matrix from iTunes Search API data.

Outputs:
- <prefix>_matrix.csv: per-competitor feature matrix
- <prefix>_common_patterns.csv: prevalence of message motifs
- <prefix>_term_coverage.csv: high-coverage vocabulary
- <prefix>_similarity.csv: pairwise app similarity (jaccard)
- <prefix>_semantic_themes.csv: semantic-context prevalence and top trigger terms
- <prefix>_keyword_emphasis.csv: weighted keyword emphasis by metadata field
- <prefix>_phrase_patterns.csv: recurring message phrase patterns
- <prefix>_report.md: strategy-oriented findings
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+_-]{1,}")
NUM_RE = re.compile(r"\d")
EXCLAIM_RE = re.compile(r"!")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "its", "of", "on", "or",
    "our", "that", "the", "this", "to", "use", "using", "with", "you", "your", "app", "apps", "best", "new", "more", "all",
    "can", "will", "not", "now", "free", "get", "one", "any", "make", "helps", "help", "built", "every", "across", "over",
}

ACTION_VERBS = {
    "organize", "plan", "track", "record", "capture", "summarize", "share", "sync", "manage", "build", "create", "save",
    "analyze", "focus", "study", "learn", "edit", "scan", "write",
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
    "description": 1.0,
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


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def fetch_itunes_apps(seed: str, country: str, limit: int) -> List[Dict[str, object]]:
    params = urllib.parse.urlencode({"term": seed, "entity": "software", "country": country, "limit": limit})
    url = f"https://itunes.apple.com/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "aso-growth-optimizer/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    return results


def app_text(app: Dict[str, object]) -> str:
    desc = str(app.get("description", ""))
    name = str(app.get("trackName", ""))
    genre = str(app.get("primaryGenreName", ""))
    seller = str(app.get("sellerName", ""))
    return " ".join([name, desc, genre, seller])


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


def build_similarity(names: List[str], token_sets: List[Set[str]]) -> List[List[str]]:
    table: List[List[str]] = []
    header = ["app"] + names
    table.append(header)
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


def strategic_implications(motif_stats: List[Tuple[str, float, int, int]]) -> List[str]:
    prevalence = {name: p for name, p, _, _ in motif_stats}
    lines: List[str] = []

    if prevalence.get("ai_positioning", 0.0) >= 0.6:
        lines.append("AI positioning is crowded. Differentiate with concrete outcome claims, not generic AI wording.")
    if prevalence.get("speed_positioning", 0.0) >= 0.5:
        lines.append("Speed messaging is common. Test proof-based speed claims with real scenario framing.")
    if prevalence.get("trust_privacy", 0.0) < 0.35:
        lines.append("Trust/privacy is underused. This is a whitespace opportunity if product support exists.")
    if prevalence.get("collaboration", 0.0) < 0.30:
        lines.append("Collaboration language has low saturation. Consider team and sharing use-cases in metadata variants.")
    if prevalence.get("capture_ingest", 0.0) >= 0.5 and prevalence.get("productivity_outcome", 0.0) >= 0.5:
        lines.append("Competitors pair capture + productivity outcomes. Preserve this narrative chain in listing flow.")
    if not lines:
        lines.append("No dominant motif concentration detected. Positioning can be split by locale and user-intent clusters.")

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
    ranked: List[Tuple[str, float, int, int, int]] = []
    for keyword, stats in keyword_stats.items():
        app_coverage = int(stats.get("apps", 0))
        if app_coverage < min_doc_freq:
            continue
        title_count = int(stats.get("title", 0))
        desc_count = int(stats.get("description", 0))
        weighted = (title_count * FIELD_WEIGHTS["title"]) + (desc_count * FIELD_WEIGHTS["description"])
        ranked.append((keyword, weighted, app_coverage, title_count, desc_count))

    ranked.sort(key=lambda x: (x[1], x[2], x[0]), reverse=True)
    rows: List[List[object]] = [[
        "keyword",
        "weighted_emphasis",
        "app_coverage",
        "coverage_ratio",
        "title_mentions",
        "description_mentions",
        "dominant_field",
    ]]
    for keyword, weighted, app_coverage, title_count, desc_count in ranked[:top_n]:
        dominant_field = "title" if title_count >= desc_count else "description"
        rows.append(
            [
                keyword,
                f"{weighted:.2f}",
                app_coverage,
                f"{(app_coverage / total_apps) if total_apps else 0.0:.3f}",
                title_count,
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
    ranked: List[Tuple[str, float, int, int, int, int]] = []
    for phrase, stats in phrase_stats.items():
        app_count = len(stats.get("apps", set()))
        if app_count < min_doc_freq:
            continue
        title_mentions = int(stats.get("title_mentions", 0))
        desc_mentions = int(stats.get("description_mentions", 0))
        ngram_size = int(stats.get("ngram_size", 2))
        weighted = (title_mentions * FIELD_WEIGHTS["title"]) + (desc_mentions * FIELD_WEIGHTS["description"])
        ranked.append((phrase, weighted, app_count, title_mentions, desc_mentions, ngram_size))

    ranked.sort(key=lambda x: (x[1], x[2], x[0]), reverse=True)
    rows: List[List[object]] = [[
        "phrase",
        "ngram_size",
        "weighted_emphasis",
        "document_frequency",
        "coverage_ratio",
        "title_mentions",
        "description_mentions",
        "dominant_field",
    ]]
    for phrase, weighted, app_count, title_mentions, desc_mentions, ngram_size in ranked[:top_n]:
        dominant_field = "title" if title_mentions >= desc_mentions else "description"
        rows.append(
            [
                phrase,
                ngram_size,
                f"{weighted:.2f}",
                app_count,
                f"{(app_count / total_apps) if total_apps else 0.0:.3f}",
                title_mentions,
                desc_mentions,
                dominant_field,
            ]
        )
    return rows


def write_csv(path: Path, rows: List[List[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def infer_scope(requested_scope: str) -> str:
    if requested_scope == "auto":
        # This script is iTunes/App Store based; auto defaults to iOS scope.
        return "ios_only"
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
        "# ASO Competitor Analysis Report (Skipped)",
        "",
        f"- App scope: `{app_scope}`",
        f"- Reason: {reason}",
        "",
        "## Next Step",
        "- Use Android/Play-specific competitor exports for android-only products.",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ASO competitor analysis matrix from iTunes data")
    parser.add_argument("--seeds", required=True, help="Comma-separated seed queries")
    parser.add_argument("--country", default="us", help="Country code for iTunes search")
    parser.add_argument("--limit", type=int, default=50, help="Max apps per seed")
    parser.add_argument("--min-token-len", type=int, default=3, help="Minimum token length")
    parser.add_argument("--common-threshold", type=float, default=0.6, help="Prevalence threshold for common patterns")
    parser.add_argument("--top-terms", type=int, default=80, help="Top shared terms to output")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--prefix", default="aso_competitor", help="Output file prefix")
    parser.add_argument(
        "--app-scope",
        choices=["auto", "ios_only", "android_only", "dual"],
        default="auto",
        help="Platform scope gate. auto defaults to ios_only for iTunes data.",
    )
    parser.add_argument(
        "--on-mismatch",
        choices=["skip", "error"],
        default="skip",
        help="Behavior when scope is unsupported for this script.",
    )
    args = parser.parse_args()

    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    if not seeds:
        print("ERROR: at least one seed is required")
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    app_scope = infer_scope(args.app_scope)
    if app_scope == "android_only":
        reason = "iTunes-based competitor mining is not applicable to android_only scope."
        if args.on_mismatch == "error":
            print("ERROR: " + reason)
            return 2
        print("SKIP: " + reason)
        write_skipped_outputs(output_dir=output_dir, prefix=args.prefix, app_scope=app_scope, reason=reason)
        return 0

    apps_by_id: Dict[int, Dict[str, object]] = {}
    seed_hits: Dict[int, Set[str]] = defaultdict(set)

    for seed in seeds:
        try:
            items = fetch_itunes_apps(seed, args.country, args.limit)
        except Exception as exc:
            print(f"ERROR: iTunes fetch failed for seed '{seed}': {exc}")
            return 2

        for item in items:
            track_id = safe_int(item.get("trackId"), 0)
            if track_id <= 0:
                continue
            apps_by_id[track_id] = item
            seed_hits[track_id].add(seed)

    if not apps_by_id:
        print("ERROR: no competitor apps found")
        return 1

    matrix_rows: List[Dict[str, object]] = []
    token_sets: List[Set[str]] = []
    names: List[str] = []

    theme_app_counts: Counter[str] = Counter()
    theme_terms: Dict[str, Counter[str]] = defaultdict(Counter)
    theme_examples: Dict[str, List[str]] = defaultdict(list)
    keyword_stats: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {"apps": 0, "title": 0, "description": 0}
    )
    phrase_stats: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {"apps": set(), "title_mentions": 0, "description_mentions": 0, "ngram_size": 2}
    )

    for track_id, app in apps_by_id.items():
        name = str(app.get("trackName", ""))
        desc = str(app.get("description", ""))
        seller = str(app.get("sellerName", ""))
        genre = str(app.get("primaryGenreName", ""))
        price = safe_float(app.get("price"), 0.0)
        currency = str(app.get("currency", ""))
        rating = safe_float(app.get("averageUserRating"), 0.0)
        rating_count = safe_int(app.get("userRatingCount"), 0)

        text = app_text(app)
        tokens = tokenize(text, args.min_token_len)
        token_set = set(tokens)
        motifs = motif_presence(tokens)

        title = str(app.get("trackName", ""))
        title_tokens = tokenize(title, args.min_token_len)
        desc_tokens = tokenize(desc, args.min_token_len)
        metadata_token_set = set(title_tokens).union(desc_tokens)
        first_token = title_tokens[0] if title_tokens else ""

        app_theme_hits = build_theme_hits(metadata_token_set)
        app_dominant_theme = dominant_theme(app_theme_hits)

        for theme, hit_count in app_theme_hits.items():
            if hit_count <= 0:
                continue
            theme_app_counts[theme] += 1
            theme_terms[theme].update([t for t in metadata_token_set if t in SEMANTIC_THEMES[theme]])
            if name and len(theme_examples[theme]) < 5 and name not in theme_examples[theme]:
                theme_examples[theme].append(name)

        for token in metadata_token_set:
            keyword_stats[token]["apps"] = int(keyword_stats[token]["apps"]) + 1
        for token in set(title_tokens):
            keyword_stats[token]["title"] = int(keyword_stats[token]["title"]) + 1
        for token in set(desc_tokens):
            keyword_stats[token]["description"] = int(keyword_stats[token]["description"]) + 1

        for n in (2, 3):
            for phrase in set(make_ngrams(title_tokens, n)):
                phrase_stats[phrase]["ngram_size"] = n
                phrase_stats[phrase]["title_mentions"] = int(phrase_stats[phrase]["title_mentions"]) + 1
                phrase_stats[phrase]["apps"].add(track_id)
            for phrase in set(make_ngrams(desc_tokens, n)):
                phrase_stats[phrase]["ngram_size"] = n
                phrase_stats[phrase]["description_mentions"] = int(phrase_stats[phrase]["description_mentions"]) + 1
                phrase_stats[phrase]["apps"].add(track_id)

        row: Dict[str, object] = {
            "track_id": track_id,
            "app_name": name,
            "seller": seller,
            "genre": genre,
            "country": args.country,
            "matched_seeds": " | ".join(sorted(seed_hits[track_id])),
            "price": f"{price:.2f}",
            "currency": currency,
            "avg_rating": f"{rating:.2f}",
            "rating_count": rating_count,
            "title_len": len(title),
            "description_len": len(desc),
            "title_has_number": 1 if NUM_RE.search(title) else 0,
            "title_has_exclaim": 1 if EXCLAIM_RE.search(title) else 0,
            "title_starts_with_action_verb": 1 if first_token in ACTION_VERBS else 0,
            "dominant_theme": app_dominant_theme,
            "top_title_terms": ", ".join(top_terms_from_tokens(title_tokens, 4)),
            "top_description_terms": ", ".join(top_terms_from_tokens(desc_tokens, 6)),
            "app_store_url": str(app.get("trackViewUrl", "")),
        }
        row.update(motifs)

        matrix_rows.append(row)
        token_sets.append(token_set)
        names.append(name)

    motif_stats = summarize_motifs(matrix_rows)

    min_doc_freq = max(2, int(math.ceil(len(token_sets) * args.common_threshold)))
    top_terms = top_document_terms(token_sets, args.top_terms, min_doc_freq)
    similarity_table = build_similarity(names, token_sets)
    semantic_theme_csv = build_theme_summary(theme_app_counts, theme_terms, theme_examples, len(matrix_rows))
    keyword_emphasis_csv = build_keyword_emphasis_rows(keyword_stats, len(matrix_rows), min_doc_freq, args.top_terms)
    phrase_patterns_csv = build_phrase_pattern_rows(phrase_stats, len(matrix_rows), min_doc_freq, args.top_terms)

    matrix_headers = [
        "track_id",
        "app_name",
        "seller",
        "genre",
        "country",
        "matched_seeds",
        "price",
        "currency",
        "avg_rating",
        "rating_count",
        "title_len",
        "description_len",
        "title_has_number",
        "title_has_exclaim",
        "title_starts_with_action_verb",
        "dominant_theme",
        "top_title_terms",
        "top_description_terms",
    ] + list(MOTIFS.keys()) + ["app_store_url"]

    matrix_csv: List[List[object]] = [matrix_headers]
    for row in sorted(matrix_rows, key=lambda r: (r.get("app_name", ""), r.get("track_id", 0))):
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
    desc_lengths = [int(r["description_len"]) for r in matrix_rows]

    implications = strategic_implications(motif_stats)

    report_lines = [
        "# ASO Competitor Analysis Report",
        "",
        "## Dataset Summary",
        f"- App scope: `{app_scope}`",
        "- Source: `Apple iTunes Search API`",
        f"- Country: `{args.country}`",
        f"- Seeds: `{', '.join(seeds)}`",
        f"- Unique competitor apps: `{len(matrix_rows)}`",
        f"- Common-pattern threshold: `{args.common_threshold:.2f}`",
        "",
        "## Structural Metadata Patterns",
        f"- Avg title length: `{statistics.mean(title_lengths):.1f}`",
        f"- Median title length: `{statistics.median(title_lengths):.1f}`",
        f"- Avg description length: `{statistics.mean(desc_lengths):.1f}`",
        f"- Median description length: `{statistics.median(desc_lengths):.1f}`",
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
    report_lines.append("## Keyword Emphasis (Title vs Description)")
    for row in keyword_emphasis_csv[1:13]:
        report_lines.append(
            f"- `{row[0]}` score=`{row[1]}` coverage=`{row[3]}` dominant=`{row[6]}` title=`{row[4]}` desc=`{row[5]}`"
        )

    report_lines.append("")
    report_lines.append("## Recurring Phrase Patterns")
    for row in phrase_patterns_csv[1:11]:
        report_lines.append(
            f"- `{row[0]}` n=`{row[1]}` score=`{row[2]}` coverage=`{row[4]}` dominant=`{row[7]}`"
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
