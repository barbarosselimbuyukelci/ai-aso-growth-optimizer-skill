#!/usr/bin/env python3
"""
Discover intent-oriented keyword candidates from iTunes Search API listing language.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from typing import Dict, List, Set

STOPWORDS = {
    "the", "and", "for", "with", "from", "your", "you", "that", "this", "into", "are", "our", "app",
    "best", "free", "new", "all", "more", "than", "can", "will", "use", "using", "not", "get", "now",
    "in", "on", "to", "a", "an", "of", "it", "is", "as", "by", "or", "at", "be", "we", "us", "its",
}

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+-]{1,}")


def tokenize(text: str, min_len: int) -> List[str]:
    tokens = []
    for token in TOKEN_RE.findall(text.lower()):
        if len(token) < min_len:
            continue
        if token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def fetch_apps(seed: str, country: str, limit: int) -> List[Dict[str, object]]:
    query = urllib.parse.urlencode({"term": seed, "entity": "software", "country": country, "limit": limit})
    url = f"https://itunes.apple.com/search?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "aso-growth-optimizer/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("results", [])


def extract_text_chunks(app: Dict[str, object]) -> str:
    parts = [
        str(app.get("trackName", "")),
        str(app.get("description", "")),
        str(app.get("primaryGenreName", "")),
        str(app.get("sellerName", "")),
    ]
    genres = app.get("genres", [])
    if isinstance(genres, list):
        parts.extend(str(g) for g in genres)
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover intent keyword candidates from iTunes Search API")
    parser.add_argument("--seeds", required=True, help="Comma-separated seed phrases")
    parser.add_argument("--country", default="us", help="App Store country code (default: us)")
    parser.add_argument("--limit", type=int, default=50, help="Max results per seed (default: 50)")
    parser.add_argument("--min-token-len", type=int, default=3, help="Minimum token length (default: 3)")
    parser.add_argument("--top", type=int, default=120, help="Top candidate count (default: 120)")
    parser.add_argument("--output", help="Optional output CSV path")
    args = parser.parse_args()

    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    if not seeds:
        print("ERROR: at least one seed is required")
        return 2

    all_apps: Dict[int, Dict[str, object]] = {}
    app_hits_by_token: Dict[str, Set[int]] = defaultdict(set)
    token_counts: Counter[str] = Counter()

    for seed in seeds:
        try:
            apps = fetch_apps(seed, args.country, args.limit)
        except Exception as exc:
            print(f"ERROR: failed fetching iTunes data for seed '{seed}': {exc}")
            return 2

        for app in apps:
            track_id = int(app.get("trackId", 0) or 0)
            if track_id <= 0:
                continue
            all_apps[track_id] = app
            text = extract_text_chunks(app)
            tokens = tokenize(text, args.min_token_len)
            unique = set(tokens)
            token_counts.update(tokens)
            for token in unique:
                app_hits_by_token[token].add(track_id)

    total_apps = len(all_apps)
    if total_apps == 0:
        print("ERROR: no apps returned from iTunes API")
        return 1

    ranked = []
    for token, freq in token_counts.items():
        coverage = len(app_hits_by_token[token])
        if coverage < 2:
            continue
        # Score favors terms that repeat often but also appear across multiple apps.
        score = float(freq) * math.log(1 + coverage)
        ranked.append((score, token, freq, coverage))

    ranked.sort(key=lambda row: row[0], reverse=True)
    ranked = ranked[: args.top]

    print("rank,keyword,score,frequency,app_coverage")
    for i, (score, token, freq, coverage) in enumerate(ranked, start=1):
        print(f"{i},{token},{score:.3f},{freq},{coverage}")

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "keyword", "score", "frequency", "app_coverage", "sample_app_names"])
            for i, (score, token, freq, coverage) in enumerate(ranked, start=1):
                sample_names = []
                for track_id in list(app_hits_by_token[token])[:5]:
                    sample_names.append(str(all_apps[track_id].get("trackName", "")))
                writer.writerow([i, token, f"{score:.3f}", freq, coverage, " | ".join(sample_names)])

    return 0


if __name__ == "__main__":
    sys.exit(main())
