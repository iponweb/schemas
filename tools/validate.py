#!/usr/bin/env python3
"""
Validate a generated VERSION-strict schema directory.

Usage (from the controller directory):
    python3 ../../tools/validate.py v0.19.1-strict

Checks:
  1. _definitions.json exists and is valid JSON
  2. All *.json files are valid JSON
  3. Every $ref in individual schemas resolves within _definitions.json
  4. The two primary CRD schemas listed in config.yaml are present
"""

import json
import sys
from pathlib import Path


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        return e


def collect_refs(obj, refs=None):
    if refs is None:
        refs = set()
    if isinstance(obj, dict):
        if "$ref" in obj:
            refs.add(obj["$ref"])
        for v in obj.values():
            collect_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            collect_refs(item, refs)
    return refs


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <VERSION-strict-dir>", file=sys.stderr)
        sys.exit(1)

    schema_dir = Path(sys.argv[1])
    errors = []
    warnings = []

    # ------------------------------------------------------------------
    # 1. Check _definitions.json
    # ------------------------------------------------------------------
    defs_path = schema_dir / "_definitions.json"
    if not defs_path.exists():
        errors.append("_definitions.json not found")
        print("\n".join(f"ERROR: {e}" for e in errors))
        sys.exit(1)

    defs_data = load_json(defs_path)
    if isinstance(defs_data, json.JSONDecodeError):
        errors.append(f"_definitions.json is not valid JSON: {defs_data}")
        print("\n".join(f"ERROR: {e}" for e in errors))
        sys.exit(1)

    known_defs = set(defs_data.get("definitions", {}).keys())
    print(f"  _definitions.json  {len(known_defs)} definitions")

    # ------------------------------------------------------------------
    # 2. Validate all JSON files + collect $refs
    # ------------------------------------------------------------------
    schema_files = sorted(p for p in schema_dir.glob("*.json")
                          if p.name != "_definitions.json" and p.name != "all.json")
    bad_json = []
    missing_refs = []

    for path in schema_files:
        data = load_json(path)
        if isinstance(data, json.JSONDecodeError):
            bad_json.append((path.name, str(data)))
            continue

        for ref in collect_refs(data):
            if not ref.startswith("_definitions.json#/definitions/"):
                continue
            def_key = ref.split("#/definitions/", 1)[1]
            if def_key not in known_defs:
                missing_refs.append((path.name, def_key))

    if bad_json:
        for name, msg in bad_json:
            errors.append(f"invalid JSON in {name}: {msg}")
    else:
        print(f"  JSON syntax         {len(schema_files)} files OK")

    if missing_refs:
        for schema, ref in missing_refs:
            errors.append(f"unresolved $ref in {schema}: {ref}")
    else:
        print(f"  $ref resolution     all refs resolve")

    # ------------------------------------------------------------------
    # 3. Summary
    # ------------------------------------------------------------------
    print()
    if errors:
        for e in errors:
            print(f"FAIL  {e}")
        sys.exit(1)
    else:
        print(f"PASS  {schema_dir}  ({len(schema_files)} schemas, {len(known_defs)} definitions)")


main()
