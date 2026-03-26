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
#   make generate CONTROLLER=karpenter VERSION=v1.10.0
#
.PHONY: generate
generate:
	@test -n "$(CONTROLLER)" || (echo "ERROR: CONTROLLER is required"; exit 1)
	@test -n "$(VERSION)"    || (echo "ERROR: VERSION is required"; exit 1)
	docker run -it --rm \
		-v "$(REPO_ROOT):/repo" \
		-w "/repo/json-schemas/$(CONTROLLER)" \
		$(BUILDER_IMAGE) \
		python3 /repo/tools/generate.py generate/$(VERSION)/config.yaml

# ── Schema generation (local) ──────────────────────────────────────────────────
#
# Usage:
#   make generate-local CONTROLLER=karpenter VERSION=v1.10.0
#
.PHONY: generate-local
generate-local:
	@test -n "$(CONTROLLER)" || (echo "ERROR: CONTROLLER is required"; exit 1)
	@test -n "$(VERSION)"    || (echo "ERROR: VERSION is required"; exit 1)
	cd json-schemas/$(CONTROLLER) && python3 ../../tools/generate.py generate/$(VERSION)/config.yaml

# ── Kubernetes built-in schema generation ──────────────────────────────────────
#
# Usage:
#   make generate-kubernetes VERSION=v1.34.1
#
.PHONY: generate-kubernetes
generate-kubernetes:
	@test -n "$(VERSION)" || (echo "ERROR: VERSION is required"; exit 1)
	cd json-schemas/kubernetes && KUBERNETES_VERSION=$(VERSION) sh generate/generage.sh

# ── Validation ─────────────────────────────────────────────────────────────────
#
# Usage:
#   make validate CONTROLLER=karpenter VERSION=v1.10.0
#
.PHONY: validate
validate:
	@test -n "$(CONTROLLER)" || (echo "ERROR: CONTROLLER is required"; exit 1)
	@test -n "$(VERSION)"    || (echo "ERROR: VERSION is required"; exit 1)
	python3 tools/validate.py json-schemas/$(CONTROLLER)/$(VERSION)-strict
