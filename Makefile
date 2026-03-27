CONTROLLER ?=
VERSION    ?=
THREADS    ?=

BUILDER_IMAGE := schema-builder
REPO_ROOT     := $(CURDIR)

# ── Builder image ──────────────────────────────────────────────────────────────

.PHONY: builder
builder:
	docker build --pull -t $(BUILDER_IMAGE) builder/

# ── Schema generation (Docker) ─────────────────────────────────────────────────
#
# Usage:
#   make generate CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
#
.PHONY: generate
generate:
	@test -n "$(CONTROLLER)" || (echo "ERROR: CONTROLLER is required"; exit 1)
	@test -n "$(VERSION)"    || (echo "ERROR: VERSION is required"; exit 1)
	docker run --rm $(if $(shell [ -t 0 ] && echo y),-it) \
		-v "$(REPO_ROOT):/repo" \
		-w "/repo" \
		$(BUILDER_IMAGE) \
		python3 tools/generate.py config/$(CONTROLLER)/$(VERSION)/config.yaml

# ── Schema generation (local) ──────────────────────────────────────────────────
#
# Usage:
#   make generate-local CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
#
.PHONY: generate-local
generate-local:
	@test -n "$(CONTROLLER)" || (echo "ERROR: CONTROLLER is required"; exit 1)
	@test -n "$(VERSION)"    || (echo "ERROR: VERSION is required"; exit 1)
	python3 tools/generate.py config/$(CONTROLLER)/$(VERSION)/config.yaml

# ── Parallel generation — all controllers, all versions (Docker) ───────────────
#
# Usage:
#   make generate-all              # 8 threads (default)
#   make generate-all THREADS=4
#
.PHONY: generate-all
generate-all:
	python3 tools/run.py $(if $(THREADS),--threads $(THREADS)) --docker $(BUILDER_IMAGE) config

# ── Parallel generation — all versions of one controller (Docker) ──────────────
#
# Usage:
#   make generate-all-versions CONTROLLER=aws/karpenter-provider-aws
#   make generate-all-versions CONTROLLER=aws/karpenter-provider-aws THREADS=4
#
.PHONY: generate-all-versions
generate-all-versions:
	@test -n "$(CONTROLLER)" || (echo "ERROR: CONTROLLER is required"; exit 1)
	python3 tools/run.py $(if $(THREADS),--threads $(THREADS)) --docker $(BUILDER_IMAGE) config/$(CONTROLLER)

# ── Kubernetes built-in schema generation ──────────────────────────────────────
#
# Usage:
#   make generate-kubernetes VERSION=v1.34.1
#
K8S_DISCOVERY_BASE := https://raw.githubusercontent.com/kubernetes/kubernetes

.PHONY: generate-kubernetes
generate-kubernetes:
	@test -n "$(VERSION)" || (echo "ERROR: VERSION is required"; exit 1)
	mkdir -p schemas/kubernetes/kubernetes/$(VERSION)/openapi
	mkdir -p schemas/kubernetes/kubernetes/$(VERSION)/json-schema/source
	curl -fsSL \
		"$(K8S_DISCOVERY_BASE)/$(VERSION)/api/openapi-spec/swagger.json" \
		-o schemas/kubernetes/kubernetes/$(VERSION)/openapi/source.json
	openapi2jsonschema \
		schemas/kubernetes/kubernetes/$(VERSION)/openapi/source.json \
		-o schemas/kubernetes/kubernetes/$(VERSION)/json-schema/source \
		--strict --kubernetes --expanded
	python3 tools/discover.py \
		--discovery-base-url "$(K8S_DISCOVERY_BASE)/$(VERSION)/api/discovery" \
		--output schemas/kubernetes/kubernetes/$(VERSION)/index.yaml

# ── Documentation site ─────────────────────────────────────────────────────────
#
# Usage:
#   make icons             # download controller icons to schemas/ORG/REPO/icon.*
#   make site-install      # install npm deps (once)
#   make site              # build static site → site/dist/
#   make site-dev          # run dev server (hot reload)
#   make site-preview      # preview the built site locally
#
# For GitHub Pages with a base path:
#   BASE_PATH=/schemas make site
#
BASE_PATH ?=

.PHONY: icons
icons:
	python3 tools/download_icons.py

.PHONY: site-install
site-install:
	npm --prefix site ci

.PHONY: site
site:
	BASE_PATH="$(BASE_PATH)" npm --prefix site run build

.PHONY: site-dev
site-dev:
	npm --prefix site run dev

.PHONY: site-preview
site-preview:
	npm --prefix site run preview

# ── Validation ─────────────────────────────────────────────────────────────────
#
# Usage:
#   make validate CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
#
.PHONY: validate
validate:
	@test -n "$(CONTROLLER)" || (echo "ERROR: CONTROLLER is required"; exit 1)
	@test -n "$(VERSION)"    || (echo "ERROR: VERSION is required"; exit 1)
	python3 tools/validate.py schemas/$(CONTROLLER)/$(VERSION)/json-schema/source
