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
      crds.yaml                  # All CRDs as a single multi-document YAML (for Terraform)
      crd/                       # Individual CRD YAML files (one per CRD name)
      discovery/                 # Raw API discovery JSON files
        apis.json                # Filtered APIGroupList (controller groups only)
        apis__GROUP__VERSION.json
      json-schema/
        source/
          _definitions.json      # All schema definitions (source-generated)
          KIND.GROUP.VERSION.json
        live/
          _definitions.json      # All schema definitions (live kube-apiserver)
          KIND.GROUP.VERSION.json
      openapi/
        source.json              # Merged OpenAPI spec from source (intermediate)
        live.json                # Filtered OpenAPI spec from live /openapi/v2

tools/
  generate.py                    # Shared generation pipeline script (single controller/version)
  run.py                         # Parallel runner: discovers configs, runs generate.py N-way
  discover.py                    # Populates index.yaml from API discovery
  envtest.py                     # Live CRD discovery via envtest kube-apiserver
  envtest_openapi.py             # Fetches /openapi/v2 from envtest, produces json-schema/live/
  validate.py                    # Schema validation script
  openapi-json-gen/
    main.go.tmpl                 # Go source template for the OpenAPI builder
builder/
  Dockerfile                     # Builds the schema-builder Docker image
logs/                            # Per-job logs written by run.py (.gitignored)
site/                            # Astro static site (see §Site below)
Makefile
```

**ORG/REPO** mirrors the GitHub repository path (e.g. `aws/karpenter-provider-aws`).
This is unambiguous even when multiple vendors implement the same API group.

**Exception — built-in Kubernetes schemas** have no `config/kubernetes/kubernetes/` entry.
`make generate-kubernetes VERSION=v1.34.1` fetches `swagger.json` directly from the
Kubernetes GitHub repo and writes to `schemas/kubernetes/kubernetes/VERSION/json-schema/source/`.

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
 8. openapi2jsonschema → schemas/ORG/REPO/VERSION/json-schema/source/
 9. tools/discover.py (static)   # (optional) populate index.yaml from discovery_base_url
10. collect_crds                  # (optional) copy CRD YAMLs to crd/, write crds.yaml, populate index.yaml
11. tools/envtest.py              # (optional) start kube-apiserver, install CRDs, populate index.yaml
                                  #            via live discovery — overwrites step 10's resource list
                                  #            with authoritative data; runs when crd_path is set and
                                  #            $ENVTEST_BIN_DIR/kube-apiserver is present
12. tools/envtest_openapi.py      # (optional, requires step 11) fetch /openapi/v2 from the same
                                  #            API server, filter to controller groups, save
                                  #            openapi/live.json and generate json-schema/live/
13. compare_schemas               # (optional, requires steps 8+12) compare root CRD definition
                                  #            names between json-schema/source/ and json-schema/live/;
                                  #            reports mismatches that indicate wrong host_conversion_rules
```

Steps 10–13 are mutually exclusive with step 9: controllers that use `crd_path` rely on
envtest for discovery; controllers that use `discovery_base_url` fetch static files from GitHub.

**Single controller — Docker (preferred):**
```bash
make builder                                                              # build image once
make generate CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
```

**Single controller — local (no Docker):**
```bash
make generate-local CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
```

**All controllers, all versions — 8 parallel Docker containers:**
```bash
make generate-all                          # 8 threads (default)
make generate-all THREADS=4               # custom thread count
```

**All versions of one controller — parallel Docker:**
```bash
make generate-all-versions CONTROLLER=aws/karpenter-provider-aws
make generate-all-versions CONTROLLER=cert-manager/cert-manager THREADS=2
```

Per-job logs are written to `logs/ORG-REPO-VERSION.log`. Failed jobs print their
last 30 log lines to stdout and `run.py` exits non-zero.

Each Docker container is named `ORG-REPO-VERSION-<4-char-hex>` so `docker ps` shows
what is currently running.

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

