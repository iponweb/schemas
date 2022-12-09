FROM golang:alpine as builder

#: install openapi-gen
#:
#: See also:
#: - https://github.com/kubernetes/kube-openapi/tree/master/cmd/openapi-gen
#:
RUN set -x \
    && go install k8s.io/kube-openapi/cmd/openapi-gen@latest

FROM golang:alpine

#: install openapi2jsonschema
#:
#: See also:
#: - https://github.com/instrumenta/openapi2jsonschema
#:
RUN set -x \
    && apk add --no-cache python3 py3-pip git \
    && pip install openapi2jsonschema

COPY --from=builder /go/bin/openapi-gen /bin/openapi-gen
