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
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = Path(args.log_out).resolve() if args.log_out else output_dir / "pipeline_run_log.json"
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
            write_json(log_path, log)
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
            write_json(log_path, log)
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
            write_json(log_path, log)
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
            write_json(log_path, log)
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
        write_json(log_path, log)
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
        write_json(log_path, log)
        return 1

    if args.push_ios:
        if not args.app_identifier:
            print("ERROR: --app-identifier is required when --push-ios is set")
            write_json(log_path, log)
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
            write_json(log_path, log)
            return 1

    if args.push_android:
        if not args.package_name:
            print("ERROR: --package-name is required when --push-android is set")
            write_json(log_path, log)
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
            write_json(log_path, log)
            return 1

    log["finished_at_utc"] = utc_now()
    log["status"] = "ok"
    write_json(log_path, log)
    print(f"Pipeline completed. Log: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