# GitHub repository path to clone (no https:// prefix).
# For Go modules with a major-version suffix (e.g. github.com/argoproj/argo-cd/v3),
# use the bare GitHub repo path here (github.com/argoproj/argo-cd) — the /v3 suffix
# is part of the Go module path but not the actual repository URL.
# The full module path (with suffix) belongs only in openapi_gen_packages / crd_names.
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

# Path (relative to the cloned repository root) where CRD YAML files live.
# When set, generate.py:
#   - Copies individual CRD documents to schemas/ORG/REPO/VERSION/crd/
#     (one file per CRD, named <plural>.<group>.yaml).
#   - Populates index.yaml with one entry per served CRD version.
#   - If $ENVTEST_BIN_DIR/kube-apiserver is present (inside Docker), also runs
#     tools/envtest.py to overwrite index.yaml with live discovery data.
#
# Mutually exclusive with discovery_base_url — use one or the other.
#
# Common values:
#   "config/crd/bases"           external-secrets, secrets-store-csi-driver
#   "config/crd/overlay"         VictoriaMetrics (multi-doc overlay files)
#   "config/crd/standard"        gateway-api
#   "charts/CHART/crds"          gatekeeper, cert-manager
#   "pkg/apis/crds"              karpenter
#   "example/prometheus-operator-crd"  prometheus-operator
crd_path: "pkg/apis/crds"

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
#
# Matching rules (applied longest-key-first):
#   1. Sub-package match: HasPrefix(name, key+"/")
#      Fires when a type lives in a sub-package of key.
#      After replacement, the Go path is stripped to keep only {version}.{Kind}.
#      Example key: "github.com/aws/karpenter-provider-aws"
#      Matches:     "github.com/aws/karpenter-provider-aws/pkg/apis/v1.EC2NodeClass"
#
#   2. Exact package match: HasPrefix(name, key+".")
#      Fires when a type lives in the exact package named by key.
#      The version is extracted from the last path segment of key.
#      Use this when a sub-package has a DIFFERENT API group than the module root.
#      Example key: "github.com/cert-manager/cert-manager/pkg/apis/acme"
#      Matches:     "github.com/cert-manager/cert-manager/pkg/apis/acme/v1.Challenge"
#      Result:      "io.cert-manager.acme.v1.Challenge"
#
# Only one rule fires per type (break after first match). Sort longer (more
# specific) keys first so sub-package rules win over module-level fallbacks.
# This is done automatically inside main.go.tmpl.
#
# Multi-group controllers: when a controller's CRDs span multiple Kubernetes API
# groups (e.g. "cert-manager.io" and "acme.cert-manager.io", or
# "external-secrets.io" and "generators.external-secrets.io"), add a more-specific
# key for each non-default group before the module-level fallback:
#
#   "github.com/cert-manager/cert-manager/pkg/apis/acme": "acme.cert-manager.io"
#   "github.com/cert-manager/cert-manager": "cert-manager.io"
#
#   "github.com/external-secrets/external-secrets/apis/generators": "generators.external-secrets.io"
#   "github.com/external-secrets/external-secrets": "external-secrets.io"
#
# For controllers whose module path doesn't match their CRD group at all
# (e.g. gateway-api: module "sigs.k8s.io/gateway-api", group "gateway.networking.k8s.io"),
# a single rule suffices:
#   "sigs.k8s.io/gateway-api": "gateway.networking.k8s.io"
#
# Derive the group value from the controller's CRD group annotation (groupName
# in doc.go or +groupName marker).
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

### type_aliases value format depends on the openapi-gen version that generated the code

The `type_aliases` value must match the key that the generated `GetOpenAPIDefinitions`
function uses for the alias target. This key format is determined by the version of
**openapi-gen** (and its bundled kube-openapi) that produced the `openapi_generated.go`
— NOT by the `k8s.io/kube-openapi` version in `go_dependencies`.

