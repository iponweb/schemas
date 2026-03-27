#!/usr/bin/env python3
"""
Fetch /openapi/v2 from an envtest API server with CRDs installed,
filter to controller groups only, save openapi-live.json, and run
openapi2jsonschema to produce json-schema-live/.

Usage:
    python3 tools/envtest_openapi.py \
        --crd-dir    schemas/prometheus-operator/prometheus-operator/v0.90.1/crd \
        --openapi-out schemas/prometheus-operator/prometheus-operator/v0.90.1/openapi/openapi-live.json \
        --output-dir  schemas/prometheus-operator/prometheus-operator/v0.90.1/json-schema-live

Environment:
    ENVTEST_BIN_DIR   path to directory with etcd/kube-apiserver/kubectl
                      (default: /usr/local/kubebuilder/bin)
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

TOOLS_DIR = Path(__file__).parent
DEFAULT_BIN_DIR = Path(os.environ.get('ENVTEST_BIN_DIR', '/usr/local/kubebuilder/bin'))


class _CRDLoader(yaml.SafeLoader):
    """SafeLoader that tolerates the YAML 1.1 '=' value-indicator scalar."""

_CRDLoader.add_constructor(
    'tag:yaml.org,2002:value',
    lambda loader, node: loader.construct_scalar(node),
)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait_ready(url, token, timeout=30):
    import ssl, urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    opener.addheaders = [('Authorization', f'Bearer {token}')]
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with opener.open(f'{url}/healthz', timeout=2) as r:
                if r.read() == b'ok':
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def sanitize_crds(crd_dir, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(Path(crd_dir).glob('*.yaml')):
        try:
            with open(src) as f:
                docs = list(yaml.load_all(f, Loader=_CRDLoader))
        except yaml.YAMLError:
            continue
        cleaned = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            meta = doc.get('metadata', {})
            labels = meta.get('labels', {})
            if any('{{' in str(v) for v in labels.values()):
                meta['labels'] = {k: v for k, v in labels.items() if '{{' not in str(v)}
            cleaned.append(doc)
        if cleaned:
            (dest_dir / src.name).write_text(
                yaml.dump_all(cleaned, default_flow_style=False, sort_keys=False, allow_unicode=True)
            )


def crd_groups(crd_dir):
    groups = set()
    for f in sorted(Path(crd_dir).glob('*.yaml')):
        try:
            with open(f) as fh:
                for doc in yaml.load_all(fh, Loader=_CRDLoader):
                    if isinstance(doc, dict) and doc.get('kind') == 'CustomResourceDefinition':
                        g = doc.get('spec', {}).get('group', '')
                        if g:
                            groups.add(g)
        except Exception:
            pass
    return groups


def fetch_openapi_v2(url, token):
    import ssl, urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    opener.addheaders = [('Authorization', f'Bearer {token}')]
    with opener.open(f'{url}/openapi/v2', timeout=30) as r:
        return json.loads(r.read())


def filter_openapi(spec, groups):
    """Keep only definitions whose name starts with a reversed controller group prefix."""
    group_prefixes = set()
    for g in groups:
        parts = g.split('.')
        parts.reverse()
        group_prefixes.add('.'.join(parts))

    kept = {}
    for key, val in spec.get('definitions', {}).items():
        for prefix in group_prefixes:
            if key.startswith(prefix + '.'):
                kept[key] = val
                break

    return {
        'swagger': spec.get('swagger', '2.0'),
        'info': spec.get('info', {}),
        'paths': {},
        'definitions': kept,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--crd-dir', required=True,
                        help='Directory containing individual CRD YAML files')
    parser.add_argument('--openapi-out', required=True,
                        help='Path to write the filtered openapi-live.json')
    parser.add_argument('--output-dir', required=True,
                        help='Directory to write json-schema-live/ schemas')
    parser.add_argument('--envtest-bin-dir', default=str(DEFAULT_BIN_DIR))
    args = parser.parse_args()

    bin_dir = Path(args.envtest_bin_dir)
    etcd_bin      = bin_dir / 'etcd'
    apiserver_bin = bin_dir / 'kube-apiserver'
    kubectl_bin   = bin_dir / 'kubectl'
    for b in [etcd_bin, apiserver_bin, kubectl_bin]:
        if not b.exists():
            print(f'error: {b} not found', file=sys.stderr); sys.exit(1)

    crd_dir = Path(args.crd_dir)
    groups = crd_groups(crd_dir)
    if not groups:
        print('error: no CRD groups found', file=sys.stderr); sys.exit(1)

    etcd_port = free_port()
    etcd_peer = free_port()
    api_port  = free_port()
    token     = 'envtest-admin'

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        token_file = tmpdir / 'token.csv'
        token_file.write_text(f'{token},admin,admin,system:masters\n')
        sa_key = tmpdir / 'sa.key'
        subprocess.run(['openssl', 'genrsa', '-out', str(sa_key), '2048'],
                       capture_output=True, check=True)

        etcd_proc = subprocess.Popen(
            [str(etcd_bin),
             '--data-dir', str(tmpdir / 'etcd'),
             '--listen-client-urls', f'http://127.0.0.1:{etcd_port}',
             '--advertise-client-urls', f'http://127.0.0.1:{etcd_port}',
             '--listen-peer-urls', f'http://127.0.0.1:{etcd_peer}',
             '--log-level', 'error'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        apiserver_proc = subprocess.Popen(
            [str(apiserver_bin),
             '--etcd-servers', f'http://127.0.0.1:{etcd_port}',
             '--bind-address', '127.0.0.1',
             '--secure-port', str(api_port),
             '--authorization-mode', 'AlwaysAllow',
             '--token-auth-file', str(token_file),
             '--service-account-issuer', 'https://kubernetes.default.svc',
             '--service-account-key-file', str(sa_key),
             '--service-account-signing-key-file', str(sa_key),
             '--cert-dir', str(tmpdir / 'certs'),
             '--disable-admission-plugins', 'ServiceAccount'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        api_url = f'https://127.0.0.1:{api_port}'

        try:
            print(f'  envtest-openapi: starting API server on :{api_port} ...', flush=True)
            if not wait_ready(api_url, token):
                print('error: API server not ready', file=sys.stderr); sys.exit(1)

            sanitized = tmpdir / 'sanitized'
            sanitize_crds(crd_dir, sanitized)
            result = subprocess.run(
                [str(kubectl_bin), f'--server={api_url}', '--insecure-skip-tls-verify',
                 f'--token={token}', 'create', '-f', str(sanitized)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f'error: kubectl create failed:\n{result.stderr}', file=sys.stderr)
                sys.exit(1)
            time.sleep(1)

            print(f'  envtest-openapi: fetching /openapi/v2 ...', flush=True)
            raw_spec = fetch_openapi_v2(api_url, token)
            filtered = filter_openapi(raw_spec, groups)
            print(f'  envtest-openapi: {len(filtered["definitions"])} definitions '
                  f'in groups: {sorted(groups)}', flush=True)

            # Save openapi-live.json
            openapi_out = Path(args.openapi_out)
            openapi_out.parent.mkdir(parents=True, exist_ok=True)
            openapi_out.write_text(json.dumps(filtered, indent=2))

            # Convert to JSON Schema
            output_dir = Path(args.output_dir)
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True)

            subprocess.run(
                ['openapi2jsonschema', str(openapi_out),
                 '-o', str(output_dir), '--strict', '--expanded', '--kubernetes'],
                check=True,
            )
            print(f'  envtest-openapi: {len(list(output_dir.glob("*.json")))} schemas '
                  f'written to {output_dir}', flush=True)

        finally:
            apiserver_proc.terminate()
            etcd_proc.terminate()
            apiserver_proc.wait()
            etcd_proc.wait()


if __name__ == '__main__':
    main()
