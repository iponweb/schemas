#!/usr/bin/env python3
"""
Download controller icons and store them at schemas/ORG/REPO/icon.{svg,png}.

Usage:
    python3 tools/download_icons.py
"""
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# CNCF artwork base (official project logos)
CNCF = "https://raw.githubusercontent.com/cncf/artwork/main/projects"

ICONS: dict[str, list[str]] = {
    "kubernetes/kubernetes": [
        f"{CNCF}/kubernetes/icon/color/kubernetes-icon-color.svg",
        "https://raw.githubusercontent.com/kubernetes/kubernetes/master/logo/logo.svg",
    ],
    "kubernetes-sigs/gateway-api": [
        "https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/main/site-src/images/logo/logo.svg",
        f"{CNCF}/kubernetes/icon/color/kubernetes-icon-color.svg",
    ],
    "kubernetes-sigs/secrets-store-csi-driver": [
        f"{CNCF}/kubernetes/icon/color/kubernetes-icon-color.svg",
    ],
    "argoproj/argo-cd": [
        "https://raw.githubusercontent.com/argoproj/argo-cd/master/docs/assets/logo.png",
        f"{CNCF}/argo/icon/color/argo-icon-color.svg",
    ],
    "prometheus-operator/prometheus-operator": [
        f"{CNCF}/prometheus/icon/color/prometheus-icon-color.svg",
        "https://raw.githubusercontent.com/prometheus/prometheus/main/documentation/images/prometheus-logo.svg",
    ],
    "cert-manager/cert-manager": [
        "https://raw.githubusercontent.com/cert-manager/website/master/static/images/cert-manager-logo-icon.svg",
        "https://cert-manager.io/images/cert-manager-logo-icon.svg",
    ],
    "external-secrets/external-secrets": [
        "https://raw.githubusercontent.com/external-secrets/external-secrets/main/assets/eso-logo-large.png",
        "https://raw.githubusercontent.com/external-secrets/external-secrets/main/docs/pictures/external-secrets-operator-logo.png",
    ],
    "open-policy-agent/gatekeeper": [
        f"{CNCF}/open-policy-agent/icon/color/open-policy-agent-icon-color.svg",
        "https://raw.githubusercontent.com/open-policy-agent/opa/main/logo/logo.svg",
        "https://raw.githubusercontent.com/cncf/artwork/main/projects/open-policy-agent/icon/color/open-policy-agent-icon-color.svg",
    ],
    "VictoriaMetrics/operator": [
        "https://raw.githubusercontent.com/VictoriaMetrics/VictoriaMetrics/master/docs/logo.png",
        "https://avatars.githubusercontent.com/u/43720803?s=200",
    ],
    "cloudpilot-ai/karpenter-provider-gcp": [
        "https://raw.githubusercontent.com/cloudpilot-ai/karpenter-provider-gcp/main/logo/logo.png",
        "https://avatars.githubusercontent.com/u/119816745?s=200",  # cloudpilot-ai org avatar
    ],
    "aws/karpenter-provider-aws": [
        "https://raw.githubusercontent.com/aws/karpenter-provider-aws/main/website/static/banner.png",
        "https://avatars.githubusercontent.com/u/9950313?s=200",  # AWS org avatar
    ],
    "aws/karpenter": [
        "https://raw.githubusercontent.com/aws/karpenter/main/website/static/banner.png",
        "https://avatars.githubusercontent.com/u/9950313?s=200",
    ],
}


def download(url: str) -> tuple[bytes, str] | None:
    """Fetch URL, return (content, extension) or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "schemas-icon-downloader/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "svg" in ct or url.endswith(".svg"):
                return content, "svg"
            elif "png" in ct or url.endswith(".png"):
                return content, "png"
            return content, "bin"
    except Exception as e:
        return None


def main() -> None:
    ok = []
    failed = []

    for slug, urls in ICONS.items():
        out_dir = REPO_ROOT / "schemas" / slug
        if not out_dir.exists():
            print(f"  SKIP  {slug} (no schemas directory)")
            continue

        # Remove existing icons before downloading
        for old in out_dir.glob("icon.*"):
            old.unlink()

        downloaded = False
        for url in urls:
            result = download(url)
            if result:
                content, ext = result
                if ext == "bin":
                    print(f"  SKIP  {slug} — unknown content type from {url}")
                    continue
                out_path = out_dir / f"icon.{ext}"
                out_path.write_bytes(content)
                size = len(content)
                print(f"  OK    {slug} → icon.{ext} ({size:,} bytes)  {url}")
                ok.append(slug)
                downloaded = True
                break
            else:
                print(f"  MISS  {slug} — {url}")

        if not downloaded:
            failed.append(slug)

    print()
    print(f"Downloaded: {len(ok)}  Failed/skipped: {len(failed)}")
    if failed:
        print("No icon found for:", ", ".join(failed))


if __name__ == "__main__":
    main()
