#!/usr/bin/env python3
"""
Populate index.yaml with resources from Kubernetes API discovery files.

Discovery files follow the Kubernetes api/discovery directory convention:

  {base}/api__v1.json              - core group (APIResourceList)
  {base}/apis.json                 - named group list (APIGroupList)
  {base}/apis__{group}__{ver}.json - per-group-version resources (APIResourceList)

Can be used standalone or called by generate.py when discovery_base_url is set
in config.yaml.

Usage:
    python3 tools/discover.py \\
        --discovery-base-url https://raw.githubusercontent.com/kubernetes/kubernetes/v1.34.1/api/discovery \\
        --output schemas/kubernetes/kubernetes/v1.34.1/index.yaml
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_json(url, save_to=None):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            raw = r.read()
        if save_to:
            Path(save_to).parent.mkdir(parents=True, exist_ok=True)
            Path(save_to).write_bytes(raw)
        return json.loads(raw)
    except Exception as e:
        print(f"  warning: could not fetch {url}: {e}", file=sys.stderr)
        return None


def parse_resource_list(data, group):
    """Parse an APIResourceList into resource dicts, skipping subresources."""
    group_version = data.get('groupVersion', '')
    version = group_version.split('/')[-1] if '/' in group_version else group_version

    resources = []
    for r in data.get('resources', []):
        if '/' in r.get('name', ''):   # subresource — skip
            continue
        entry = {
            'kind':    r['kind'],
            'group':   group,
            'version': version,
            'plural':  r['name'],
            'scope':   'Namespaced' if r.get('namespaced') else 'Cluster',
        }
        if r.get('shortNames'):
            entry['shortNames'] = r['shortNames']
        resources.append(entry)
    return resources


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover(base_url, dump_dir=None):
    """
    Fetch all APIResourceList files from a Kubernetes api/discovery directory.
    Returns a sorted list of resource dicts.
    If dump_dir is set, raw JSON files are saved there.
    """
    base = base_url.rstrip('/')
    resources = []

    def save_path(filename):
        return Path(dump_dir) / filename if dump_dir else None

    # Core group
    data = fetch_json(f"{base}/api__v1.json", save_to=save_path("api__v1.json"))
    if data:
        resources.extend(parse_resource_list(data, group=''))

    # Named groups via apis.json
    apis = fetch_json(f"{base}/apis.json", save_to=save_path("apis.json"))
    if apis:
        for group_info in apis.get('groups', []):
            group = group_info['name']
            for version_info in group_info.get('versions', []):
                gv = version_info['groupVersion']        # e.g. "apps/v1"
                version = gv.split('/')[-1]
                filename = f"apis__{group}__{version}.json"
                data = fetch_json(f"{base}/{filename}", save_to=save_path(filename))
                if data:
                    resources.extend(parse_resource_list(data, group=group))

    resources.sort(key=lambda r: (r['group'], r['version'], r['kind']))
    return resources


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--discovery-base-url', required=True,
                        help='Base URL of a kubernetes api/discovery directory')
    parser.add_argument('--output', required=True,
                        help='Path to the version index.yaml to write')
    parser.add_argument('--dump-dir',
                        help='Directory to save raw discovery JSON files (optional)')
    args = parser.parse_args()

    dump_dir = args.dump_dir or str(Path(args.output).parent / 'discovery')

    print(f"Discovering resources from {args.discovery_base_url} ...", flush=True)
    resources = discover(args.discovery_base_url, dump_dir=dump_dir)
    print(f"  found {len(resources)} resources", flush=True)

    output = Path(args.output)
    existing = {}
    if output.exists():
        with open(output) as f:
            existing = yaml.safe_load(f) or {}

    existing['resources'] = resources
    output.write_text(
        yaml.dump(existing, default_flow_style=False, sort_keys=False, allow_unicode=True)
    )
    print(f"Written {output}", flush=True)


if __name__ == '__main__':
    main()
