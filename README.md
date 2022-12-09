# Schemas

The repository contains JSON Schemas required for
[metachart](https://github.com/iponweb/metachart) born Helm Charts generation.

For complete charts list see [charts](https://github.com/iponweb/charts).

Inspired by
[instrumenta/kubernetes-json-schema](https://github.com/instrumenta/kubernetes-json-schema).

## Structure

Schemas:

```
schema-type/controller-name/v0.0.1-strict/_definitions.json
schema-type/controller-name/v0.0.1-strict/resource-controller-name-v1.json
```

Generators:

```
schema-type/controller-name/generate/v0.0.1/generate.sh
```

## Adding a schema

Currently, schema build process is pretty straightforward and can be divided
in the following steps:

- Clone the controller repository
- Prepare and apply patch to the controller sources. In most cases adding of
  the `// +k8s:openapi-gen=true` comment to the `doc.go` file of api definition
  is enough to enable OpenAPI schema generation from go sources. In some cases,
  dependencies also have to be patched. For example,
  [knative/pkg](https://github.com/knative/pkg) does not contain required
  comment.
- OpenAPI golang schema generation
- Conversion of golang OpenAPI schema to JSON OpenAPI definition
- OpenAPI JSON schema conversion to JSON Schema

## For operators developers

If you are an operator/api-server developer with custom resources, and you are
interested in the [metachart](https://github.com/iponweb/metachart) born Helm
Charts usage, we kindly recommend you to maintain OpenAPI and JSON schemas by
yourself and host them in your repositories to speedup new versions support
and decrease potential errors count.
