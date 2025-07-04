FROM golang:alpine as builder

#: install openapi-gen
#:
#: See also:
#: - https://github.com/kubernetes/kube-openapi/tree/master/cmd/openapi-gen
#:
RUN set -x \
    && go install k8s.io/kube-openapi/cmd/openapi-gen@9bd5c66d9911c53f5aedb8595fde9c229ca56703

FROM golang:alpine

#: install openapi2jsonschema
#:
#: See also:
#: - https://github.com/instrumenta/openapi2jsonschema
#:
RUN set -x \
    && apk add --no-cache python3 py3-pip git \
    && python3 -m venv /venv \
    && /venv/bin/pip install -U setuptools \
    && /venv/bin/pip install --no-build-isolation wheel "cython<3.0.0" openapi2jsonschema pyyaml openapi2jsonschema


ENV PATH="/venv/bin:$PATH"

COPY --from=builder /go/bin/openapi-gen /bin/openapi-gen
