# Schemas

JSON Schemas for Kubernetes built-in APIs and third-party controllers/operators.
Used by [metachart](https://github.com/iponweb/metachart) for Helm chart validation.

Inspired by [instrumenta/kubernetes-json-schema](https://github.com/instrumenta/kubernetes-json-schema).

## Structure

```
schemas/
  ORG/REPO/
    index.yaml          # Controller metadata (name, repository URL)
    VERSION/
      index.yaml        # Resource list with GVK (group/version/kind)
      crds.yaml         # All CRDs as a single multi-document YAML (for Terraform)
      crd/              # Individual CRD YAML files (one per CRD name)
      discovery/        # Raw API discovery JSON files
      json-schema/
        source/         # Schemas generated from Go source via openapi-gen
        live/           # Schemas from a live kube-apiserver (via envtest)
      openapi/
        source.json     # Merged OpenAPI spec (source-generated)
        live.json       # OpenAPI spec from live kube-apiserver
```

Built-in Kubernetes schemas live under `schemas/kubernetes/kubernetes/VERSION/`.

## Generating schemas

**Prerequisites:** Docker (for the builder image) or a local Go + Python environment.

```bash
# Build the Docker image once
make builder

# Generate schemas for a controller
make generate CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0

# Generate built-in Kubernetes schemas
make generate-kubernetes VERSION=v1.34.1

# Validate generated schemas
make validate CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
```

Local (no Docker):

```bash
make generate-local CONTROLLER=aws/karpenter-provider-aws VERSION=v1.10.0
```

See [CLAUDE.md](CLAUDE.md) for the full generation pipeline reference.

## Using `crds.yaml` with Terraform

Each controller version includes a `crds.yaml` — all CRDs concatenated into a single
multi-document YAML. This is convenient for Terraform:

```hcl
data "kubectl_file_documents" "crds" {
  content = file("schemas/aws/karpenter-provider-aws/v1.10.0/crds.yaml")
}

resource "kubectl_manifest" "crds" {
  for_each          = data.kubectl_file_documents.crds.manifests
  yaml_body         = each.value
  server_side_apply = true
}
```

## For controller developers

If you maintain a Kubernetes controller with custom resources and are interested in
[metachart](https://github.com/iponweb/metachart) Helm chart generation, consider
hosting OpenAPI and JSON schemas in your own repository to speed up version support
and reduce errors.
