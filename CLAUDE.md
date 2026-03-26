# CLAUDE.md — Repository Guide

## Purpose

This repository generates and stores JSON Schemas for Kubernetes built-in APIs and
third-party controllers/operators. Schemas are used by
[metachart](https://github.com/iponweb/metachart) for Helm chart validation.

---

## Repository Structure

```
json-schemas/
  CONTROLLER/
    generate/
      boilerplate.go.txt         # Apache 2.0 header for openapi-gen
      VERSION/
        generate.sh              # Main generation script (run inside Docker)
        generate-docker.sh       # Docker wrapper that invokes generate.sh
        generate-openapi-json.go # Go program: merges CRD + k8s OpenAPI → JSON
        patch.diff               # Patch applied to controller source
        patch-vendor.diff        # (optional) Patch for vendored deps
        go.mod / go.sum          # Go module for generate-openapi-json.go
        generated/openapi/       # Intermediate build artifacts (.gitignored)
    VERSION-strict/
      _definitions.json          # All schema definitions
      RESOURCE-GROUP-VERSION.json # Individual resource schemas
builder/
  Dockerfile                     # Builds the schema-builder Docker image
```

**Exception — built-in Kubernetes schemas** live under `json-schemas/kubernetes/generate/`
and use a single `generage.sh` (typo in filename) that fetches `swagger.json` directly
from the Kubernetes GitHub repo — no source cloning or openapi-gen step needed.

---

## Controllers & Versions

| Controller | Versions |
|---|---|
| cert-manager | v1.14.5 |
| external-secrets | v0.6.1, v0.7.2, v0.18.2 |
| gatekeeper | v3.10.0 |
| karpenter | v0.19.1 |
| kubernetes | v1.22 – v1.34 (many patch releases) |
| kubernetes-gateway-api | v1.1.0, v1.3.0 |
| prometheus-operator | v0.60.1, v0.63.0 |
| secrets-store-csi-driver | v1.4.6 |
| victoriametrics-operator | v0.63.0 |

---

## Generation Pipeline

### For third-party controllers

```
1. git clone --depth 1 --branch VERSION https://REPOSITORY
2. git apply patch.diff          # enable +k8s:openapi-gen=true in doc.go
3. go mod vendor
4. openapi-gen → openapi_generated.go
5. go run generate-openapi-json.go → openapi.json
6. openapi2jsonschema → VERSION-strict/
```

**Run via Docker (preferred):**
```bash
# 1. Build the builder image once
docker build -t schema-builder builder/

# 2. From the controller directory (e.g., json-schemas/external-secrets)
sh generate/VERSION/generate-docker.sh
```

The `generate-docker.sh` script mounts the current directory as `/src` and runs
`generate/VERSION/generate.sh` inside the container.

### For built-in Kubernetes schemas

```bash
cd json-schemas/kubernetes/
KUBERNETES_VERSION=v1.34.1 sh generate/generage.sh
```

No Docker or source cloning needed — the script fetches
`https://raw.githubusercontent.com/kubernetes/kubernetes/VERSION/api/openapi-spec/swagger.json`
directly.

---

## Tooling (inside the Docker image)

| Tool | Source |
|---|---|
| `openapi-gen` | `k8s.io/kube-openapi/cmd/openapi-gen` (pinned commit) |
| `openapi2jsonschema` | `instrumenta/openapi2jsonschema` (Python, via venv) |
| `go` | golang:alpine base image |
| `git` | Alpine package |

---

## Output Schema Format

- **`_definitions.json`** — central definitions, referenced by individual schemas
- **`RESOURCE-GROUP-VERSION.json`** — per-resource schema, e.g.
  `externalsecret-externalsecrets-v1.json`
- All schemas use `--strict --expanded --kubernetes` flags from `openapi2jsonschema`
- `additionalProperties: false` enforced on all resources

---

## Adding a New Controller Version

1. Create `json-schemas/CONTROLLER/generate/NEW_VERSION/`
2. Copy and adapt from an existing version:
   - `generate.sh` — update `VERSION`, `REPOSITORY`, API group paths
   - `generate-docker.sh` — update `VERSION`
   - `generate-openapi-json.go` — update `kubernetesSwaggerUrl`, `crdNames`, `hostConversionRules`
   - `go.mod` / `go.sum` — update module deps to match controller version
3. Create `patch.diff` (and `patch-vendor.diff` if needed)
4. Build the Docker image if not already done: `docker build -t schema-builder builder/`
5. Run: `sh generate/NEW_VERSION/generate-docker.sh` from the controller directory
6. Commit generated schemas in `NEW_VERSION-strict/`

---

## Known Issues / Notes

- `json-schemas/kubernetes/generate/generage.sh` — typo in filename (`generage` vs `generate`)
- `generated/` directories are `.gitignored` (intermediate artifacts)
- The `generate.sh` scripts contain commented-out debug helpers (`sleep infinity`, `trap` cleanup)
- Each controller carries its own copy of `boilerplate.go.txt` (identical content)
- `generate-openapi-json.go` has significant structural duplication across controllers
- `ioutil.ReadAll` (deprecated since Go 1.16) used in some `generate-openapi-json.go` files
