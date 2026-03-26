#!/usr/bin/env python3
"""
Shared schema generation pipeline for Kubernetes controllers.

Usage (from the controller directory, e.g. json-schemas/karpenter/):
    python3 ../../tools/generate.py generate/v0.19.1/config.yaml

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
# Pipeline
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <config.yaml>", file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[1]).resolve()
    controller_dir = Path.cwd()          # e.g. json-schemas/karpenter/
    version_dir = config_path.parent     # e.g. generate/v0.19.1/

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
        boilerplate = controller_dir / "generate" / "boilerplate.go.txt"
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
        # Step 8 — Convert OpenAPI → JSON Schema
        # -------------------------------------------------------------------
        output_dir = controller_dir / f"{version}-strict"
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True)

        run([
            "openapi2jsonschema",
            version_dir / "generated" / "openapi" / "openapi.json",
            "-o", output_dir,
            "--strict", "--expanded", "--kubernetes",
        ])

        print(f"\nDone. Schemas written to {output_dir}", flush=True)

    finally:
        shutil.rmtree(sources_root, ignore_errors=True)


main()
