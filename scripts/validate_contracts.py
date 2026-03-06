#!/usr/bin/env python3
"""Lightweight endpoint contract validator for local E2E checks."""
from __future__ import annotations

import argparse
import json
import random
import string
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a lightweight endpoint contract JSON file.")
    parser.add_argument("--contract", required=True, help="Path to contract JSON")
    parser.add_argument("--base-url", required=True, help="Target base URL")
    parser.add_argument("--workspace-id", default="", help="Workspace ID for $workspace_id substitutions")
    parser.add_argument("--workspace-slug", default="default", help="Workspace slug for $workspace_slug substitutions")
    parser.add_argument("--header", action="append", default=[], help="Extra header key=value")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    return parser.parse_args()


def _random_token(length: int = 6) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def _substitute_value(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str):
        out = value
        for key, repl in ctx.items():
            out = out.replace(f"${key}", str(repl))
        return out
    if isinstance(value, list):
        return [_substitute_value(item, ctx) for item in value]
    if isinstance(value, dict):
        return {k: _substitute_value(v, ctx) for k, v in value.items()}
    return value


def _json_lookup(payload: Any, path: str) -> Any:
    if path == "":
        return payload
    current: Any = payload
    for raw_part in path.split("."):
        part = raw_part.strip()
        if part == "":
            continue
        if isinstance(current, list):
            index = int(part)
            current = current[index]
            continue
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(part)
            current = current[part]
            continue
        raise KeyError(part)
    return current


def _request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout_seconds: int,
) -> tuple[int, Any, str]:
    body = None
    request_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, method=method, headers=request_headers, data=body)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return int(resp.status), parsed, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return int(exc.code), parsed, raw
    except Exception as exc:
        return 0, {}, str(exc)


def main() -> int:
    args = parse_args()
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    base_url = args.base_url.rstrip("/")
    endpoints = contract.get("endpoints") if isinstance(contract.get("endpoints"), list) else []
    if not endpoints:
        print(f"FAIL {args.contract}: no endpoints declared")
        return 1

    context: dict[str, Any] = {
        "workspace_id": args.workspace_id,
        "workspace_slug": args.workspace_slug,
        "rand": _random_token(),
    }
    headers = {}
    default_headers = contract.get("default_headers") if isinstance(contract.get("default_headers"), dict) else {}
    for key, value in default_headers.items():
        headers[str(key)] = str(_substitute_value(value, context))
    for item in args.header:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        headers[key.strip()] = value.strip()

    failures = 0
    for endpoint in endpoints:
        name = str(endpoint.get("name") or "unnamed")
        method = str(endpoint.get("method") or "GET").upper()
        path = str(_substitute_value(endpoint.get("path") or "/", context))
        url = f"{base_url}{path}"
        req_payload = endpoint.get("request_json")
        payload = _substitute_value(req_payload, context) if isinstance(req_payload, dict) else None
        expected = endpoint.get("success_status") if isinstance(endpoint.get("success_status"), list) else [200]
        expected_codes = {int(item) for item in expected}

        code, parsed, raw = _request_json(
            method=method,
            url=url,
            headers=headers,
            payload=payload,
            timeout_seconds=args.timeout_seconds,
        )
        ok = code in expected_codes
        missing: list[str] = []
        required_fields = endpoint.get("required_response_fields") if isinstance(endpoint.get("required_response_fields"), list) else []
        if ok and required_fields:
            for field in required_fields:
                try:
                    _json_lookup(parsed, str(field))
                except Exception:
                    missing.append(str(field))
            ok = not missing

        extracts = endpoint.get("extract") if isinstance(endpoint.get("extract"), dict) else {}
        if ok and extracts:
            for key, source_path in extracts.items():
                try:
                    value = _json_lookup(parsed, str(source_path))
                    context[str(key)] = value
                except Exception:
                    ok = False
                    missing.append(f"extract:{key}<-{source_path}")

        if ok:
            print(f"PASS {name} [{method} {path}] -> {code}")
        else:
            failures += 1
            suffix = f" missing={','.join(missing)}" if missing else ""
            print(f"FAIL {name} [{method} {path}] -> {code}{suffix}")
            snippet = raw[:280].replace("\n", " ")
            print(f"  response: {snippet}")

    if failures:
        print(f"RESULT FAIL ({failures}/{len(endpoints)} failed)")
        return 1
    print(f"RESULT PASS ({len(endpoints)} endpoints)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
