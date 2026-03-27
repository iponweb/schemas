#!/usr/bin/env python3
"""
Start a temporary kube-apiserver, install CRDs, and dump live discovery.

Uses envtest binaries (etcd + kube-apiserver + kubectl) installed by
setup-envtest. The API server is torn down after discovery completes.

Only resources belonging to groups defined in the CRDs are written to
index.yaml — built-in Kubernetes groups are filtered out.

Usage:
    python3 tools/envtest.py \
        --crd-dir schemas/aws/karpenter-provider-aws/v1.10.0/crd \
        --output  schemas/aws/karpenter-provider-aws/v1.10.0/index.yaml

Environment:
    ENVTEST_BIN_DIR   path to directory with etcd/kube-apiserver/kubectl
                      (default: /usr/local/kubebuilder/bin)
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml


class _NoAnchorDumper(yaml.SafeDumper):
    """SafeDumper that never emits YAML anchors/aliases."""
    def ignore_aliases(self, data):
        return True

TOOLS_DIR = Path(__file__).parent
DEFAULT_BIN_DIR = Path(os.environ.get('ENVTEST_BIN_DIR', '/usr/local/kubebuilder/bin'))


class _CRDLoader(yaml.SafeLoader):
    """SafeLoader that tolerates the YAML 1.1 '=' value-indicator scalar."""

_CRDLoader.add_constructor(
    'tag:yaml.org,2002:value',
    lambda loader, node: loader.construct_scalar(node),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait_ready(url, token, timeout=30):
    """Poll /healthz until the API server responds ok."""
    import ssl
    import urllib.request

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
    """
    Copy CRD files to dest_dir with Helm template strings removed from labels.
    Labels containing '{{' are invalid for kubectl and must be stripped.
    Annotations are preserved as-is (required annotations like
    api-approved.kubernetes.io must not be removed).
    """
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
                meta['labels'] = {k: v for k, v in labels.items()
                                  if '{{' not in str(v)}
            cleaned.append(doc)
        if cleaned:
            dest = dest_dir / src.name
            dest.write_text(
                yaml.dump_all(cleaned, Dumper=_NoAnchorDumper, default_flow_style=False,
                              sort_keys=False, allow_unicode=True)
            )


def crd_groups(crd_dir):
    """Return the set of API groups defined by CRDs in crd_dir."""
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--crd-dir', required=True,
                        help='Directory containing CRD YAML files to install')
    parser.add_argument('--output', required=True,
                        help='Path to the version index.yaml to write')
    parser.add_argument('--dump-dir',
                        help='Directory to save raw discovery JSON files (optional)')
    parser.add_argument('--envtest-bin-dir', default=str(DEFAULT_BIN_DIR),
                        help='Directory containing etcd/kube-apiserver/kubectl')
    args = parser.parse_args()

    bin_dir = Path(args.envtest_bin_dir)
    etcd_bin       = bin_dir / 'etcd'
    apiserver_bin  = bin_dir / 'kube-apiserver'
    kubectl_bin    = bin_dir / 'kubectl'

    for b in [etcd_bin, apiserver_bin, kubectl_bin]:
        if not b.exists():
            print(f'error: {b} not found — run: setup-envtest use --bin-dir {bin_dir}',
                  file=sys.stderr)
            sys.exit(1)

    crd_dir = Path(args.crd_dir)
    if not crd_dir.exists() or not list(crd_dir.glob('*.yaml')):
        print(f'error: no CRD YAML files found in {crd_dir}', file=sys.stderr)
        sys.exit(1)

    groups = crd_groups(crd_dir)
    if not groups:
        print(f'error: no CustomResourceDefinition documents found in {crd_dir}',
              file=sys.stderr)
        sys.exit(1)

    etcd_port = free_port()
    etcd_peer = free_port()
    api_port  = free_port()
    token     = 'envtest-admin'

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        token_file = tmpdir / 'token.csv'
        token_file.write_text(f'{token},admin,admin,system:masters\n')
        sa_key = tmpdir / 'sa.key'

        # Generate service account signing key
        subprocess.run(
            ['openssl', 'genrsa', '-out', str(sa_key), '2048'],
            capture_output=True, check=True,
        )

        # Start etcd
        etcd_proc = subprocess.Popen(
            [str(etcd_bin),
             '--data-dir',            str(tmpdir / 'etcd'),
             '--listen-client-urls',  f'http://127.0.0.1:{etcd_port}',
             '--advertise-client-urls', f'http://127.0.0.1:{etcd_port}',
             '--listen-peer-urls',    f'http://127.0.0.1:{etcd_peer}',
             '--log-level', 'error'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        # Start kube-apiserver
        apiserver_proc = subprocess.Popen(
            [str(apiserver_bin),
             '--etcd-servers',                   f'http://127.0.0.1:{etcd_port}',
             '--bind-address',                   '127.0.0.1',
             '--secure-port',                    str(api_port),
             '--authorization-mode',             'AlwaysAllow',
             '--token-auth-file',                str(token_file),
             '--service-account-issuer',         'https://kubernetes.default.svc',
             '--service-account-key-file',       str(sa_key),
             '--service-account-signing-key-file', str(sa_key),
             '--cert-dir',                       str(tmpdir / 'certs'),
             '--disable-admission-plugins',      'ServiceAccount'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        api_url = f'https://127.0.0.1:{api_port}'

        try:
            print(f'  envtest: starting API server on :{api_port} ...', flush=True)
            if not wait_ready(api_url, token):
                print('  error: API server did not become ready', file=sys.stderr)
                sys.exit(1)

            # Apply sanitized CRDs (annotations/labels stripped to avoid
            # Helm template strings and oversized annotation payloads)
            sanitized_dir = Path(tmpdir) / 'sanitized-crds'
            sanitize_crds(crd_dir, sanitized_dir)
            result = subprocess.run(
                [str(kubectl_bin),
                 f'--server={api_url}',
                 '--insecure-skip-tls-verify',
                 f'--token={token}',
                 'create', '-f', str(sanitized_dir)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f'  error: kubectl apply failed:\n{result.stderr}', file=sys.stderr)
                sys.exit(1)
            n_crd_files = len(list(sanitized_dir.glob("*.yaml")))
            print(f'  envtest: CRDs installed ({n_crd_files} files)', flush=True)

            # Live discovery — reuse discover.py logic
            sys.path.insert(0, str(TOOLS_DIR))
            from discover import discover_live, make_opener

            opener   = make_opener(token=token, insecure=True)
            dump_dir = args.dump_dir or str(Path(args.output).parent / 'discovery')

            # Retry discovery until the resource count stabilises — the API
            # server may need a moment to register all CRDs after kubectl create.
            prev_count = -1
            resources  = []
            for attempt in range(20):
                time.sleep(1)
                dump_path = Path(dump_dir)
                if dump_path.exists():
                    shutil.rmtree(dump_path)
                resources = discover_live(api_url, opener, dump_dir=dump_dir,
                                          only_groups=groups)
                if len(resources) == prev_count:
                    break  # stable
                prev_count = len(resources)

            print(f'  envtest: {len(resources)} resources in groups: {sorted(groups)}',
                  flush=True)

            output = Path(args.output)
            existing = {}
            if output.exists():
                with open(output) as f:
                    existing = yaml.safe_load(f) or {}
            existing['resources'] = resources
            output.write_text(
                yaml.dump(existing, Dumper=_NoAnchorDumper, default_flow_style=False,
                          sort_keys=False, allow_unicode=True)
            )

        finally:
            apiserver_proc.terminate()
            etcd_proc.terminate()
            apiserver_proc.wait()
            etcd_proc.wait()


if __name__ == '__main__':
    main()
