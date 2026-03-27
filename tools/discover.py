#!/usr/bin/env python3
"""
Populate index.yaml with resources from Kubernetes API discovery.

Two modes:

  --static   (default) reads pre-dumped JSON files from a directory URL:
               {base}/api__v1.json              - core group (APIResourceList)
               {base}/apis.json                 - named group list (APIGroupList)
               {base}/apis__{group}__{ver}.json - per-group-version resources

  --live     reads directly from a running Kubernetes API server:
               {base}/api/v1
               {base}/apis
               {base}/apis/{group}/{version}

Usage (static — GitHub raw):
    python3 tools/discover.py \\
        --discovery-base-url https://raw.githubusercontent.com/kubernetes/kubernetes/v1.34.1/api/discovery \\
        --output schemas/kubernetes/kubernetes/v1.34.1/index.yaml

Usage (live — local API server):
    python3 tools/discover.py --live \\
        --discovery-base-url https://127.0.0.1:16443 \\
        --token admin --insecure \\
        --output schemas/aws/karpenter-provider-aws/v1.10.0/index.yaml
"""

import argparse
import json
import ssl
import sys
import urllib.request
from pathlib import Path

import yaml


class _NoAnchorDumper(yaml.SafeDumper):
    """SafeDumper that never emits YAML anchors/aliases."""
    def ignore_aliases(self, data):
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_opener(token=None, insecure=False):
    """Return a urllib opener with optional bearer token and TLS skip."""
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    opener = urllib.request.build_opener(*handlers)
    if token:
        opener.addheaders = [('Authorization', f'Bearer {token}')]
    return opener


def fetch_json(url, opener, save_to=None):
    try:
        with opener.open(url, timeout=30) as r:
            raw = r.read()
        data = json.loads(raw)
        if save_to:
            Path(save_to).parent.mkdir(parents=True, exist_ok=True)
            Path(save_to).write_text(json.dumps(data, indent=2))
        return data
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
# Discovery — static file mode (GitHub raw / pre-dumped files)
# ---------------------------------------------------------------------------

def discover_static(base_url, opener, dump_dir=None):
    base = base_url.rstrip('/')
    resources = []

    def save_path(filename):
        return Path(dump_dir) / filename if dump_dir else None

    data = fetch_json(f"{base}/api__v1.json", opener, save_to=save_path("api__v1.json"))
    if data:
        resources.extend(parse_resource_list(data, group=''))

    apis = fetch_json(f"{base}/apis.json", opener, save_to=save_path("apis.json"))
    if apis:
        for group_info in apis.get('groups', []):
            group = group_info['name']
            for version_info in group_info.get('versions', []):
                gv = version_info['groupVersion']
                version = gv.split('/')[-1]
                filename = f"apis__{group}__{version}.json"
                data = fetch_json(f"{base}/{filename}", opener, save_to=save_path(filename))
                if data:
                    resources.extend(parse_resource_list(data, group=group))

    resources.sort(key=lambda r: (r['group'], r['version'], r['kind']))
    return resources


# ---------------------------------------------------------------------------
# Discovery — live API server mode
# ---------------------------------------------------------------------------

def discover_live(base_url, opener, dump_dir=None, only_groups=None):
    """
    Fetch discovery from a live API server.

    only_groups: if provided, only fetch group-versions whose group is in this
                 set — /api/v1 (core group) and unrelated groups are skipped.
    """
    base = base_url.rstrip('/')
    resources = []

    def save_path(filename):
        return Path(dump_dir) / filename if dump_dir else None

    # Core group: /api/v1 — skip when filtering to specific groups
    if not only_groups:
        data = fetch_json(f"{base}/api/v1", opener, save_to=save_path("api__v1.json"))
        if data:
            resources.extend(parse_resource_list(data, group=''))

    # Named groups: /apis
    apis = fetch_json(f"{base}/apis", opener)
    if apis:
        if only_groups:
            # Save a filtered apis.json containing only the relevant groups
            filtered = dict(apis)
            filtered['groups'] = [g for g in apis.get('groups', [])
                                   if g['name'] in only_groups]
            if dump_dir:
                p = save_path("apis.json")
                Path(p).parent.mkdir(parents=True, exist_ok=True)
                Path(p).write_text(json.dumps(filtered, indent=2))
        else:
            if dump_dir:
                save_path_val = save_path("apis.json")
                Path(save_path_val).parent.mkdir(parents=True, exist_ok=True)
                Path(save_path_val).write_text(json.dumps(apis, indent=2))

        for group_info in apis.get('groups', []):
            group = group_info['name']
            if only_groups and group not in only_groups:
                continue
            for version_info in group_info.get('versions', []):
                gv = version_info['groupVersion']
                version = gv.split('/')[-1]
                filename = f"apis__{group}__{version}.json"
                data = fetch_json(f"{base}/apis/{gv}", opener, save_to=save_path(filename))
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
                        help='Base URL (GitHub raw directory or live API server)')
    parser.add_argument('--output', required=True,
                        help='Path to the version index.yaml to write')
    parser.add_argument('--dump-dir',
                        help='Directory to save raw discovery JSON files (optional)')
    parser.add_argument('--live', action='store_true',
                        help='Read from a live Kubernetes API server instead of static files')
    parser.add_argument('--token',
                        help='Bearer token for live API server authentication')
    parser.add_argument('--insecure', action='store_true',
                        help='Skip TLS certificate verification (live mode)')
    args = parser.parse_args()

    dump_dir = args.dump_dir or str(Path(args.output).parent / 'discovery')
    opener = make_opener(token=args.token, insecure=args.insecure)

    print(f"Discovering resources from {args.discovery_base_url} ...", flush=True)
    if args.live:
        resources = discover_live(args.discovery_base_url, opener, dump_dir=dump_dir)
    else:
        resources = discover_static(args.discovery_base_url, opener, dump_dir=dump_dir)
    print(f"  found {len(resources)} resources", flush=True)

    output = Path(args.output)
    existing = {}
    if output.exists():
        with open(output) as f:
            existing = yaml.safe_load(f) or {}

    existing['resources'] = resources
    output.write_text(
        yaml.dump(existing, Dumper=_NoAnchorDumper, default_flow_style=False, sort_keys=False, allow_unicode=True)
    )
    print(f"Written {output}", flush=True)


if __name__ == '__main__':
    main()
