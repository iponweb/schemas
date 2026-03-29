#!/usr/bin/env python3
"""
Validate a generated JSON Schema directory.

Usage:
    python3 tools/validate.py schemas/ORG/REPO/VERSION/json-schema/source

Checks:
  1. _definitions.json exists and is valid JSON
  2. All *.json files are valid JSON
  3. Every $ref in individual schemas resolves within _definitions.json
  4. index.yaml integrity: every resource has a definitionKey that exists in
     _definitions.json.
  4. GVK annotation: each resource's definition carries the correct
     x-kubernetes-group-version-kind entry (skipped when the definition key
     belongs to a different API version than the resource).
  5. Cross-schema consistency (when json-schema/live/ is present): for every
     resource in index.yaml, the definitionKey in source and the key carrying
     the same GVK in live must be identical.
"""

import json
import re
import sys
from pathlib import Path

_VERSION_RE = re.compile(r'^v\d+(?:alpha\d+|beta\d+)?$')


def _version_from_def_key(dk: str):
    """Return the version segment embedded in a definition key, e.g. 'v1beta1'
    from 'io.external-secrets.v1beta1.ExternalSecret', or None."""
    parts = dk.split('.')
    if len(parts) >= 2 and _VERSION_RE.fullmatch(parts[-2]):
        return parts[-2]
    return None


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
        if "$ref" in obj and isinstance(obj["$ref"], str):
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
    # 3. index.yaml integrity: definitionKey refs
    # ------------------------------------------------------------------
    # index.yaml lives two levels above json-schema/source/
    index_yaml = schema_dir.parent.parent / "index.yaml"
    if index_yaml.exists():
        try:
            import yaml
            with open(index_yaml) as f:
                idx = yaml.safe_load(f) or {}
        except Exception as exc:
            errors.append(f"index.yaml could not be read: {exc}")
            idx = {}

        resources = idx.get("resources", [])
        missing_keys = []
        broken_refs  = []

        for r in resources:
            kind    = r.get("kind", "")
            group   = r.get("group", "")
            version = r.get("version", "")
            dk      = r.get("definitionKey", "")
            label   = f"{group}/{version}/{kind}"

            if not dk:
                missing_keys.append(label)
                continue

            if dk not in known_defs:
                broken_refs.append(f"{label} → '{dk}'")

        index_ok = not (missing_keys or broken_refs)
        if index_ok:
            print(f"  index.yaml          {len(resources)} resources OK")
        else:
            for label in missing_keys:
                errors.append(f"index.yaml: missing definitionKey for {label}")
            for msg in broken_refs:
                errors.append(f"index.yaml: definitionKey not in _definitions.json: {msg}")
    else:
        warnings.append("index.yaml not found — skipping definitionKey checks")
        print(f"  index.yaml          (not found, skipped)")

    # ------------------------------------------------------------------
    # 4. GVK annotation: each resource's definition must carry the correct
    #    x-kubernetes-group-version-kind entry.
    #    Skipped when the definition key belongs to a different API version
    #    (the resource is served from a shared definition — e.g. a v1beta1
    #    resource whose only Go type is v1).
    # ------------------------------------------------------------------
    if index_yaml.exists() and resources:
        missing_gvk  = []
        gvk_mismatch = []

        for r in resources:
            kind    = r.get("kind", "")
            group   = r.get("group", "")
            version = r.get("version", "")
            dk      = r.get("definitionKey", "")
            label   = f"{group}/{version}/{kind}"

            if not dk or dk not in known_defs:
                continue  # already caught in check 3

            dk_ver = _version_from_def_key(dk)
            if dk_ver and dk_ver != version:
                continue  # definition belongs to a different version — skip

            gvk_list = defs_data["definitions"][dk].get(
                "x-kubernetes-group-version-kind", []
            )
            expected = {"group": group, "kind": kind, "version": version}
            if not gvk_list:
                missing_gvk.append(f"{label} (def '{dk}')")
            elif expected not in gvk_list:
                gvk_mismatch.append(f"{label} (def '{dk}'): got {gvk_list}")

        gvk_ok = not (missing_gvk or gvk_mismatch)
        if gvk_ok:
            checked = sum(
                1 for r in resources
                if r.get("definitionKey") in known_defs
                and _version_from_def_key(r["definitionKey"]) in (None, r.get("version", ""))
            )
            print(f"  GVK annotations     {checked} definitions OK")
        else:
            for msg in missing_gvk:
                errors.append(f"index.yaml: definition missing x-kubernetes-group-version-kind: {msg}")
            for msg in gvk_mismatch:
                errors.append(f"index.yaml: x-kubernetes-group-version-kind mismatch: {msg}")

    # ------------------------------------------------------------------
    # 5. Cross-schema consistency: source definitionKey == live definitionKey
    # ------------------------------------------------------------------
    live_defs_path = schema_dir.parent / "live" / "_definitions.json"
    if live_defs_path.exists() and index_yaml.exists() and resources:
        live_data = load_json(live_defs_path)
        if isinstance(live_data, json.JSONDecodeError):
            warnings.append(f"live/_definitions.json is not valid JSON — skipping cross-schema check")
        else:
            # Build GVK → definition key index for live definitions
            live_gvk_index = {}
            for dk, defn in live_data.get("definitions", {}).items():
                for gvk in defn.get("x-kubernetes-group-version-kind", []):
                    t = (gvk.get("group", ""), gvk.get("kind", ""), gvk.get("version", ""))
                    live_gvk_index[t] = dk

            cross_mismatches = []
            cross_missing = []
            for r in resources:
                kind    = r.get("kind", "")
                group   = r.get("group", "")
                version = r.get("version", "")
                src_dk  = r.get("definitionKey", "")
                if not src_dk:
                    continue  # already caught in check 4
                gvk_key = (group, kind, version)
                live_dk = live_gvk_index.get(gvk_key)
                if live_dk is None:
                    cross_missing.append(f"{group}/{version}/{kind}: definitionKey='{src_dk}' has no matching GVK in live/_definitions.json")
                elif live_dk != src_dk:
                    cross_mismatches.append(
                        f"{group}/{version}/{kind}: source='{src_dk}' live='{live_dk}'"
                    )

            if cross_mismatches or cross_missing:
                for msg in cross_missing:
                    warnings.append(f"cross-schema: GVK not found in live: {msg}")
                for msg in cross_mismatches:
                    errors.append(f"cross-schema definitionKey mismatch: {msg}")
            else:
                checked = sum(1 for r in resources if r.get("definitionKey"))
                print(f"  cross-schema        {checked} resources match source↔live")
    else:
        print(f"  cross-schema        (live/ not present, skipped)")

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print()
    if errors:
        for e in errors:
            print(f"FAIL  {e}")
        sys.exit(1)
    else:
        print(f"PASS  {schema_dir}  ({len(schema_files)} schemas, {len(known_defs)} definitions)")


main()
