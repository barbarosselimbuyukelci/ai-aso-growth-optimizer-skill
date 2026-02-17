#!/usr/bin/env python3
"""
Estimate keyword demand score by blending multiple ASO/SEM proxy signals.

The script does not claim "exact official volume". It computes a practical
estimated demand score (0-100) using available sources:

- Apple proxy metrics
- Google Keyword Planner exports
- AppTweak-like metrics
- Competitor term coverage
- iTunes intent signal output
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from typing import Dict, List, Optional, Set, Tuple


def to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(",", "")
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except Exception:
        return None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def normalize_keyword(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def normalize_locale(text: str) -> str:
    return str(text or "").strip().lower()


def normalize_platform(text: str) -> str:
    t = str(text or "").strip().lower()
    if t in {"ios", "apple", "appstore"}:
        return "apple"
    if t in {"android", "google", "play"}:
        return "google"
    return t


def read_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def percentile_scaled(values: List[Optional[float]], use_log: bool = False, reverse: bool = False) -> List[Optional[float]]:
    present = [(idx, v) for idx, v in enumerate(values) if v is not None]
    if not present:
        return [None for _ in values]

    transformed: List[Tuple[int, float]] = []
    for idx, val in present:
        v = float(val)
        if use_log:
            v = math.log1p(max(0.0, v))
        if reverse:
            v = -v
        transformed.append((idx, v))

    only = [v for _, v in transformed]
    lo, hi = min(only), max(only)

    out: List[Optional[float]] = [None for _ in values]
    if hi == lo:
        for idx, _ in transformed:
            out[idx] = 50.0
        return out

    for idx, v in transformed:
        out[idx] = ((v - lo) / (hi - lo)) * 100.0
    return out


def parse_competition(value: object) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in {"low"}:
        return 33.0
    if s in {"medium", "med"}:
        return 66.0
    if s in {"high"}:
        return 100.0
    v = to_float(s)
    if v is None:
        return None
    if v <= 1.0:
        return clamp(v * 100.0)
    return clamp(v)


def extract_metric(row: Dict[str, str], candidates: List[str], parser=to_float) -> Optional[float]:
    for key in candidates:
        if key in row:
            return parser(row.get(key))
    return None


def index_rows(rows: List[Dict[str, str]], keyword_field_candidates: List[str]) -> Dict[str, List[Dict[str, str]]]:
    idx: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        keyword = ""
        for key in keyword_field_candidates:
            if key in row and str(row.get(key, "")).strip():
                keyword = str(row.get(key, ""))
                break
        k = normalize_keyword(keyword)
        if not k:
            continue
        idx.setdefault(k, []).append(row)
    return idx


def row_match_score(source_row: Dict[str, str], locale: str, platform: str) -> int:
    score = 0
    source_locale = normalize_locale(source_row.get("locale", ""))
    source_platform = normalize_platform(source_row.get("platform", ""))
    if source_locale and locale and source_locale == locale:
        score += 3
    elif not source_locale:
        score += 1
    if source_platform and platform and source_platform == platform:
        score += 2
    elif not source_platform:
        score += 1
    return score


def pick_best_row(rows: List[Dict[str, str]], locale: str, platform: str) -> Optional[Dict[str, str]]:
    if not rows:
        return None
    ranked = sorted(rows, key=lambda r: row_match_score(r, locale, platform), reverse=True)
    return ranked[0]


def avg(values: List[Optional[float]]) -> Optional[float]:
    items = [v for v in values if v is not None]
    if not items:
        return None
    return sum(items) / len(items)


def confidence_band(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def infer_app_scope(
    requested_scope: str,
    keyword_rows: List[Dict[str, str]],
    has_apple_source: bool,
    has_google_source: bool,
    has_itunes_source: bool,
) -> str:
    if requested_scope != "auto":
        return requested_scope

    platforms: Set[str] = set()
    for row in keyword_rows:
        p = normalize_platform(row.get("platform", ""))
        if p in {"apple", "google"}:
            platforms.add(p)

    if platforms == {"apple"}:
        return "ios_only"
    if platforms == {"google"}:
        return "android_only"
    if platforms == {"apple", "google"}:
        return "dual"

    if has_google_source and not (has_apple_source or has_itunes_source):
        return "android_only"
    if (has_apple_source or has_itunes_source) and not has_google_source:
        return "ios_only"
    if has_google_source and (has_apple_source or has_itunes_source):
        return "dual"

    return "dual"


def base_components_for_scope(scope: str) -> Set[str]:
    if scope == "ios_only":
        return {"apple", "apptweak", "competitor", "itunes"}
    if scope == "android_only":
        return {"google", "apptweak", "competitor"}
    return {"apple", "google", "apptweak", "competitor", "itunes"}


def effective_platform_for_scope(scope: str, keyword_platform: str) -> str:
    if scope == "ios_only":
        return "apple"
    if scope == "android_only":
        return "google"
    return keyword_platform


def row_allowed_components(scope: str, row_platform: str) -> Set[str]:
    allowed = set(base_components_for_scope(scope))

    # In dual scope, per-row platform can narrow required components.
    if scope == "dual":
        if row_platform == "apple":
            allowed.discard("google")
        elif row_platform == "google":
            allowed.discard("apple")
            allowed.discard("itunes")
    return allowed


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate ASO keyword demand score using multi-source proxies")
    parser.add_argument("--keywords", required=True, help="CSV path with columns: keyword[,locale,platform]")
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument("--output-json", help="Optional output JSON path")
    parser.add_argument("--apple-proxy", help="CSV with Apple proxy metrics")
    parser.add_argument("--google-planner", help="CSV with Google Planner metrics")
    parser.add_argument("--apptweak", help="CSV with AppTweak-like metrics")
    parser.add_argument("--competitor-terms", help="CSV with competitor term coverage")
    parser.add_argument("--itunes-signals", help="CSV from iTunes keyword discovery")
    parser.add_argument(
        "--app-scope",
        choices=["auto", "ios_only", "android_only", "dual"],
        default="auto",
        help="App platform scope. auto infers from keyword rows and available sources.",
    )
    parser.add_argument("--w-apple", type=float, default=0.30)
    parser.add_argument("--w-google", type=float, default=0.30)
    parser.add_argument("--w-apptweak", type=float, default=0.25)
    parser.add_argument("--w-competitor", type=float, default=0.10)
    parser.add_argument("--w-itunes", type=float, default=0.05)
    args = parser.parse_args()

    try:
        keyword_rows = read_csv(args.keywords)
    except Exception as exc:
        print(f"ERROR: failed to read keywords csv: {exc}")
        return 2

    if not keyword_rows:
        print("ERROR: keywords csv is empty")
        return 2

    if "keyword" not in keyword_rows[0]:
        print("ERROR: keywords csv must include 'keyword' column")
        return 2

    apple_idx: Dict[str, List[Dict[str, str]]] = {}
    google_idx: Dict[str, List[Dict[str, str]]] = {}
    apptweak_idx: Dict[str, List[Dict[str, str]]] = {}
    competitor_idx: Dict[str, List[Dict[str, str]]] = {}
    itunes_idx: Dict[str, List[Dict[str, str]]] = {}

    def load_optional_index(path: Optional[str], fields: List[str]) -> Dict[str, List[Dict[str, str]]]:
        if not path:
            return {}
        rows = read_csv(path)
        return index_rows(rows, fields)

    try:
        apple_idx = load_optional_index(args.apple_proxy, ["keyword", "term"])
        google_idx = load_optional_index(args.google_planner, ["keyword", "term"])
        apptweak_idx = load_optional_index(args.apptweak, ["keyword", "term"])
        competitor_idx = load_optional_index(args.competitor_terms, ["keyword", "term"])
        itunes_idx = load_optional_index(args.itunes_signals, ["keyword", "term"])
    except Exception as exc:
        print(f"ERROR: failed to load optional source csv: {exc}")
        return 2

    inferred_scope = infer_app_scope(
        requested_scope=args.app_scope,
        keyword_rows=keyword_rows,
        has_apple_source=bool(args.apple_proxy),
        has_google_source=bool(args.google_planner),
        has_itunes_source=bool(args.itunes_signals),
    )

    records: List[Dict[str, object]] = []
    for row in keyword_rows:
        keyword = str(row.get("keyword", "")).strip()
        if not keyword:
            continue
        k_norm = normalize_keyword(keyword)
        locale = normalize_locale(row.get("locale", ""))
        raw_platform = normalize_platform(row.get("platform", ""))
        platform = effective_platform_for_scope(inferred_scope, raw_platform)

        apple_row = pick_best_row(apple_idx.get(k_norm, []), locale, platform)
        google_row = pick_best_row(google_idx.get(k_norm, []), locale, platform)
        apptweak_row = pick_best_row(apptweak_idx.get(k_norm, []), locale, platform)
        competitor_row = pick_best_row(competitor_idx.get(k_norm, []), locale, platform)
        itunes_row = pick_best_row(itunes_idx.get(k_norm, []), locale, platform)

        record: Dict[str, object] = {
            "keyword": keyword,
            "locale": row.get("locale", ""),
            "platform": row.get("platform", ""),
            "effective_platform": platform,
            "raw_apple_popularity": extract_metric(apple_row or {}, ["apple_popularity", "popularity", "search_popularity"]),
            "raw_apple_rank": extract_metric(apple_row or {}, ["apple_rank", "rank"]),
            "raw_apple_ttr": extract_metric(apple_row or {}, ["apple_ttr", "ttr", "tap_through_rate"]),
            "raw_google_searches": extract_metric(
                google_row or {}, ["avg_monthly_searches", "google_searches", "monthly_searches"]
            ),
            "raw_google_competition": extract_metric(
                google_row or {}, ["competition_index", "competition"], parser=parse_competition
            ),
            "raw_google_bid": avg(
                [
                    extract_metric(google_row or {}, ["top_of_page_bid_low", "bid_low"]),
                    extract_metric(google_row or {}, ["top_of_page_bid_high", "bid_high"]),
                ]
            ),
            "raw_apptweak_volume": extract_metric(apptweak_row or {}, ["apptweak_volume", "volume"]),
            "raw_apptweak_installs": extract_metric(apptweak_row or {}, ["apptweak_installs", "installs"]),
            "raw_competitor_coverage": extract_metric(
                competitor_row or {}, ["coverage_ratio", "competitor_coverage", "coverage"]
            ),
            "raw_competitor_doc_freq": extract_metric(
                competitor_row or {}, ["document_frequency", "doc_freq", "frequency"]
            ),
            "raw_itunes_score": extract_metric(itunes_row or {}, ["score", "itunes_score"]),
            "raw_itunes_app_coverage": extract_metric(itunes_row or {}, ["app_coverage", "itunes_app_coverage"]),
        }
        records.append(record)

    if not records:
        print("ERROR: no valid keyword rows found")
        return 2

    def column(name: str) -> List[Optional[float]]:
        return [to_float(r.get(name)) for r in records]

    apple_popularity_n = [clamp(v) if v is not None else None for v in column("raw_apple_popularity")]
    apple_rank_n = percentile_scaled(column("raw_apple_rank"), use_log=False, reverse=True)
    apple_ttr_raw = column("raw_apple_ttr")
    apple_ttr_n: List[Optional[float]] = []
    for v in apple_ttr_raw:
        if v is None:
            apple_ttr_n.append(None)
            continue
        apple_ttr_n.append(clamp(v * 100.0 if v <= 1.0 else v))

    google_searches_n = percentile_scaled(column("raw_google_searches"), use_log=True, reverse=False)
    google_comp_n = [clamp(v) if v is not None else None for v in column("raw_google_competition")]
    google_bid_n = percentile_scaled(column("raw_google_bid"), use_log=True, reverse=False)

    apptweak_volume_n = [clamp(v) if v is not None else None for v in column("raw_apptweak_volume")]
    apptweak_installs_n = percentile_scaled(column("raw_apptweak_installs"), use_log=True, reverse=False)

    comp_cov_raw = column("raw_competitor_coverage")
    comp_cov_n: List[Optional[float]] = []
    for v in comp_cov_raw:
        if v is None:
            comp_cov_n.append(None)
            continue
        if v <= 1.0:
            comp_cov_n.append(clamp(v * 100.0))
        else:
            comp_cov_n.append(clamp(v))
    comp_doc_n = percentile_scaled(column("raw_competitor_doc_freq"), use_log=True, reverse=False)

    itunes_score_n = percentile_scaled(column("raw_itunes_score"), use_log=True, reverse=False)
    itunes_cov_n = percentile_scaled(column("raw_itunes_app_coverage"), use_log=False, reverse=False)

    weights = {
        "apple": max(0.0, args.w_apple),
        "google": max(0.0, args.w_google),
        "apptweak": max(0.0, args.w_apptweak),
        "competitor": max(0.0, args.w_competitor),
        "itunes": max(0.0, args.w_itunes),
    }

    # Scope-aware hard exclusions to prevent wasted processing.
    if inferred_scope == "ios_only":
        weights["google"] = 0.0
    elif inferred_scope == "android_only":
        weights["apple"] = 0.0
        weights["itunes"] = 0.0

    total_weight = sum(weights.values())
    if total_weight <= 0:
        print("ERROR: at least one component weight must be > 0")
        return 2

    out_rows: List[Dict[str, object]] = []
    for i, base in enumerate(records):
        apple_score = avg([apple_popularity_n[i], apple_rank_n[i], apple_ttr_n[i]])
        google_score = avg([google_searches_n[i], google_comp_n[i], google_bid_n[i]])
        apptweak_score = avg([apptweak_volume_n[i], apptweak_installs_n[i]])
        competitor_score = avg([comp_cov_n[i], comp_doc_n[i]])
        itunes_score = avg([itunes_score_n[i], itunes_cov_n[i]])

        components: Dict[str, Optional[float]] = {
            "apple": apple_score,
            "google": google_score,
            "apptweak": apptweak_score,
            "competitor": competitor_score,
            "itunes": itunes_score,
        }

        allowed = row_allowed_components(inferred_scope, str(base.get("effective_platform", "")))
        target_components = {name for name in allowed if weights.get(name, 0.0) > 0}
        target_weight = sum(weights[name] for name in target_components)
        available = {k: v for k, v in components.items() if k in target_components and v is not None}

        if not available or target_weight <= 0:
            demand_score = 0.0
            conf_score = 0.0
            sources = ""
        else:
            avail_weight = sum(weights[k] for k in available.keys())
            demand_score = 0.0
            for name, value in available.items():
                demand_score += (weights[name] / avail_weight) * float(value)

            coverage_ratio = avail_weight / target_weight
            source_density = len(available) / len(target_components)
            conf_score = ((coverage_ratio * 0.7) + (source_density * 0.3)) * 100.0
            sources = "|".join(sorted(available.keys()))

        def display_component(name: str, value: Optional[float]) -> object:
            if name not in target_components or value is None:
                return ""
            return round(value, 2)

        row = {
            "keyword": base["keyword"],
            "locale": base["locale"],
            "platform": base["platform"],
            "effective_platform": base["effective_platform"],
            "app_scope": inferred_scope,
            "estimated_demand_score": round(demand_score, 2),
            "confidence_score": round(conf_score, 2),
            "confidence_band": confidence_band(conf_score),
            "apple_score": display_component("apple", apple_score),
            "google_score": display_component("google", google_score),
            "apptweak_score": display_component("apptweak", apptweak_score),
            "competitor_score": display_component("competitor", competitor_score),
            "itunes_score": display_component("itunes", itunes_score),
            "evidence_sources": sources,
        }
        out_rows.append(row)

    out_rows.sort(
        key=lambda r: (float(r["estimated_demand_score"]), float(r["confidence_score"])),
        reverse=True,
    )
    for idx, row in enumerate(out_rows, start=1):
        row["rank"] = idx

    headers = [
        "rank",
        "keyword",
        "locale",
        "platform",
        "effective_platform",
        "app_scope",
        "estimated_demand_score",
        "confidence_score",
        "confidence_band",
        "apple_score",
        "google_score",
        "apptweak_score",
        "competitor_score",
        "itunes_score",
        "evidence_sources",
    ]

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in out_rows:
            writer.writerow(row)

    if args.output_json:
        payload = {
            "app_scope": inferred_scope,
            "weights": weights,
            "total_keywords": len(out_rows),
            "rows": out_rows,
        }
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

    print(f"Inferred app scope: {inferred_scope}")
    print(f"Wrote demand estimates: {args.output}")
    if args.output_json:
        print(f"Wrote JSON report: {args.output_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
