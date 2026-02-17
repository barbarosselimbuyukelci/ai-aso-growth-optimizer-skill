#!/usr/bin/env python3
"""
Generate or execute fastlane commands for ASO metadata operations.
Dry-run by default.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from typing import List


def build_ios_deliver(app_identifier: str, metadata_path: str, skip_screenshots: bool) -> List[str]:
    return [
        "bundle",
        "exec",
        "fastlane",
        "deliver",
        "--app_identifier",
        app_identifier,
        "--metadata_path",
        metadata_path,
        "--skip_binary_upload",
        "true",
        "--skip_screenshots",
        "true" if skip_screenshots else "false",
        "--force",
        "true",
    ]


def build_android_supply(package_name: str, metadata_path: str, skip_images: bool) -> List[str]:
    return [
        "bundle",
        "exec",
        "fastlane",
        "supply",
        "--package_name",
        package_name,
        "--metadata_path",
        metadata_path,
        "--skip_upload_apk",
        "true",
        "--skip_upload_aab",
        "true",
        "--skip_upload_images",
        "true" if skip_images else "false",
    ]


def infer_scope(requested_scope: str, platform: str, has_ios_id: bool, has_android_id: bool) -> str:
    if requested_scope != "auto":
        return requested_scope
    if has_ios_id and has_android_id:
        return "dual"
    if platform == "ios":
        return "ios_only"
    if platform == "android":
        return "android_only"
    return "dual"


def scope_mismatch(scope: str, platform: str) -> bool:
    if scope == "ios_only" and platform == "android":
        return True
    if scope == "android_only" and platform == "ios":
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="ASO fastlane bridge")
    parser.add_argument("--platform", choices=["ios", "android"], required=True)
    parser.add_argument("--lane", choices=["deliver", "supply"], required=True)
    parser.add_argument("--metadata-path", required=True)
    parser.add_argument("--app-identifier", help="Required for iOS/deliver")
    parser.add_argument("--package-name", help="Required for Android/supply")
    parser.add_argument("--skip-screenshots", action="store_true", help="iOS: skip screenshot upload")
    parser.add_argument("--skip-images", action="store_true", help="Android: skip image upload")
    parser.add_argument(
        "--app-scope",
        choices=["auto", "ios_only", "android_only", "dual"],
        default="auto",
        help="Platform scope gate. Use ios_only/android_only to prevent unnecessary runs.",
    )
    parser.add_argument(
        "--on-mismatch",
        choices=["skip", "error"],
        default="skip",
        help="Behavior when command platform is outside app scope.",
    )
    parser.add_argument("--execute", action="store_true", help="Execute command (default: dry-run)")
    args = parser.parse_args()

    inferred_scope = infer_scope(
        requested_scope=args.app_scope,
        platform=args.platform,
        has_ios_id=bool(args.app_identifier),
        has_android_id=bool(args.package_name),
    )

    if scope_mismatch(inferred_scope, args.platform):
        msg = (
            f"SKIP: platform '{args.platform}' is outside app scope '{inferred_scope}'. "
            "No fastlane command generated."
        )
        if args.on_mismatch == "error":
            print("ERROR: " + msg)
            return 2
        print(msg)
        return 0

    if args.platform == "ios" and args.lane != "deliver":
        print("ERROR: iOS platform must use lane=deliver")
        return 2
    if args.platform == "android" and args.lane != "supply":
        print("ERROR: Android platform must use lane=supply")
        return 2

    if args.platform == "ios":
        if not args.app_identifier:
            print("ERROR: --app-identifier is required for iOS")
            return 2
        cmd = build_ios_deliver(args.app_identifier, args.metadata_path, args.skip_screenshots)
    else:
        if not args.package_name:
            print("ERROR: --package-name is required for Android")
            return 2
        cmd = build_android_supply(args.package_name, args.metadata_path, args.skip_images)

    rendered = " ".join(shlex.quote(c) for c in cmd)
    print(f"APP_SCOPE: {inferred_scope}")
    print(f"FASTLANE_COMMAND: {rendered}")

    if not args.execute:
        print("MODE: dry-run (command not executed)")
        return 0

    proc = subprocess.run(cmd)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
