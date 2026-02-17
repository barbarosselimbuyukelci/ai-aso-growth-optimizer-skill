#!/usr/bin/env python3
"""
Translation bridge for ASO metadata.

Supports:
- mock provider (copy source)
- command provider (invoke external translator command)
- libretranslate provider (LibreTranslate-compatible API)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List


def load_payload(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")
    if "entries" not in payload or "target_locales" not in payload:
        raise ValueError("Input JSON must include 'entries' and 'target_locales'")
    return payload


def translate_command(template: str, source_locale: str, target_locale: str, text: str, entry_id: str) -> str:
    command = template.format(
        source_locale=source_locale,
        target_locale=target_locale,
        text=text,
        id=entry_id,
    )
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"translator command failed with code {proc.returncode}")
    return proc.stdout.strip()


def translate_libre(endpoint: str, api_key: str, source_locale: str, target_locale: str, text: str) -> str:
    payload = {
        "q": text,
        "source": source_locale.split("-")[0].lower(),
        "target": target_locale.split("-")[0].lower(),
        "format": "text",
    }
    if api_key:
        payload["api_key"] = api_key

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    translated = body.get("translatedText")
    if not isinstance(translated, str) or not translated.strip():
        raise RuntimeError("libretranslate response missing translatedText")
    return translated.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="ASO translation bridge")
    parser.add_argument("--input", required=True, help="Input JSON path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--provider", choices=["mock", "command", "libretranslate"], default="mock")
    parser.add_argument("--command-template", help="Command template for provider=command")
    parser.add_argument("--libre-endpoint", default="http://localhost:5000/translate", help="LibreTranslate endpoint")
    parser.add_argument("--libre-api-key", default="", help="Optional LibreTranslate API key")
    parser.add_argument("--sleep-ms", type=int, default=0, help="Optional delay between requests")
    args = parser.parse_args()

    try:
        payload = load_payload(args.input)
    except Exception as exc:
        print(f"ERROR: failed to load input: {exc}")
        return 2

    source_locale = str(payload.get("source_locale", "en-US"))
    target_locales = payload.get("target_locales", [])
    entries = payload.get("entries", [])

    if args.provider == "command" and not args.command_template:
        print("ERROR: --command-template is required for provider=command")
        return 2

    if not isinstance(target_locales, list) or not target_locales:
        print("ERROR: target_locales must be a non-empty list")
        return 2
    if not isinstance(entries, list) or not entries:
        print("ERROR: entries must be a non-empty list")
        return 2

    output: Dict[str, Any] = {
        "source_locale": source_locale,
        "target_locales": target_locales,
        "protected_terms": payload.get("protected_terms", []),
        "entries": [],
    }

    for entry in entries:
        entry_id = str(entry.get("id", ""))
        field = str(entry.get("field", ""))
        source_text = str(entry.get("text", ""))
        if not source_text:
            continue

        translations: Dict[str, str] = {}

        for target_locale in target_locales:
            target_locale = str(target_locale)
            try:
                if args.provider == "mock":
                    translated = source_text
                elif args.provider == "command":
                    translated = translate_command(args.command_template or "", source_locale, target_locale, source_text, entry_id)
                else:
                    translated = translate_libre(args.libre_endpoint, args.libre_api_key, source_locale, target_locale, source_text)
            except Exception as exc:
                print(f"ERROR: entry={entry_id} locale={target_locale} translation failed: {exc}")
                return 1

            translations[target_locale] = translated

            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)

        output["entries"].append(
            {
                "id": entry_id,
                "field": field,
                "source_text": source_text,
                "translations": translations,
            }
        )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote translated payload: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
