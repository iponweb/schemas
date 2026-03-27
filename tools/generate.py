#!/usr/bin/env python3
"""
Shared schema generation pipeline for Kubernetes controllers.

Usage (from the repo root):
    python3 tools/generate.py config/aws/karpenter-provider-aws/v1.10.0/config.yaml

Output is written to schemas/ORG/REPO/VERSION/json-schema/ derived from the config path.
All pipeline parameters are read from config.yaml.
"""

import os
import shutil
import subprocess
import sys
import yaml
from pathlib import Path
from string import Template


TOOLS_DIR = Path(__file__).parent
REPO_ROOT = TOOLS_DIR.parent
TEMPLATE_FILE = TOOLS_DIR / "openapi-json-gen" / "main.go.tmpl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd, *, cwd=None, extra_env=None):
    """Run a command, raise on non-zero exit."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    print(f"+ {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None,
                   env=env, check=True)


def openapi_gen_uses_new_api():
    """Return True if the installed openapi-gen uses the post-2023 flag API."""
    result = subprocess.run(["openapi-gen", "--help"],
                            capture_output=True, text=True)
    help_text = result.stdout + result.stderr
    return "--input-dirs" not in help_text


def run_capture(cmd, *, cwd=None, output_file):
    """Run a command, writing stdout to output_file."""
    env = os.environ.copy()
    print(f"+ {' '.join(str(c) for c in cmd)} > {output_file}", flush=True)
    with open(output_file, "w") as out:
        subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None,
                       env=env, stdout=out, check=True)


def render_main_go(cfg):
    """Render generated/main.go from the shared template and config values."""
    with open(TEMPLATE_FILE) as f:
        tmpl = Template(f.read())

    crd_names = "\n".join(f'\t\t"{n}",' for n in cfg["crd_names"])
    host_rules = "\n".join(
        f'\t\t"{k}": "{v}",'
        for k, v in cfg.get("host_conversion_rules", {}).items()
    )
    aliases = "\n".join(
        f'\t\t"{k}": "{v}",'
        for k, v in cfg.get("type_aliases", {}).items()
    )

    return tmpl.substitute(
        kubernetes_swagger_url=cfg["kubernetes_swagger_url"],
        title=cfg.get("title", "CRD OpenAPI"),
        crd_names=crd_names,
        host_conversion_rules=host_rules,
        type_aliases=aliases,
    )


# ---------------------------------------------------------------------------
# CRD collection
# ---------------------------------------------------------------------------

class _CRDLoader(yaml.SafeLoader):
    """SafeLoader that tolerates the YAML 1.1 '=' value-indicator scalar."""

_CRDLoader.add_constructor(
    'tag:yaml.org,2002:value',
    lambda loader, node: loader.construct_scalar(node),
)


def collect_crds(sources_root: Path, crd_path: str, crd_dir: Path, index_yaml: Path):
    """
    Recursively find CRD YAML files under sources_root/crd_path, copy them to
    crd_dir, and populate index_yaml with the resource list.
    Each served version of a CRD becomes a separate resource entry.
    """
    search_root = sources_root / crd_path
    if not search_root.exists():
        print(f"  warning: crd_path {search_root} does not exist — skipping CRD collection",
              file=sys.stderr)
        return

    crd_dir.mkdir(parents=True, exist_ok=True)

    resources = []
    copied = 0

    yaml_files = sorted(search_root.rglob("*.yaml")) + sorted(search_root.rglob("*.yml"))
    for yaml_file in yaml_files:
        try:
            with open(yaml_file) as f:
                docs = list(yaml.load_all(f, Loader=_CRDLoader))
        except yaml.YAMLError as e:
            print(f"  warning: skipping {yaml_file.name} — YAML parse error: {e}", file=sys.stderr)
            continue
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if doc.get('kind') != 'CustomResourceDefinition':
                continue
            name = doc.get('metadata', {}).get('name', '')
            if not name:
                continue

            # Write the individual CRD document (not the whole source file,
            # which may be a multi-document YAML containing all CRDs).
            dest = crd_dir / f"{name}.yaml"
            dest.write_text(
                yaml.dump(doc, default_flow_style=False, sort_keys=False,
                          allow_unicode=True)
            )
            copied += 1

            spec = doc.get('spec', {})
            group = spec.get('group', '')
            names = spec.get('names', {})
            kind = names.get('kind', '')
            plural = names.get('plural', '')
            scope = spec.get('scope', 'Namespaced')
            short_names = names.get('shortNames', [])

            # One entry per served version
            for ver_info in spec.get('versions', []):
                if not ver_info.get('served', True):
                    continue
                entry = {
                    'kind': kind,
                    'group': group,
                    'version': ver_info['name'],
                    'plural': plural,
                    'scope': scope,
                }
                if short_names:
                    entry['shortNames'] = short_names
                resources.append(entry)

    # Deduplicate by (group, version, kind) — some repos have multiple CRD
    # overlay files containing the same CRDs (e.g. with/without descriptions).
    seen = set()
    unique_resources = []
    for r in resources:
        key = (r['group'], r['version'], r['kind'])
        if key not in seen:
            seen.add(key)
            unique_resources.append(r)
    resources = unique_resources

    resources.sort(key=lambda r: (r['group'], r['version'], r['kind']))

    existing = {}
    if index_yaml.exists():
        with open(index_yaml) as f:
            existing = yaml.safe_load(f) or {}
    existing['resources'] = resources
    index_yaml.write_text(
        yaml.dump(existing, default_flow_style=False, sort_keys=False, allow_unicode=True)
    )
    print(f"  CRDs: copied {copied} files, {len(resources)} resource entries → {index_yaml}",
          flush=True)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <config.yaml>", file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[1]).resolve()
    version_dir = config_path.parent     # e.g. config/aws/karpenter-provider-aws/v1.10.0/

    # Derive output path: config/ORG/REPO/VERSION/ → schemas/ORG/REPO/VERSION/json-schema/
    rel = config_path.parent.relative_to(REPO_ROOT / "config")
    output_dir = REPO_ROOT / "schemas" / rel / "json-schema"

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    version    = cfg["version"]
    repository = cfg["repository"]

    gopath      = Path(os.environ.get("GOPATH", "/go"))
    sources_root = gopath / "src" / repository

    # Determine the installed Go version so we can pin GOTOOLCHAIN to it,
    # preventing "go.mod requires go >= X" errors when a controller's go.mod
    # specifies a minimum version newer than the image's toolchain.
    go_version_str = subprocess.check_output(["go", "version"]).decode().split()[2]  # e.g. "go1.25.1"
    go_env = {"GOWORK": "off", "GOTOOLCHAIN": go_version_str}

    # -----------------------------------------------------------------------
    # Step 1 — Clone
    # -----------------------------------------------------------------------
    shutil.rmtree(sources_root, ignore_errors=True)
    sources_root.mkdir(parents=True)

    try:
        run(["git", "clone", "--depth", "1", "--branch", version,
             f"https://{repository}", sources_root])

        # -------------------------------------------------------------------
        # Step 2 — Apply source patch (optional)
        # -------------------------------------------------------------------
        patch = version_dir / "patch.diff"
        if patch.exists():
            run(["git", "apply", patch], cwd=sources_root)

        # -------------------------------------------------------------------
        # Step 3 — Download dependencies
        # -------------------------------------------------------------------
        run(["go", "mod", "vendor"], cwd=sources_root, extra_env=go_env)

        # -------------------------------------------------------------------
        # Step 4 — Apply vendor patch (optional)
        # -------------------------------------------------------------------
        vendor_patch = version_dir / "patch-vendor.diff"
        if vendor_patch.exists():
            run(["git", "apply", vendor_patch], cwd=sources_root)

        # -------------------------------------------------------------------
        # Step 5 — Generate OpenAPI Go code (openapi-gen)
        # -------------------------------------------------------------------
        boilerplate = REPO_ROOT / "config" / "boilerplate.go.txt"
        generated_dir = version_dir / "generated" / "openapi"
        generated_dir.mkdir(parents=True, exist_ok=True)

        # Expand any comma-separated package entries into individual items
        packages = []
        for entry in cfg.get("openapi_gen_packages", []):
            packages.extend(p.strip() for p in entry.split(","))

        if openapi_gen_uses_new_api():
            # post-2023 API: positional package args, --output-dir is the full path.
            # Run from sources_root so Go modules resolve deps from vendor/.
            openapi_gen_cmd = [
                "openapi-gen", "-v", "4",
                "--go-header-file", boilerplate,
                "--output-pkg", "openapi-json-gen/openapi",
                "--output-file", "openapi_generated.go",
                "--output-dir", generated_dir,
            ] + packages
            run(openapi_gen_cmd, cwd=sources_root)
        else:
            # pre-2023 API: --input-dirs flags, GO111MODULE=off + GOPATH lookup.
            openapi_gen_cmd = [
                "openapi-gen", "-v", "4",
                "-h", boilerplate,
                "--output-package", "generated/openapi",
                "--output-file-base", "openapi_generated",
                "--output-base", version_dir,
            ]
            for pkg in packages:
                openapi_gen_cmd += ["--input-dirs", pkg]
            run(openapi_gen_cmd, extra_env={"GO111MODULE": "off"})

        # -------------------------------------------------------------------
        # Step 6 — Write go.mod + render main.go into generated/
        #           (both are gitignored — no committed go.mod needed)
        # -------------------------------------------------------------------
        go_ver = subprocess.check_output(["go", "version"]).decode().split()[2][2:]
        deps = cfg.get("go_dependencies", {})
        go_mod_lines = [f"module openapi-json-gen", f"", f"go {go_ver}"]
        if deps:
            go_mod_lines += ["", "require ("]
            go_mod_lines += [f"\t{pkg} {ver}" for pkg, ver in deps.items()]
            go_mod_lines += [")"]
        go_mod = generated_dir.parent / "go.mod"
        go_mod.write_text("\n".join(go_mod_lines) + "\n")

        main_go = generated_dir.parent / "main.go"
        main_go.write_text(render_main_go(cfg))

        # -------------------------------------------------------------------
        # Step 7 — Compile and run: produce openapi.json
        # -------------------------------------------------------------------
        run(["go", "mod", "tidy"], cwd=generated_dir.parent)
        run_capture(
            ["go", "run", "./main.go"],
            cwd=generated_dir.parent,
            output_file=generated_dir / "openapi.json",
        )

        # -------------------------------------------------------------------
        # Step 8 — Persist openapi.json
        # -------------------------------------------------------------------
        openapi_src = generated_dir / "openapi.json"
        openapi_out = REPO_ROOT / "schemas" / rel / "openapi" / "openapi.json"
        openapi_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(openapi_src, openapi_out)

        # -------------------------------------------------------------------
        # Step 9 — Convert OpenAPI → JSON Schema
        # -------------------------------------------------------------------
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True)

        run([
            "openapi2jsonschema",
            openapi_src,
            "-o", output_dir,
            "--strict", "--expanded", "--kubernetes",
        ])

        # -------------------------------------------------------------------
        # Step 10 — Populate index.yaml from discovery (optional)
        # -------------------------------------------------------------------
        discovery_base_url = cfg.get('discovery_base_url')
        if discovery_base_url:
            index_yaml = REPO_ROOT / "schemas" / rel / "index.yaml"
            run([
                "python3", TOOLS_DIR / "discover.py",
                "--discovery-base-url", discovery_base_url,
                "--output", index_yaml,
            ])

        # -------------------------------------------------------------------
        # Step 11 — Collect CRDs (optional)
        # -------------------------------------------------------------------
        crd_path_cfg = cfg.get('crd_path')
        if crd_path_cfg:
            crd_dir = REPO_ROOT / "schemas" / rel / "crd"
            index_yaml = REPO_ROOT / "schemas" / rel / "index.yaml"
            collect_crds(sources_root, crd_path_cfg, crd_dir, index_yaml)

        # -------------------------------------------------------------------
        # Step 12 — Live CRD discovery via envtest (optional)
        #           Runs when crd_path is set and envtest binaries are present.
        #           Overwrites the index.yaml resource list with authoritative
        #           data from a real API server instead of static CRD parsing.
        # -------------------------------------------------------------------
        envtest_bin_dir = Path(os.environ.get("ENVTEST_BIN_DIR", "/usr/local/kubebuilder/bin"))
        if crd_path_cfg and (envtest_bin_dir / "kube-apiserver").exists():
            crd_dir   = REPO_ROOT / "schemas" / rel / "crd"
            index_yaml = REPO_ROOT / "schemas" / rel / "index.yaml"
            run([
                "python3", TOOLS_DIR / "envtest.py",
                "--crd-dir", crd_dir,
                "--output",  index_yaml,
                "--envtest-bin-dir", envtest_bin_dir,
            ])

        print(f"\nDone. Schemas written to {output_dir}", flush=True)
        print(f"      OpenAPI written to  {openapi_out}", flush=True)

    finally:
        shutil.rmtree(sources_root, ignore_errors=True)


main()