- **Old openapi-gen** (kube-openapi ≤ 2024-08): keys are Go type paths.
  Use `"k8s.io/apimachinery/pkg/apis/meta/v1.Condition"` as the alias value.
- **New openapi-gen** (kube-openapi ≥ 2024-11): types that implement `OpenAPIModelName()`
  use their model name as the key.
  Use `"io.k8s.apimachinery.pkg.apis.meta.v1.Condition"` as the alias value.

To determine which format a specific controller uses, check the generated
`config/ORG/REPO/VERSION/generated/openapi/openapi_generated.go` for the key
`metav1.Condition` uses in the returned map:
```
grep '"k8s.io/apimachinery/pkg/apis/meta/v1.Condition"\|"io.k8s.apimachinery' \
  config/ORG/REPO/VERSION/generated/openapi/openapi_generated.go | head -1
```

If the key starts with `"k8s.io/..."` → use the old format.
If the key starts with `"io.k8s...."` → use the new format.

The `k8s.io/kube-openapi` version in `go_dependencies` does **not** need to match the
controller's go.mod. Using a newer version (e.g. `v0.0.0-20251125145642-4e65d59e963e`)
is safe as long as the generated code is compatible, which it generally is.

Symptoms of wrong format: generation fails with:
> `cannot build openapi definitions: cannot find model definition for github.com/awslabs/operatorpkg/status.Condition`

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

### YAML 1.1 `=` value-indicator scalar in CRD files

Some CRDs (e.g. prometheus-operator's `alertmanagerconfigs`) contain `=` as a plain
YAML scalar. Python's `yaml.SafeLoader` rejects it with:

> `could not determine a constructor for the tag 'tag:yaml.org,2002:value'`

Both `generate.py` (`collect_crds`) and `tools/envtest.py` (`sanitize_crds`,
`crd_groups`) use a custom `_CRDLoader` subclass that registers a constructor for
`tag:yaml.org,2002:value` to handle this. Do not replace these loaders with
`yaml.SafeLoader` or files will be silently skipped.

### Multi-document CRD overlay files

Some repositories (e.g. VictoriaMetrics `config/crd/overlay/`) ship variant CRD files
(`crd.yaml`, `crd.descriptionless.yaml`, `crd.specless.yaml`) each containing all CRDs
as a multi-document YAML. `collect_crds` deduplicates by `(group, version, kind)` and
writes one file per CRD (not a copy of the whole source file) to avoid `AlreadyExists`
errors when `kubectl create` is run by `envtest.py`.

### kubectl create vs apply for CRD installation

`tools/envtest.py` uses `kubectl create` (not `apply`) to install CRDs into the
envtest API server. `kubectl apply` adds a
`kubectl.kubernetes.io/last-applied-configuration` annotation containing the full CRD
JSON, which can exceed the 256 KB kube-apiserver annotation limit for large CRDs.

### compare-schemas mismatch after host_conversion_rules change

Step 13 (`compare_schemas`) checks that every root CRD kind appears under the same
definition key in both `json-schema/source/` and `json-schema/live/`. A
`MISS` in the **source** column means a `host_conversion_rules` rule is wrong or
missing. A `MISS` in the **live** column means the CRD exists in the source but was
not served by the live API server (usually a missing or unserved version in the chart).

Common root causes for source MISS:
- The controller has CRDs in **multiple API groups** (e.g. `cert-manager.io` and
  `acme.cert-manager.io`) but only one module-level rule was set — add per-package
  rules for each non-default group.
- The module path doesn't share a prefix with the CRD group (e.g. `sigs.k8s.io/gateway-api`
  vs `gateway.networking.k8s.io`) — add an explicit mapping.
- A type is listed in `crd_names` but the Go type doesn't exist at that version
  (CRD added to helm chart before Go type was written) — remove from `crd_names`.

### generated/ is gitignored

The `**/generated/*` pattern in `.gitignore` covers intermediate build artifacts.
Do not commit anything under `generated/`.

---

## Site (`site/`)

