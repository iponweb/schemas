#!/usr/bin/env python3
"""
Parallel schema generation runner.

Discovers all config.yaml files under a given root directory and runs
tools/generate.py for each one concurrently — either locally or via Docker.

Usage:
    python3 tools/run.py [--threads N] [--docker [IMAGE]] <config-root>

Examples:
    # All controllers, all versions — local, physical CPU count threads (default)
    python3 tools/run.py config

    # All versions of one controller — Docker
    python3 tools/run.py --docker config/aws/karpenter-provider-aws

    # Custom thread count + explicit image name
    python3 tools/run.py --threads 4 --docker schema-builder config
"""

import argparse
import os
import platform
import re
import secrets
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

TOOLS_DIR     = Path(__file__).parent
REPO_ROOT     = TOOLS_DIR.parent
LOGS_DIR      = REPO_ROOT / "logs"
DEFAULT_IMAGE = "schema-builder"


def physical_cpu_count() -> int:
    """Return the number of physical (non-hyperthreaded) CPU cores."""
    try:
        if platform.system() == "Darwin":
            return int(subprocess.check_output(
                ["sysctl", "-n", "hw.physicalcpu"], stderr=subprocess.DEVNULL
            ).strip())
        if platform.system() == "Linux":
            cores: set[tuple[str, str]] = set()
            phys = core = None
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("physical id"):
                        phys = line.split(":")[1].strip()
                    elif line.startswith("core id"):
                        core = line.split(":")[1].strip()
                    elif not line.strip() and phys is not None and core is not None:
                        cores.add((phys, core))
                        phys = core = None
            if cores:
                return len(cores)
    except Exception:
        pass
    return os.cpu_count() or 1


def find_configs(root: Path) -> list[Path]:
    return sorted(root.rglob("config.yaml"))


def build_cmd(config: Path, docker_image: str | None) -> list[str]:
    """Return the command list to run generate.py for one config."""
    config_abs = config.resolve()
    config_rel = config_abs.relative_to(REPO_ROOT)
    if docker_image:
        rel_parent = config_abs.parent.relative_to(REPO_ROOT / "config")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(rel_parent)).strip("-")
        name = f"{slug}-{secrets.token_hex(2)}"
        return [
            "docker", "run", "--rm",
            "--name", name,
            "-v", f"{REPO_ROOT}:/repo",
            "-w", "/repo",
            docker_image,
            "python3", "tools/generate.py", str(config_rel),
        ]
    return [sys.executable, str(TOOLS_DIR / "generate.py"), str(config_abs)]


def run_one(config: Path, docker_image: str | None) -> tuple[Path, int, Path]:
    """Run generate.py for one config. Returns (config, returncode, log_path)."""
    config = config.resolve()
    rel = config.relative_to(REPO_ROOT / "config")
    log_name = str(rel.parent).replace("/", "-") + ".log"
    log_path = LOGS_DIR / log_name

    LOGS_DIR.mkdir(exist_ok=True)

    result = subprocess.run(
        build_cmd(config, docker_image),
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_path.write_text(result.stdout)
    return config, result.returncode, log_path


def main():
    parser = argparse.ArgumentParser(description="Run schema generation in parallel.")
    parser.add_argument("root", help="Config root dir (e.g. config or config/aws/karpenter-provider-aws)")
    default_threads = physical_cpu_count()
    parser.add_argument("--threads", "-j", type=int, default=default_threads,
                        help=f"Parallel workers (default: physical CPU count = {default_threads})")
    parser.add_argument("--docker", nargs="?", const=DEFAULT_IMAGE, default=None,
                        metavar="IMAGE",
                        help=f"Run via Docker (default image: {DEFAULT_IMAGE})")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"ERROR: {root} does not exist", file=sys.stderr)
        sys.exit(1)

    configs = find_configs(root)
    if not configs:
        print(f"No config.yaml files found under {root}", file=sys.stderr)
        sys.exit(1)

    total   = len(configs)
    threads = min(args.threads, total)
    mode    = f"Docker ({args.docker})" if args.docker else "local"
    print(f"Running {total} generation(s) with {threads} thread(s) [{mode}].", flush=True)
    print(f"Logs → {LOGS_DIR}/\n", flush=True)

    start     = time.monotonic()
    ok_list   = []
    fail_list = []

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(run_one, c, args.docker): c for c in configs}
        done = 0
        for fut in as_completed(futures):
            config, rc, log_path = fut.result()
            done += 1
            rel    = config.parent.relative_to(REPO_ROOT / "config")
            label  = str(rel)
            status = "OK  " if rc == 0 else "FAIL"
            print(f"  [{done:>2}/{total}] {status}  {label}  → {log_path.name}", flush=True)
            if rc == 0:
                ok_list.append(label)
            else:
                fail_list.append((label, log_path))

    elapsed = time.monotonic() - start
    print(f"\n{'─'*60}", flush=True)
    print(f"Finished in {elapsed:.0f}s — {len(ok_list)} OK, {len(fail_list)} FAILED.", flush=True)

    if fail_list:
        print("\nFailed jobs:", flush=True)
        for label, log_path in fail_list:
            print(f"  {label}  (log: {log_path})", flush=True)
        # Print last 30 lines of each failing log
        for label, log_path in fail_list:
            print(f"\n{'─'*40} {label}", flush=True)
            lines = log_path.read_text().splitlines()
            for line in lines[-30:]:
                print(f"  {line}", flush=True)
        sys.exit(1)


main()
