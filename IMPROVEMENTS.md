# Schema Generation — Improvement Plan

## Overview

The current process works but requires significant manual effort each time a new
controller version is added: copy files from a previous version, update constants in
multiple places, manually invoke Docker commands. The goal of this plan is to reduce
that toil and make the generation process more reliable, without introducing CI/CD.

---

## Improvement 1 — Root Makefile

**Problem:** No single entry point to build the Docker image, generate schemas, or
validate output. Users must know which directory to `cd` into and which script to run.

**Solution:** Add a root `Makefile` with self-documenting targets.

```makefile
CONTROLLER   ?=
VERSION      ?=
IMAGE        ?= schema-builder

.PHONY: help build generate generate-kubernetes validate

help:          ## Show this help
generate:      ## Generate schemas: make generate CONTROLLER=external-secrets VERSION=v0.18.2
generate-kubernetes: ## Generate k8s schemas: make generate-kubernetes VERSION=v1.34.1
build:         ## Build the builder Docker image
validate:      ## Validate generated schemas (placeholder)
```

**Impact:** Single discoverable interface for all operations; easy onboarding for new contributors.

---

## Improvement 2 — Fix Typo in Kubernetes Generate Script

**Problem:** `json-schemas/kubernetes/generate/generage.sh` — `generage` is a typo.

**Solution:**
- Rename to `generate.sh`
- Add `generate-docker.sh` wrapper consistent with all other controllers

**Impact:** Consistency; also makes the Makefile target simpler.

---

## Improvement 3 — Centralize `boilerplate.go.txt`

**Problem:** Every controller has its own copy of `boilerplate.go.txt` in `generate/`.
All copies are identical. Changes must be applied N times.

**Solution:** Move to a single `generate/boilerplate.go.txt` at the repo root. Update
`generate.sh` scripts to reference `${REPO_ROOT}/generate/boilerplate.go.txt`.

**Impact:** Single source of truth for the license header.

---

## Improvement 4 — Shared `generate-openapi-json` Tool

**Problem:** Every controller version has its own `generate-openapi-json.go` that
contains the same ~180 lines of boilerplate (`loadVanilla`, `mergedDefinitions`,
`reverse`, `main` structure). Only `kubernetesSwaggerUrl`, `crdNames`, and
`hostConversionRules` differ between controllers.

**Solution:** Extract the shared logic into a standalone CLI tool at
`tools/generate-openapi-json/` that accepts configuration:

```
tools/
  generate-openapi-json/
    main.go       # generic tool: reads config file, produces openapi.json
    go.mod
```

Configuration file per controller version (e.g. `generate/VERSION/openapi-config.yaml`):

```yaml
kubernetesSwaggerUrl: https://raw.githubusercontent.com/.../swagger.json
hostConversionRules:
  github.com/external-secrets/external-secrets: external-secrets.io
crdNames:
  - github.com/external-secrets/external-secrets/apis/externalsecrets/v1.ExternalSecret
  - ...
```

The `generate.sh` script then calls:
```bash
go run "${REPO_ROOT}/tools/generate-openapi-json/main.go" \
  --config "${ROOT}/generate/${VERSION}/openapi-config.yaml" \
  > generated/openapi/openapi.json
```

**Impact:** Removes ~150 lines of duplicated Go per version; adding a new version only
requires a small YAML config instead of copying and editing a Go file.

---

## Improvement 5 — Version Registry (`versions.yaml`)

**Problem:** There is no machine-readable list of which controllers and versions exist.
Automation, validation, and documentation all require manual discovery.

**Solution:** Add `versions.yaml` at the repo root:

```yaml
controllers:
  external-secrets:
    repository: github.com/external-secrets/external-secrets
    versions:
      - v0.6.1
      - v0.7.2
      - v0.18.2
  cert-manager:
    repository: github.com/cert-manager/cert-manager
    versions:
      - v1.14.5
  kubernetes:
    type: builtin   # fetches swagger.json directly
    versions:
      - v1.33.2
      - v1.34.1
  # ...
```

**Impact:** Enables the Makefile to iterate over all versions; enables automated
checking for stale versions; makes the set of supported versions explicit and auditable.

---

## Improvement 6 — Schema Validation Step

**Problem:** After generation there is no automated check that the output is sane.
Silent failures (wrong patch, upstream API change) are only caught by the consumer.

**Solution:** Add a `validate` target that runs basic sanity checks:

1. **Schema count check:** `_definitions.json` must contain at least N definitions
   (configurable per controller in `versions.yaml`).
2. **JSON syntax check:** All `*.json` files in the output directory must be valid JSON.
3. **`$ref` resolution check:** All `$ref` values in individual schemas must resolve
   within `_definitions.json`.

Implementation: small Python or shell script at `tools/validate-schemas.sh`.

**Impact:** Catches partial generation failures before commit.

---

## Improvement 7 — Cleanup Debug Artifacts from `generate.sh`

**Problem:** Scripts contain commented-out debug code:
```bash
#trap 'rm -rf "${SOURCES_ROOT}"' EXIT
#echo 'sleep'
#sleep infinity
```

**Solution:**
- Remove commented-out debug code.
- Re-enable the `trap` cleanup so source directories are removed on exit (both success
  and failure), keeping the Docker container filesystem clean.

**Impact:** Cleaner scripts; prevents disk space issues in Docker builds.

---

## Improvement 8 — Pin `openapi2jsonschema` Version in Dockerfile

**Problem:** The Dockerfile installs `openapi2jsonschema` without pinning a version,
meaning the image can produce different output over time as the package is updated.

**Solution:** Pin to a specific version:
```dockerfile
/venv/bin/pip install openapi2jsonschema==0.9.1
```

**Impact:** Reproducible builds; no unexpected schema changes after a `docker build`.

---

## Improvement 9 — Update Deprecated Go API Usage

**Problem:** `generate-openapi-json.go` files use `ioutil.ReadAll` which has been
deprecated since Go 1.16 (replaced by `io.ReadAll`).

**Solution:** Update all occurrences to `io.ReadAll` when refactoring the shared tool
(see Improvement 4).

**Impact:** Eliminates deprecation warnings; aligns with current Go idioms.

---

## Implementation Order

| Priority | Improvement | Effort | Impact |
|---|---|---|---|
| 1 | Fix typo + add kubernetes docker wrapper (#2) | Low | Low |
| 2 | Centralize `boilerplate.go.txt` (#3) | Low | Low |
| 3 | Root Makefile (#1) | Medium | High |
| 4 | Version registry `versions.yaml` (#5) | Medium | Medium |
| 5 | Schema validation step (#6) | Medium | High |
| 6 | Cleanup debug code in scripts (#7) | Low | Low |
| 7 | Pin `openapi2jsonschema` in Dockerfile (#8) | Low | Medium |
| 8 | Shared `generate-openapi-json` tool (#4) | High | High |
| 9 | Update deprecated Go APIs (#9) | Low | Low |

---

## Out of Scope (for now)

- CI/CD integration (GitHub Actions, etc.)
- Automatic upstream version detection
- Schema diffing between versions