An [Astro](https://astro.build) static site (`output: 'static'`, `trailingSlash: 'always'`)
that reads schema data from `schemas/` at build time. No server or database — everything
is pre-rendered to HTML + JSON files in `site/dist/`.

### Site structure

```
site/
  src/
    layouts/
      Layout.astro               # Shared HTML shell (nav, breadcrumbs, footer)
    components/
      ResourcesTable.tsx          # React island — resource list with "Hide system" toggle
      FileBadge.astro             # "source" / "live" badge with CSS-only tooltip
      DiffView.astro              # Version-diff display (added/removed/changed)
      PropertyTree.tsx            # Interactive JSON Schema field tree (React island)
      ChangeHistory.tsx           # Per-resource change history across versions (React island)
      ControllerIcon.astro        # Org avatar from GitHub
    lib/
      data.ts                     # All data-access functions (reads schemas/ at build time)
      types.ts                    # Shared TypeScript interfaces (Controller, Resource, …)
    pages/
      index.astro                 # Home — controller grid + hero with API link
      about.astro                 # "How it's built" documentation page
      [org]/[repo]/
        index.astro               # Controller overview: version list + latest resource table
        [version]/
          index.astro             # Version page: diff, Files & Links, ResourcesTable
          [group]/[kind].astro    # Resource kind page: schema tree, Files & Links, history
      api/v1/
        index.json.ts             # Level 1: list of all controllers
        [org]/[repo]/
          index.json.ts           # Level 2: controller metadata + version list
          [version]/
            index.json.ts         # Level 3: full resource list with schema URLs
```

### Running the site

```bash
cd site
npm install
npm run dev        # dev server at http://localhost:4321
npm run build      # static build to site/dist/
npm run preview    # preview the built output
```

Or via the root Makefile:
```bash
make site-dev      # npm run dev
make site-build    # npm run build
```

### Data layer (`site/src/lib/data.ts`)

All functions read directly from `schemas/` using Node `fs` (only available at build time):

| Function | Returns |
|---|---|
| `getAllControllers()` | All controllers sorted by org/repo, versions newest-first |
| `getControllerMeta(org, repo)` | `name`, `repository` from controller `index.yaml` |
| `getResources(org, repo, version)` | Resource list from version `index.yaml` |
| `getVersionDiff(org, repo, vNew, vOld)` | Added/removed/changed resources between versions |
| `getVersionAssets(org, repo, version)` | GitHub and file URLs for a version's artifacts |
| `getResourceAssets(org, repo, version, kind, group, apiVersion, plural)` | Per-resource artifact URLs + `definitionKey` |
| `getResourceSchema(…)` | Parsed JSON Schema from `json-schema/source/` CRD file |
| `getResourceSchemaFromDefinitions(…)` | Schema from `_definitions.json` (Kubernetes built-ins) |
| `getDefinitions(…)` | Full definitions map from `_definitions.json` |
| `getChangeHistory(…)` | Schema diff history for a resource across all versions |

### `index.yaml` formats

**Controller-level** (`schemas/ORG/REPO/index.yaml`):
```yaml
name: "Human-readable name"
repository: "https://github.com/ORG/REPO"
systemResources:              # optional — T2 system resources (see §Resource classification)
  - kind: Endpoints
    group: ""
  - kind: EndpointSlice
    group: discovery.k8s.io
```

**Version-level** (`schemas/ORG/REPO/VERSION/index.yaml`):
```yaml
resources:
  - kind: Deployment
    group: apps
    version: v1
    plural: deployments
    scope: Namespaced
    shortNames: [deploy]      # optional
    definitionKey: io.k8s.api.apps.v1.Deployment   # optional — set by annotate_definition_keys()
    userManaged: false         # optional — omitted for normal resources, false for system ones
```

### Resource classification (`userManaged` field)

Resources fall into three categories:

**User-managed** (default — `userManaged` omitted): resources intended to be created and
managed directly by users (`Deployment`, `Service`, `ConfigMap`, etc.).

**System — auto-detected (T1)**: set `userManaged: false` automatically by `tools/discover.py`
when API verbs do not include `delete` (e.g. `TokenReview`, `Binding`, `ComponentStatus`)
or the group is `internal.apiserver.k8s.io`.

**System — manually listed (T2)**: set `userManaged: false` by `tools/discover.py` at
generation time from the controller-level `systemResources` list. Use for resources that
have full verbs but are managed by the control plane rather than users (e.g. `Endpoints`,
`EndpointSlice`, `VolumeAttachment`).

The site shows a `system` badge on these resources and the `ResourcesTable` component
offers a "Hide system resources" toggle (only when discovery data is available).

### `definitionKey` — JSON Schema `$ref` name

`tools/generate.py` calls `annotate_definition_keys()` after schema generation to match
each resource to its key in `_definitions.json` (e.g. `io.k8s.api.apps.v1.Deployment`)
and write it back to `index.yaml`. Matching logic:
- Find all keys in `_definitions.json` whose last dot-segment equals `resource.kind`
- Prefer the key whose prefix starts with the first segment of `resource.group`
- Write the best match as `definitionKey` in the resource entry

The site uses `definitionKey` for the copyable `$ref` name shown on resource kind pages.
`getResourceAssets()` prefers this pre-computed value and falls back to scanning
`_definitions.json` live at build time.

### Static JSON API

Three levels of static JSON files are generated as Astro endpoint files and served from `dist/`:

| Path | Content |
|---|---|
| `/api/v1/index.json` | All controllers: org, repo, name, repository, latestVersion, versions[], url |
| `/api/v1/{org}/{repo}/index.json` | Controller: org, repo, name, repository, versions[{version, url}] |
| `/api/v1/{org}/{repo}/{version}/index.json` | Version: org, repo, version, crdsBundle, openapiSource, openapiLive, resources[…] |

Each resource entry in the Level 3 response includes:
```json
{
  "kind": "Deployment", "group": "apps", "version": "v1",
  "plural": "deployments", "scope": "Namespaced",
  "shortNames": ["deploy"],
  "definitionKey": "io.k8s.api.apps.v1.Deployment",
  "userManaged": false,
  "urls": {
    "definitionsSource": "https://github.com/…/_definitions.json",
    "definitionsLive":   "https://github.com/…/_definitions.json",
    "schemaSource":      "https://github.com/…/deployment-apps-v1.json",
    "schemaLive":        "https://github.com/…/deployment-apps-v1.json",
    "crd":               null
  }
}
```

### JSON Schema filename formula

```
non-core: {kind.toLowerCase()}-{group.split('.')[0]}-{apiVersion}.json
core:     {kind.toLowerCase()}-{apiVersion}.json
```

Examples: `deployment-apps-v1.json`, `pod-v1.json`, `clusterpolicy-kyverno-v1.json`.

---

## Tooling

| Tool | Purpose | Install |
|---|---|---|
| `openapi-gen` | Generates Go OpenAPI definitions from annotated types | `go install k8s.io/kube-openapi/cmd/openapi-gen@VERSION` |
| `openapi2jsonschema` | Converts OpenAPI spec to JSON Schema files | Python venv (`instrumenta/openapi2jsonschema`) |
| `setup-envtest` | Downloads envtest binaries (etcd + kube-apiserver + kubectl) | `go install sigs.k8s.io/controller-runtime/tools/setup-envtest@latest` |
| `tools/envtest_openapi.py` | Starts envtest, fetches `/openapi/v2`, produces `json-schema/live/` | bundled in repo |
| `tools/run.py` | Parallel generation runner (discovers configs, launches Docker containers) | bundled in repo |
| `go` | Compiles and runs the OpenAPI builder | brew / golang.org |
| `git` | Clones controller source | system |

The Docker builder image (`make builder`) bundles all of the above including
pre-downloaded envtest binaries at `$ENVTEST_BIN_DIR=/usr/local/kubebuilder/bin`.
