#!/usr/bin/env python3
"""
Approval-gated ASO pipeline runner.

Each step:
1) Shows what will run
2) Asks for user approval
3) Asks if user wants to add anything

Use --auto-approve for non-interactive CI usage.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd: List[str], workdir: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(workdir) if workdir else None, text=True, capture_output=True)


def prompt_yes_no(message: str, default_no: bool = True) -> bool:
    suffix = " [y/N]: " if default_no else " [Y/n]: "
    ans = input(message + suffix).strip().lower()
    if not ans:
        return not default_no
    return ans in {"y", "yes"}


def prompt_note(message: str) -> str:
    return input(message + " ").strip()


def gate_step(
    *,
    step_id: str,
    title: str,
    summary: str,
    cmd: List[str],
    log: Dict[str, Any],
    auto_approve: bool,
    workdir: Optional[Path] = None,
) -> bool:
    print("")
    print(f"=== {step_id} | {title} ===")
    print(summary)
    print("Command:")
    print("  " + " ".join(cmd))

    user_note = ""
    approved = True
    if not auto_approve:
        approved = prompt_yes_no("Continue with this step?")
        user_note = prompt_note("Any additions/changes before running this step? (empty to skip)")

    step_entry: Dict[str, Any] = {
        "step_id": step_id,
        "title": title,
        "summary": summary,
        "command": cmd,
        "approved": approved,
        "user_note": user_note,
        "started_at_utc": utc_now(),
    }

    if not approved:
        step_entry["status"] = "stopped_by_user"
        step_entry["finished_at_utc"] = utc_now()
        log["steps"].append(step_entry)
        print("Stopped by user.")
        return False

    res = run_cmd(cmd, workdir=workdir)
    step_entry["return_code"] = res.returncode
    step_entry["stdout"] = res.stdout
    step_entry["stderr"] = res.stderr
    step_entry["status"] = "ok" if res.returncode == 0 else "failed"
    step_entry["finished_at_utc"] = utc_now()
    log["steps"].append(step_entry)

    if res.stdout.strip():
        print(res.stdout.strip())
    if res.stderr.strip():
        print(res.stderr.strip())

    if res.returncode != 0:
        print(f"Step failed: {step_id}")
        return False
    return True


def log_decision_step(
    *,
    step_id: str,
    title: str,
    summary: str,
    approved: bool,
    log: Dict[str, Any],
    user_note: str = "",
) -> None:
    step_entry: Dict[str, Any] = {
        "step_id": step_id,
        "title": title,
        "summary": summary,
        "command": [],
        "approved": approved,
        "user_note": user_note,
        "started_at_utc": utc_now(),
        "finished_at_utc": utc_now(),
        "status": "ok" if approved else "stopped_by_user",
        "return_code": 0 if approved else 1,
        "stdout": "",
        "stderr": "",
    }
    log["steps"].append(step_entry)


def gate_decision(
    *,
    step_id: str,
    title: str,
    summary: str,
    prompt_message: str,
    log: Dict[str, Any],
    auto_approve: bool,
) -> bool:
    print("")
    print(f"=== {step_id} | {title} ===")
    print(summary)
    approved = True
    user_note = ""
    if not auto_approve:
        approved = prompt_yes_no(prompt_message, default_no=False)
        user_note = prompt_note("Any additions/changes before continuing? (empty to skip)")
    log_decision_step(
        step_id=step_id,
        title=title,
        summary=summary,
        approved=approved,
        log=log,
        user_note=user_note,
    )
    if not approved:
        print("Stopped by user.")
    return approved


def parse_csv_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def safe_json_load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return data


def print_variant_preview(metadata_bundle: Path, max_locales: int = 5) -> None:
    if not metadata_bundle.exists():
        print(f"Variant preview unavailable: missing {metadata_bundle}")
        return
    payload = safe_json_load(metadata_bundle)
    locales = payload.get("locales", [])
    if not isinstance(locales, list) or not locales:
        print("Variant preview unavailable: metadata bundle has no locales.")
        return
    print("")
    print("=== Variant Preview ===")
    for item in locales[:max_locales]:
        if not isinstance(item, dict):
            continue
        locale = str(item.get("locale", ""))
        apple = item.get("apple", {}) if isinstance(item.get("apple"), dict) else {}
        google = item.get("google", {}) if isinstance(item.get("google"), dict) else {}
        print(f"[{locale}]")
        print(f"  Apple title: {str(apple.get('title', ''))[:80]}")
        print(f"  Apple subtitle: {str(apple.get('subtitle', ''))[:80]}")
        print(f"  Google title: {str(google.get('title', ''))[:80]}")
        print(f"  Google short: {str(google.get('short_description', ''))[:80]}")
    if len(locales) > max_locales:
        print(f"... {len(locales) - max_locales} more locales omitted")
    print("=== End Variant Preview ===")


def build_translation_batch_from_bundle(
    *,
    metadata_bundle: Path,
    platform: str,
    source_locale: str,
    output_path: Path,
) -> bool:
    payload = safe_json_load(metadata_bundle)
    locales = payload.get("locales", [])
    if not isinstance(locales, list) or len(locales) < 2:
        return False

    rows: Dict[str, Dict[str, str]] = {}
    locale_values: Dict[str, Dict[str, str]] = {}
    for item in locales:
        if not isinstance(item, dict):
            continue
        locale = str(item.get("locale", "")).strip()
        if not locale:
            continue
        block = item.get(platform, {})
        if not isinstance(block, dict):
            continue
        normalized: Dict[str, str] = {}
        for field, value in block.items():
            if isinstance(value, str):
                normalized[str(field)] = value.strip()
        if normalized:
            locale_values[locale] = normalized

    if source_locale not in locale_values:
        source_locale = sorted(locale_values.keys())[0] if locale_values else ""
    if not source_locale:
        return False

    target_locales = [l for l in sorted(locale_values.keys()) if l != source_locale]
    if not target_locales:
        return False

    source_fields = locale_values.get(source_locale, {})
    entries: List[Dict[str, Any]] = []
    for field, source_text in source_fields.items():
        if not source_text:
            continue
        translations: Dict[str, str] = {}
        for loc in target_locales:
            translations[loc] = locale_values.get(loc, {}).get(field, "")
        entries.append(
            {
                "id": f"{platform}_{field}",
                "field": field,
                "source_text": source_text,
                "translations": translations,
            }
        )

    if not entries:
        return False

    app_name = str(payload.get("app_name", "")).strip()
    out_payload = {
        "platform": platform,
        "source_locale": source_locale,
        "target_locales": target_locales,
        "protected_terms": [app_name] if app_name else [],
        "entries": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def apply_generated_fastlane_metadata(generated_root: Path, target_root: Path) -> None:
    if not generated_root.exists():
        raise FileNotFoundError(f"Generated metadata directory not found: {generated_root}")
    target_root.mkdir(parents=True, exist_ok=True)
    for child in generated_root.iterdir():
        dest = target_root / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        elif child.is_file():
            shutil.copy2(child, dest)


def git_has_changes(repo_dir: Path) -> bool:
    res = run_cmd(["git", "-C", str(repo_dir), "status", "--porcelain"])
    return res.returncode == 0 and bool(res.stdout.strip())


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_human_summary(path: Path, log: Dict[str, Any], output_dir: Path) -> None:
    steps = log.get("steps", [])
    status = str(log.get("status", "unknown"))
    analysis_dir = output_dir / "analysis"

    lines: List[str] = [
        "# ASO Pipeline Human Summary",
        "",
        "## Run Snapshot",
        f"- Status: `{status}`",
        f"- Started: `{log.get('started_at_utc', '')}`",
        f"- Finished: `{log.get('finished_at_utc', '')}`",
        f"- App scope: `{log.get('app_scope', '')}`",
        f"- Output dir: `{output_dir}`",
        "",
        "## What Was Analyzed",
    ]

    if not steps:
        lines.append("- No step executed.")
    else:
        for s in steps:
            lines.append(f"- `{s.get('step_id','')}` {s.get('title','')}: {s.get('summary','')}")

    lines.extend(["", "## Step Results"])
    for s in steps:
        rc = s.get("return_code", "")
        lines.append(f"- `{s.get('step_id','')}` `{s.get('status','')}` rc=`{rc}` {s.get('title','')}")

    keyword_csv = analysis_dir / "keyword_volume_estimates.csv"
    keyword_rows = read_csv_rows(keyword_csv)
    if keyword_rows:
        lines.extend(["", "## Key Findings", "Top keyword opportunities:"])
        top = keyword_rows[:3]
        for row in top:
            lines.append(
                f"- `{row.get('keyword','')}` demand=`{row.get('estimated_demand_score','')}` confidence=`{row.get('confidence_band','')}`"
            )

    ios_patterns = analysis_dir / "ios_competitor_common_patterns.csv"
    ios_rows = read_csv_rows(ios_patterns)
    if ios_rows:
        common = [r for r in ios_rows if str(r.get("is_common", "0")).strip() == "1"][:5]
        if common:
            lines.append("Common iOS competitor motifs:")
            for row in common:
                lines.append(f"- `{row.get('motif','')}` prevalence=`{row.get('prevalence','')}`")
    ios_semantics = analysis_dir / "ios_competitor_semantic_themes.csv"
    ios_semantic_rows = read_csv_rows(ios_semantics)
    if ios_semantic_rows:
        top_semantic = sorted(
            ios_semantic_rows,
            key=lambda r: float(str(r.get("prevalence", "0") or "0")),
            reverse=True,
        )[:5]
        top_semantic = [r for r in top_semantic if float(str(r.get("prevalence", "0") or "0")) > 0]
        if top_semantic:
            lines.append("Top iOS semantic themes:")
            for row in top_semantic:
                lines.append(
                    f"- `{row.get('theme','')}` prevalence=`{row.get('prevalence','')}` top_terms=`{row.get('top_terms','')}`"
                )

    play_patterns = analysis_dir / "play_competitor_common_patterns.csv"
    play_rows = read_csv_rows(play_patterns)
    if play_rows:
        common = [r for r in play_rows if str(r.get("is_common", "0")).strip() == "1"][:5]
        if common:
            lines.append("Common Android competitor motifs:")
            for row in common:
                lines.append(f"- `{row.get('motif','')}` prevalence=`{row.get('prevalence','')}`")
    play_semantics = analysis_dir / "play_competitor_semantic_themes.csv"
    play_semantic_rows = read_csv_rows(play_semantics)
    if play_semantic_rows:
        top_semantic = sorted(
            play_semantic_rows,
            key=lambda r: float(str(r.get("prevalence", "0") or "0")),
            reverse=True,
        )[:5]
        top_semantic = [r for r in top_semantic if float(str(r.get("prevalence", "0") or "0")) > 0]
        if top_semantic:
            lines.append("Top Android semantic themes:")
            for row in top_semantic:
                lines.append(
                    f"- `{row.get('theme','')}` prevalence=`{row.get('prevalence','')}` top_terms=`{row.get('top_terms','')}`"
                )

    gap_report = analysis_dir / "app_competitor_gap_report.md"
    if gap_report.exists():
        lines.append(f"App-vs-competitor gap report: `{gap_report}`")

    for qa_name in ["translation_qa_apple.json", "translation_qa_google.json"]:
        qa_path = analysis_dir / qa_name
        if qa_path.exists():
            try:
                qa_payload = json.loads(qa_path.read_text(encoding="utf-8-sig"))
                summary = qa_payload.get("summary", {})
                warnings = int(summary.get("warnings", 0))
                errors = int(summary.get("errors", 0))
                lines.append(f"{qa_name}: warnings=`{warnings}` errors=`{errors}`")
            except Exception:
                lines.append(f"{qa_name}: available")

    lines.extend(["", "## Generated Artifacts"])
    key_files = [
        output_dir / "metadata_bundle.json",
        output_dir / "cpp_manifest.json",
        output_dir / "psl_manifest.json",
        output_dir / "cpp_psl_summary.json",
        output_dir / "pipeline_run_log.json",
        analysis_dir / "app_competitor_gap_report.md",
        analysis_dir / "translation_qa_apple.json",
        analysis_dir / "translation_qa_google.json",
    ]
    for f in key_files:
        if f.exists():
            lines.append(f"- `{f}`")

    errors: List[str] = []
    for s in steps:
        if str(s.get("status", "")) == "failed":
            errors.append(f"{s.get('step_id','')}: command failed (rc={s.get('return_code','')})")
        stderr = str(s.get("stderr", "")).strip()
        if stderr:
            errors.append(f"{s.get('step_id','')}: stderr present")
    if errors:
        lines.extend(["", "## Warnings / Errors"])
        for e in errors:
            lines.append(f"- {e}")

    lines.extend(
        [
            "",
            "## Next Actions",
            "- Review metadata_bundle and manifests before publish.",
            "- If localization warnings exist, revise copy and rerun.",
            "- Run fastlane push in dry-run first, then execute.",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def finalize_run(log: Dict[str, Any], *, status: str, log_path: Path, summary_path: Path, output_dir: Path) -> None:
    log["finished_at_utc"] = utc_now()
    log["status"] = status
    write_json(log_path, log)
    write_human_summary(summary_path, log, output_dir)
    print("")
    print("=== Human Summary ===")
    try:
        print(summary_path.read_text(encoding="utf-8").rstrip())
    except Exception as exc:
        print(f"Could not read human summary file: {exc}")
    print("=== End Human Summary ===")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ASO pipeline with mandatory approval gates")
    parser.add_argument("--keyword-input", help="Keyword CSV for demand estimation")
    parser.add_argument("--apple-proxy", help="Apple proxy CSV for keyword estimation")
    parser.add_argument("--google-planner", help="Google planner CSV for keyword estimation")
    parser.add_argument("--apptweak", help="AppTweak-like CSV for keyword estimation")
    parser.add_argument("--competitor-terms", help="Competitor term CSV for keyword estimation")
    parser.add_argument("--itunes-signals", help="iTunes signal CSV for keyword estimation")
    parser.add_argument("--ios-seeds", help="Comma-separated seeds for iOS competitor analysis")
    parser.add_argument("--ios-country", default="us", help="Country for iOS competitor analysis")
    parser.add_argument("--play-raw-export", help="Raw Play competitor export CSV to normalize+analyze")
    parser.add_argument("--play-mapping-json", help="Optional JSON mapping for Play export normalization")
    parser.add_argument("--metadata-input", required=True, help="Input JSON for metadata generation")
    parser.add_argument("--output-dir", required=True, help="Pipeline output directory")
    parser.add_argument("--app-scope", choices=["auto", "ios_only", "android_only", "dual"], default="auto")
    parser.add_argument("--app-identifier", help="iOS bundle id for fastlane deliver")
    parser.add_argument("--package-name", help="Android package name for fastlane supply")
    parser.add_argument("--push-ios", action="store_true", help="Include iOS fastlane push step")
    parser.add_argument("--push-android", action="store_true", help="Include Android fastlane push step")
    parser.add_argument("--execute-push", action="store_true", help="Actually execute fastlane push commands")
    parser.add_argument("--auto-approve", action="store_true", help="Skip interactive approval prompts")
    parser.add_argument("--log-out", help="Optional path for pipeline run log JSON")
    parser.add_argument("--human-summary-out", help="Optional path for human-readable Markdown summary")
    parser.add_argument("--current-metadata-root", help="Current app fastlane metadata root for competitor gap analysis")
    parser.add_argument("--compare-locales", default="en-US", help="Comma-separated locales for app-vs-competitor comparison")
    parser.add_argument("--compare-common-threshold", type=float, default=0.6, help="Commonity threshold for motif/theme gaps")
    parser.add_argument("--compare-min-keyword-coverage", type=float, default=0.3, help="Min coverage ratio for missing keyword suggestions")
    parser.add_argument("--localization-source-locale", default="en-US", help="Source locale for translation semantic audit")
    parser.add_argument("--fail-on-localization-warn", action="store_true", help="Fail localization QA step when warnings are present")
    parser.add_argument("--apply-generated-metadata", action="store_true", help="Apply generated fastlane metadata into target path after variant approval")
    parser.add_argument("--target-metadata-root", help="Target fastlane metadata root for applying generated files")
    parser.add_argument("--git-workdir", default=".", help="Git repo directory for commit/push steps")
    parser.add_argument("--git-commit", action="store_true", help="Commit applied metadata/manifests")
    parser.add_argument("--git-push", action="store_true", help="Push committed changes")
    parser.add_argument("--git-remote", default="origin", help="Git remote name for push")
    parser.add_argument("--git-branch", help="Git branch to push (defaults to current tracking branch)")
    parser.add_argument("--git-commit-message", default="ASO: apply metadata + CPP/PSL variants", help="Commit message for git commit step")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = Path(args.log_out).resolve() if args.log_out else output_dir / "pipeline_run_log.json"
    human_summary_path = (
        Path(args.human_summary_out).resolve()
        if args.human_summary_out
        else output_dir / "pipeline_human_summary.md"
    )
    log: Dict[str, Any] = {
        "started_at_utc": utc_now(),
        "app_scope": args.app_scope,
        "metadata_input": str(Path(args.metadata_input).resolve()),
        "output_dir": str(output_dir),
        "steps": [],
    }

    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    metadata_bundle = output_dir / "metadata_bundle.json"
    generated_fastlane_metadata = output_dir / "fastlane" / "metadata"
    current_metadata_root = Path(args.current_metadata_root).resolve() if args.current_metadata_root else None
    target_metadata_root = (
        Path(args.target_metadata_root).resolve()
        if args.target_metadata_root
        else (current_metadata_root if current_metadata_root else None)
    )
    compare_locales = parse_csv_list(args.compare_locales)

    if args.keyword_input:
        keyword_out = analysis_dir / "keyword_volume_estimates.csv"
        keyword_out_json = analysis_dir / "keyword_volume_estimates.json"
        cmd = [
            sys.executable,
            str(script_dir / "aso_keyword_volume_estimator.py"),
            "--keywords",
            str(Path(args.keyword_input).resolve()),
            "--app-scope",
            args.app_scope,
            "--output",
            str(keyword_out),
            "--output-json",
            str(keyword_out_json),
        ]
        if args.apple_proxy:
            cmd += ["--apple-proxy", str(Path(args.apple_proxy).resolve())]
        if args.google_planner:
            cmd += ["--google-planner", str(Path(args.google_planner).resolve())]
        if args.apptweak:
            cmd += ["--apptweak", str(Path(args.apptweak).resolve())]
        if args.competitor_terms:
            cmd += ["--competitor-terms", str(Path(args.competitor_terms).resolve())]
        if args.itunes_signals:
            cmd += ["--itunes-signals", str(Path(args.itunes_signals).resolve())]

        step_ok = gate_step(
            step_id="A1",
            title="Keyword Demand Analysis",
            summary="Analyze keyword demand scores and confidence bands before metadata generation.",
            cmd=cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    if args.ios_seeds:
        ios_cmd = [
            sys.executable,
            str(script_dir / "aso_competitor_matrix_builder.py"),
            "--seeds",
            args.ios_seeds,
            "--app-scope",
            args.app_scope,
            "--country",
            args.ios_country,
            "--output-dir",
            str(analysis_dir),
            "--prefix",
            "ios_competitor",
        ]
        step_ok = gate_step(
            step_id="A2",
            title="iOS Competitor Analysis",
            summary="Build iOS competitor matrix and shared pattern report from iTunes data.",
            cmd=ios_cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    if args.play_raw_export:
        normalized_play = analysis_dir / "play_competitor_normalized.csv"
        normalize_cmd = [
            sys.executable,
            str(script_dir / "aso_play_export_normalizer.py"),
            "--input",
            str(Path(args.play_raw_export).resolve()),
            "--output",
            str(normalized_play),
        ]
        if args.play_mapping_json:
            normalize_cmd += ["--mapping-json", str(Path(args.play_mapping_json).resolve())]

        step_ok = gate_step(
            step_id="A3",
            title="Play Export Normalization",
            summary="Normalize raw Play export into analyzer-ready schema.",
            cmd=normalize_cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

        play_cmd = [
            sys.executable,
            str(script_dir / "aso_play_competitor_import_analyzer.py"),
            "--input",
            str(normalized_play),
            "--app-scope",
            args.app_scope,
            "--output-dir",
            str(analysis_dir),
            "--prefix",
            "play_competitor",
        ]
        step_ok = gate_step(
            step_id="A4",
            title="Android Competitor Analysis",
            summary="Build Play competitor matrix and shared pattern report from normalized export.",
            cmd=play_cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    has_competitor_outputs = any(
        (analysis_dir / p).exists()
        for p in [
            "ios_competitor_common_patterns.csv",
            "play_competitor_common_patterns.csv",
            "ios_competitor_semantic_themes.csv",
            "play_competitor_semantic_themes.csv",
        ]
    )
    if current_metadata_root and has_competitor_outputs:
        gap_json = analysis_dir / "app_competitor_gap_report.json"
        gap_md = analysis_dir / "app_competitor_gap_report.md"
        gap_cmd = [
            sys.executable,
            str(script_dir / "aso_competitive_gap_analyzer.py"),
            "--analysis-dir",
            str(analysis_dir),
            "--app-metadata-root",
            str(current_metadata_root),
            "--locales",
            ",".join(compare_locales) if compare_locales else "en-US",
            "--app-scope",
            args.app_scope,
            "--common-threshold",
            str(args.compare_common_threshold),
            "--min-keyword-coverage",
            str(args.compare_min_keyword_coverage),
            "--output-json",
            str(gap_json),
            "--output-md",
            str(gap_md),
        ]
        step_ok = gate_step(
            step_id="A5",
            title="App vs Competitor Gap Analysis",
            summary="Compare current app metadata against competitor motifs/themes and missing keyword emphasis.",
            cmd=gap_cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    step_ok = gate_step(
        step_id="S1",
        title="Generate Metadata",
        summary="Generate new Apple/Google metadata files and fastlane metadata folders.",
        cmd=[
            sys.executable,
            str(script_dir / "aso_metadata_generator.py"),
            "--input",
            str(Path(args.metadata_input).resolve()),
            "--output-dir",
            str(output_dir),
            "--bundle-out",
            str(metadata_bundle),
        ],
        log=log,
        auto_approve=args.auto_approve,
    )
    if not step_ok:
        finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
        return 1

    apple_batch = analysis_dir / "translation_batch_apple.json"
    google_batch = analysis_dir / "translation_batch_google.json"
    has_apple_translation_batch = build_translation_batch_from_bundle(
        metadata_bundle=metadata_bundle,
        platform="apple",
        source_locale=args.localization_source_locale,
        output_path=apple_batch,
    )
    has_google_translation_batch = build_translation_batch_from_bundle(
        metadata_bundle=metadata_bundle,
        platform="google",
        source_locale=args.localization_source_locale,
        output_path=google_batch,
    )

    if has_apple_translation_batch and args.app_scope in {"auto", "ios_only", "dual"}:
        apple_qa_out = analysis_dir / "translation_qa_apple.json"
        apple_qa_cmd = [
            sys.executable,
            str(script_dir / "aso_translation_semantic_audit.py"),
            "--input",
            str(apple_batch),
            "--platform",
            "apple",
            "--output",
            str(apple_qa_out),
        ]
        if args.fail_on_localization_warn:
            apple_qa_cmd.append("--fail-on-warn")
        step_ok = gate_step(
            step_id="L1",
            title="Localization Semantic QA (Apple)",
            summary="Validate multi-locale semantic integrity, placeholders, numeric tokens, and cultural adaptation signals.",
            cmd=apple_qa_cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    if has_google_translation_batch and args.app_scope in {"auto", "android_only", "dual"}:
        google_qa_out = analysis_dir / "translation_qa_google.json"
        google_qa_cmd = [
            sys.executable,
            str(script_dir / "aso_translation_semantic_audit.py"),
            "--input",
            str(google_batch),
            "--platform",
            "google",
            "--output",
            str(google_qa_out),
        ]
        if args.fail_on_localization_warn:
            google_qa_cmd.append("--fail-on-warn")
        step_ok = gate_step(
            step_id="L2",
            title="Localization Semantic QA (Google)",
            summary="Validate multi-locale semantic integrity, placeholders, numeric tokens, and cultural adaptation signals.",
            cmd=google_qa_cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    print_variant_preview(metadata_bundle)
    accepted = gate_decision(
        step_id="V1",
        title="Variant Acceptance Gate",
        summary="Review generated locale variants and confirm whether to proceed with CPP/PSL generation and apply/push steps.",
        prompt_message="Approve generated variants?",
        log=log,
        auto_approve=args.auto_approve,
    )
    if not accepted:
        finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
        return 1

    step_ok = gate_step(
        step_id="S2",
        title="Build CPP/PSL",
        summary="Create CPP and/or PSL manifests from generated metadata bundle according to app scope.",
        cmd=[
            sys.executable,
            str(script_dir / "aso_cpp_psl_builder.py"),
            "--input-bundle",
            str(metadata_bundle),
            "--output-dir",
            str(output_dir),
            "--app-scope",
            args.app_scope,
        ],
        log=log,
        auto_approve=args.auto_approve,
    )
    if not step_ok:
        finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
        return 1

    if args.apply_generated_metadata:
        if not target_metadata_root:
            print("ERROR: --target-metadata-root (or --current-metadata-root) is required when --apply-generated-metadata is set")
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 2
        apply_ok = gate_decision(
            step_id="S2A",
            title="Apply Generated Metadata",
            summary=f"Copy generated metadata from `{generated_fastlane_metadata}` to `{target_metadata_root}`.",
            prompt_message="Apply generated metadata files to target path?",
            log=log,
            auto_approve=args.auto_approve,
        )
        if not apply_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1
        try:
            apply_generated_fastlane_metadata(generated_fastlane_metadata, target_metadata_root)
            print(f"Applied metadata to: {target_metadata_root}")
        except Exception as exc:
            print(f"ERROR: failed to apply generated metadata: {exc}")
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    if args.push_ios:
        if not args.app_identifier:
            print("ERROR: --app-identifier is required when --push-ios is set")
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 2
        cmd = [
            sys.executable,
            str(script_dir / "aso_fastlane_bridge.py"),
            "--platform",
            "ios",
            "--lane",
            "deliver",
            "--app-scope",
            args.app_scope,
            "--app-identifier",
            args.app_identifier,
            "--metadata-path",
            str(output_dir / "fastlane" / "metadata"),
        ]
        if args.execute_push:
            cmd.append("--execute")

        step_ok = gate_step(
            step_id="S3",
            title="Push iOS Metadata",
            summary="Push iOS metadata via fastlane deliver (dry-run unless --execute-push).",
            cmd=cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    if args.push_android:
        if not args.package_name:
            print("ERROR: --package-name is required when --push-android is set")
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 2
        cmd = [
            sys.executable,
            str(script_dir / "aso_fastlane_bridge.py"),
            "--platform",
            "android",
            "--lane",
            "supply",
            "--app-scope",
            args.app_scope,
            "--package-name",
            args.package_name,
            "--metadata-path",
            str(output_dir / "fastlane" / "metadata" / "android"),
        ]
        if args.execute_push:
            cmd.append("--execute")

        step_ok = gate_step(
            step_id="S4",
            title="Push Android Metadata",
            summary="Push Android metadata via fastlane supply (dry-run unless --execute-push).",
            cmd=cmd,
            log=log,
            auto_approve=args.auto_approve,
        )
        if not step_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    repo_dir = Path(args.git_workdir).resolve()
    if args.git_commit:
        if not repo_dir.exists():
            print(f"ERROR: git workdir not found: {repo_dir}")
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 2
        stage_ok = gate_step(
            step_id="G1",
            title="Git Stage Changes",
            summary="Stage modified files before commit.",
            cmd=["git", "-C", str(repo_dir), "add", "-A"],
            log=log,
            auto_approve=args.auto_approve,
        )
        if not stage_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

        if git_has_changes(repo_dir):
            commit_ok = gate_step(
                step_id="G2",
                title="Git Commit",
                summary="Commit ASO metadata/variant changes.",
                cmd=["git", "-C", str(repo_dir), "commit", "-m", args.git_commit_message],
                log=log,
                auto_approve=args.auto_approve,
            )
            if not commit_ok:
                finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
                return 1
        else:
            log_decision_step(
                step_id="G2",
                title="Git Commit",
                summary="No staged changes to commit.",
                approved=True,
                log=log,
            )
            print("No git changes to commit.")

    if args.git_push:
        branch = args.git_branch
        if not branch:
            res = run_cmd(["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"])
            branch = res.stdout.strip() if res.returncode == 0 else ""
        if not branch:
            print("ERROR: could not determine git branch for push")
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 2
        push_ok = gate_step(
            step_id="G3",
            title="Git Push",
            summary=f"Push branch `{branch}` to remote `{args.git_remote}`.",
            cmd=["git", "-C", str(repo_dir), "push", args.git_remote, branch],
            log=log,
            auto_approve=args.auto_approve,
        )
        if not push_ok:
            finalize_run(log, status="failed", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
            return 1

    finalize_run(log, status="ok", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
    print(f"Pipeline completed. Log: {log_path}")
    print(f"Human summary: {human_summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
