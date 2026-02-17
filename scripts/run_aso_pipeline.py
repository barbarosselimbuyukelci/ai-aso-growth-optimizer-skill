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

    play_patterns = analysis_dir / "play_competitor_common_patterns.csv"
    play_rows = read_csv_rows(play_patterns)
    if play_rows:
        common = [r for r in play_rows if str(r.get("is_common", "0")).strip() == "1"][:5]
        if common:
            lines.append("Common Android competitor motifs:")
            for row in common:
                lines.append(f"- `{row.get('motif','')}` prevalence=`{row.get('prevalence','')}`")

    lines.extend(["", "## Generated Artifacts"])
    key_files = [
        output_dir / "metadata_bundle.json",
        output_dir / "cpp_manifest.json",
        output_dir / "psl_manifest.json",
        output_dir / "cpp_psl_summary.json",
        output_dir / "pipeline_run_log.json",
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

    finalize_run(log, status="ok", log_path=log_path, summary_path=human_summary_path, output_dir=output_dir)
    print(f"Pipeline completed. Log: {log_path}")
    print(f"Human summary: {human_summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
