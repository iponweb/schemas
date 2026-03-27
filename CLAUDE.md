# CLAUDE.md — Repository Guide

## Purpose

This repository generates and stores JSON Schemas for Kubernetes built-in APIs and
third-party controllers/operators. Schemas are used by
[metachart](https://github.com/iponweb/metachart) for Helm chart validation.

---

## Repository Structure

```
config/
  boilerplate.go.txt             # Shared Apache 2.0 header for openapi-gen
  ORG/REPO/VERSION/
    config.yaml                  # All generation parameters
    patch.diff                   # (optional) Patch applied to controller source
    patch-vendor.diff            # (optional) Patch applied after go mod vendor
    generated/                   # Intermediate build artifacts (.gitignored)

schemas/
  ORG/REPO/
    index.yaml                   # Controller metadata (name, repository URL)
    VERSION/
      index.yaml                 # Version data: resource list with GVK
      json-schema/
        _definitions.json        # All schema definitions
        KIND.GROUP.VERSION.json  # Individual resource schemas

tools/
  generate.py                    # Shared generation pipeline script
  validate.py                    # Schema validation script
  openapi-json-gen/
    main.go.tmpl                 # Go source template for the OpenAPI builder
builder/
  Dockerfile                     # Builds the schema-builder Docker image
Makefile
```

**ORG/REPO** mirrors the GitHub repository path (e.g. `aws/karpenter-provider-aws`).
This is unambiguous even when multiple vendors implement the same API group.

**Exception — built-in Kubernetes schemas** have no `config/kubernetes/kubernetes/` entry.
`make generate-kubernetes VERSION=v1.34.1` fetches `swagger.json` directly from the
Kubernetes GitHub repo and writes to `schemas/kubernetes/kubernetes/VERSION/json-schema/`.

---

## Generation Pipeline (Shared — `tools/generate.py`)

Karpenter (and ideally all future controllers) use the shared pipeline.

```
1. git clone --depth 1 --branch VERSION https://REPOSITORY
2. git apply patch.diff          # (optional) add +k8s:openapi-gen=true markers etc.
3. go mod vendor
4. git apply patch-vendor.diff   # (optional) patch vendor/ after download
5. openapi-gen → generated/openapi/openapi_generated.go
6. write generated/go.mod + render generated/main.go from main.go.tmpl
7. go mod tidy && go run ./main.go → generated/openapi/openapi.json
8. openapi2jsonschema → schemas/ORG/REPO/VERSION/json-schema/
```

**Run via Docker (preferred):**
```bash
make builder                                                              # build image once
make generate CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
```

**Run locally (no Docker):**
```bash
make generate-local CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
```

**Validate output:**
```bash
make validate CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
```

### For built-in Kubernetes schemas

```bash
make generate-kubernetes VERSION=v1.34.1
```

---

## config.yaml — Complete Reference

Every field and its role:

```yaml
# Version tag to check out from the repository (passed to git clone --branch).
version: "v1.10.0"

# Go module path of the repository to clone (no https:// prefix).
repository: "github.com/aws/karpenter-provider-aws"

# Packages passed to openapi-gen for Go type analysis.
# Rules:
#   - Include the controller's own CRD API packages (all served versions).
#   - Include any dependency packages whose types appear directly in the CRD
#     specs AND that do not have +k8s:openapi-gen=true in their own doc.go
#     (those need a patch-vendor.diff instead, see below).
#   - With kube-openapi >= ~2024-08 you must also explicitly list k8s stdlib
#     packages that older versions provided automatically:
#       k8s.io/api/core/v1               (NodeSelectorRequirement, Taint, etc.)
#       k8s.io/apimachinery/pkg/api/resource  (Quantity)
#   - Always include:
#       k8s.io/apimachinery/pkg/apis/meta/v1
#       k8s.io/apimachinery/pkg/runtime
#       k8s.io/apimachinery/pkg/version
openapi_gen_packages:
  - "github.com/aws/karpenter-provider-aws/pkg/apis/v1"
  - "sigs.k8s.io/karpenter/pkg/apis/v1"
  - "sigs.k8s.io/karpenter/pkg/apis/v1alpha1"
  - "k8s.io/api/core/v1"
  - "k8s.io/apimachinery/pkg/api/resource"
  - "k8s.io/apimachinery/pkg/apis/meta/v1"
  - "k8s.io/apimachinery/pkg/runtime"
  - "k8s.io/apimachinery/pkg/version"

# Go module dependencies pinned in the auto-generated generated/go.mod.
# These are NOT the controller's own go.mod — they are for the small
# generated/main.go program that builds the merged OpenAPI spec.
# Always pin these three; use versions matching the controller's go.mod:
#   k8s.io/apimachinery  — matches the controller
#   k8s.io/apiserver     — must match apimachinery (provides DefinitionNamer)
#   k8s.io/kube-openapi  — matches the controller
# Mismatched versions break resource.Quantity handling or schema building.
go_dependencies:
  k8s.io/apimachinery: "v0.35.3"
  k8s.io/apiserver: "v0.35.3"
  k8s.io/kube-openapi: "v0.0.0-20251125145642-4e65d59e963e"

# URL of the vanilla Kubernetes swagger.json used as a fallback for k8s built-in
# types not covered by openapi-gen. Use the same minor version as
# k8s.io/apimachinery (minor 35 → v1.35.x). If that exact patch hasn't been
# released yet, use the latest available patch of that minor.
kubernetes_swagger_url: "https://raw.githubusercontent.com/kubernetes/kubernetes/v1.34.1/api/openapi-spec/swagger.json"

# Optional. Base URL of a Kubernetes api/discovery directory.
# When set, tools/discover.py is run after schema generation to populate
# schemas/ORG/REPO/VERSION/index.yaml with the full resource list (kind, group,
# version, plural, scope, shortNames).
#
# Format follows the Kubernetes api/discovery convention:
#   {base}/api__v1.json              - core group resources
#   {base}/apis.json                 - named group enumeration
#   {base}/apis__{group}__{ver}.json - per-group resources
#
# Available for Kubernetes >= 1.28. Omit for older versions or non-Kubernetes
# controllers (CRD-based discovery is handled separately).
discovery_base_url: "https://raw.githubusercontent.com/kubernetes/kubernetes/v1.34.1/api/discovery"

# Human-readable title embedded in the generated OpenAPI spec.
title: "karpenter CRD OpenAPI"

# Full Go type paths of the root CRD kinds to build schemas for.
# Format: "MODULE_PATH/PKG.TypeName"
# Include every served API version of every CRD.
# Dependencies are resolved automatically — no need to list sub-types.
crd_names:
  - "github.com/aws/karpenter-provider-aws/pkg/apis/v1.EC2NodeClass"
  - "sigs.k8s.io/karpenter/pkg/apis/v1.NodePool"
  - "sigs.k8s.io/karpenter/pkg/apis/v1.NodeClaim"
  - "sigs.k8s.io/karpenter/pkg/apis/v1alpha1.NodeOverlay"

# Maps Go module prefixes to their Kubernetes API group hostnames.
# Used by GetDefinitionName to produce OpenAPI definition keys like
# "sh.karpenter.v1.NodePool" instead of "io.sigs.k8s.karpenter.pkg.apis.v1.NodePool".
# Rules:
#   - Keys are Go module path PREFIXES (not full paths).
#   - The matching uses HasPrefix(name, key+"/") — the trailing "/" prevents
#     "github.com/aws/karpenter" from matching "github.com/aws/karpenter-provider-aws".
#   - Only one rule fires per type (break after first match).
#   - Derive the value from the controller's CRD group annotation (groupName).
host_conversion_rules:
  "github.com/aws/karpenter-provider-aws": "karpenter.k8s.aws"
  "sigs.k8s.io/karpenter": "karpenter.sh"

# Maps Go type paths that cannot be processed by openapi-gen to the key of an
# equivalent type that IS present in the generated definitions map.
# Use this when a dependency package contains a type that causes openapi-gen to
# fail (e.g. a generic type with a non-string map key), making it impossible to
# include that package in openapi_gen_packages.
#
# Key format:   Go type path  ("github.com/foo/bar.Type")
# Value format: the actual map key used in the definitions map — which depends
#               on the kube-openapi version:
#
#   kube-openapi < ~2024-11:  Go type path  ("k8s.io/apimachinery/.../meta/v1.Condition")
#   kube-openapi >= ~2024-11: OpenAPIModelName() result ("io.k8s.apimachinery.pkg.apis.meta.v1.Condition")
#
# To find the correct value: check whether the target type implements
# OpenAPIModelName() in the vendored source. If it does, the value is that
# method's return string. Otherwise use the Go type path.
type_aliases:
  "github.com/awslabs/operatorpkg/status.Condition": "io.k8s.apimachinery.pkg.apis.meta.v1.Condition"
```

---

## Patch Files

Two optional patch files sit alongside `config.yaml`. Both are applied with
`git apply` inside the cloned repository.

### patch.diff — source patches (before `go mod vendor`)

Apply to the cloned controller source. Typical uses:

- Adding `// +k8s:openapi-gen=true` to a `doc.go` that lacks it.
- Adding a missing `doc.go` to a package that needs to be scanned.

This file is **optional** — `generate.py` skips it if absent.

**Optimal workflow to create it:**

```bash
# 1. Clone the controller at the target version
git clone --depth 1 --branch vX.Y.Z https://github.com/ORG/REPO /tmp/src
cd /tmp/src

# 2. Make your edits (e.g. add +k8s:openapi-gen=true to doc.go)
#    Use Python for reliable edits:
python3 -c "
content = open('pkg/apis/v1alpha5/doc.go').read()
open('pkg/apis/v1alpha5/doc.go', 'w').write(
    '// +k8s:openapi-gen=true\n' + content
)
"

# 3. Stage the original files first, THEN make the change, so git diff works:
git add pkg/apis/v1alpha5/doc.go
# ... make the actual edit ...
git diff > config/ORG/REPO/vX.Y.Z/patch.diff

# OR: stage originals and commit, then make edits, then git diff HEAD
git add -A && git commit -m "orig"
# ... edit ...
git diff HEAD > config/ORG/REPO/vX.Y.Z/patch.diff
```

### patch-vendor.diff — vendor patches (after `go mod vendor`)

Applied after `go mod vendor` downloads dependencies into `vendor/`. Typical uses:

- Adding `// +k8s:openapi-gen=true` to a vendored dependency's `doc.go`
  (e.g. `knative.dev/pkg/apis`).
- Adding `// +k8s:openapi-gen=false` to exclude a problematic type in a
  vendored package (though note: `+k8s:openapi-gen=false` does **not** work
  on generic types in current openapi-gen — use `type_aliases` instead).

This file is **optional** — `generate.py` skips it if absent.

**Optimal workflow to create it:**

```bash
# 1. Clone the controller at the target version and vendor
git clone --depth 1 --branch vX.Y.Z https://github.com/ORG/REPO /tmp/src
cd /tmp/src
go mod vendor

# 2. Stage the files you will modify
git add vendor/some/dep/doc.go

# 3. Apply edits using Python to avoid whitespace issues
python3 -c "
content = open('vendor/some/dep/doc.go').read()
open('vendor/some/dep/doc.go', 'w').write(
    content.replace(
        '// +k8s:deepcopy-gen=package\n',
        '// +k8s:deepcopy-gen=package\n// +k8s:openapi-gen=true\n'
    )
)
"

# 4. Capture the diff
git diff vendor/some/dep/doc.go > config/ORG/REPO/vX.Y.Z/patch-vendor.diff
```

**Important:** always verify the patch applies cleanly before committing:

```bash
git stash
git apply --check config/ORG/REPO/vX.Y.Z/patch-vendor.diff && echo "OK"
```

Never write patch files by hand — the blank-line context rule in unified diffs
(each context line needs a leading space, blank context lines need a trailing
space) is easy to get wrong and `git apply` will reject corrupt patches.

---

## openapi-gen API Versions

`generate.py` auto-detects which flag style to use based on `openapi-gen --help`:

| Era | Detection | Key flags |
|---|---|---|
| pre-2023 | `--input-dirs` present in help | `-h`, `--input-dirs`, `--output-base`, `GO111MODULE=off` |
| post-2023 | `--input-dirs` absent in help | `--go-header-file`, positional packages, `--output-dir`, `cwd=sources_root` |

Always run openapi-gen with `cwd=sources_root` (the cloned repo) in post-2023 mode so it
resolves dependencies from `vendor/`.

`openapi-gen` must be installed at a version matching the controller's
`k8s.io/kube-openapi` dependency. Mismatches cause `package "..." without types`
errors. Reinstall with:

```bash
go install k8s.io/kube-openapi/cmd/openapi-gen@COMMIT_OR_VERSION
```

---

## Known Issues & Pitfalls

### host_conversion_rules prefix collision

`github.com/aws/karpenter` is a prefix of `github.com/aws/karpenter-provider-aws`.
Using `strings.HasPrefix(name, rule)` without a trailing `/` causes the wrong rule
to fire. The template uses `strings.HasPrefix(name, key+"/")` and breaks after the
first match to avoid this.

### +k8s:openapi-gen=false on generic types

The `// +k8s:openapi-gen=false` marker does **not** suppress generation for generic
types like `Controller[T Object]` in current openapi-gen versions. If a vendored
package contains a generic type with an OpenAPI-incompatible field (e.g.
`map[reconcile.Request]ConditionSet` — non-string map key), you cannot include
that package in `openapi_gen_packages`. Use `type_aliases` instead to provide the
needed type's schema from an equivalent processable type.

### type_aliases key format changed in kube-openapi ~2024-11

In kube-openapi >= ~2024-11, types that implement `OpenAPIModelName()` use their
model name as the definitions map key instead of the Go type path. The value in
`type_aliases` must match the actual key:

- **Old** (kube-openapi ≤ 2024-08): `"k8s.io/apimachinery/pkg/apis/meta/v1.Condition"`
- **New** (kube-openapi ≥ 2024-11): `"io.k8s.apimachinery.pkg.apis.meta.v1.Condition"`

Check by running: `go run -mod=mod -e - <<'EOF'`
```go
package main
import (fmt; metav1 "k8s.io/apimachinery/pkg/apis/meta/v1")
func main() { fmt.Println(metav1.Condition{}.OpenAPIModelName()) }
EOF
```

### resource.Quantity missing in newer kube-openapi

kube-openapi removed the built-in special-case handler for `resource.Quantity` around
2024. Add `k8s.io/apimachinery/pkg/api/resource` to `openapi_gen_packages` explicitly.

### k8s core types missing in newer kube-openapi

Similarly, `k8s.io/api/core/v1` types (NodeSelectorRequirement, Taint, etc.) are no
longer provided automatically by the vanilla swagger fallback in newer builds. Add
`k8s.io/api/core/v1` to `openapi_gen_packages`.

### Go toolchain version

If the controller's `go.mod` specifies a `toolchain` newer than the locally installed
Go, `go mod vendor` will download it automatically. However `openapi-gen` (a pre-compiled
binary) may fail with `package "..." without types` if it was built with a different Go
version. Fix: upgrade Go to match the controller's requirement, then reinstall `openapi-gen`.

### Go workspace mode (go.work)

Some repositories (e.g. `sigs.k8s.io/gateway-api` v1.5+) use Go workspace mode
(`go.work` at the repo root). `go mod vendor` fails in workspace mode with:

> `go mod vendor cannot be run in workspace mode`

`generate.py` automatically sets `GOWORK=off` when running `go mod vendor` to work
around this. No config change is needed.

### generated/ is gitignored

The `**/generated/*` pattern in `.gitignore` covers intermediate build artifacts.
Do not commit anything under `generated/`.

---

## Tooling

| Tool | Purpose | Install |
|---|---|---|
| `openapi-gen` | Generates Go OpenAPI definitions from annotated types | `go install k8s.io/kube-openapi/cmd/openapi-gen@VERSION` |
| `openapi2jsonschema` | Converts OpenAPI spec to JSON Schema files | Python venv (`instrumenta/openapi2jsonschema`) |
| `go` | Compiles and runs the OpenAPI builder | brew / golang.org |
| `git` | Clones controller source | system |
