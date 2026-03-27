CONTROLLER ?=
VERSION    ?=

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
	docker run -it --rm \
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
	mkdir -p schemas/kubernetes/kubernetes/$(VERSION)/json-schema
	curl -fsSL \
		"$(K8S_DISCOVERY_BASE)/$(VERSION)/api/openapi-spec/swagger.json" \
		-o schemas/kubernetes/kubernetes/$(VERSION)/openapi/openapi.json
	openapi2jsonschema \
		schemas/kubernetes/kubernetes/$(VERSION)/openapi/openapi.json \
		-o schemas/kubernetes/kubernetes/$(VERSION)/json-schema \
		--strict --kubernetes --expanded
	python3 tools/discover.py \
		--discovery-base-url "$(K8S_DISCOVERY_BASE)/$(VERSION)/api/discovery" \
		--output schemas/kubernetes/kubernetes/$(VERSION)/index.yaml

# ── Validation ─────────────────────────────────────────────────────────────────
#
# Usage:
#   make validate CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
#
.PHONY: validate
validate:
	@test -n "$(CONTROLLER)" || (echo "ERROR: CONTROLLER is required"; exit 1)
	@test -n "$(VERSION)"    || (echo "ERROR: VERSION is required"; exit 1)
	python3 tools/validate.py schemas/$(CONTROLLER)/$(VERSION)/json-schema
