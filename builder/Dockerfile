FROM golang:alpine as builder

#: install openapi-gen
#:
#: See also:
#: - https://github.com/kubernetes/kube-openapi/tree/master/cmd/openapi-gen
#:
RUN set -x \
    && go install k8s.io/kube-openapi/cmd/openapi-gen@89dc17294c724e45c647d896300e9b583687b7c0

FROM golang:alpine

#: install openapi2jsonschema
#:
#: See also:
#: - https://github.com/instrumenta/openapi2jsonschema
#:
RUN set -x \
    && apk add --no-cache python3 py3-pip git \
    && python3 -m venv /venv \
    && /venv/bin/pip install wheel \
    && /venv/bin/pip install "cython<3.0.0" \
    && /venv/bin/pip install --no-build-isolation pyyaml==5.4.1 \
    && /venv/bin/pip install openapi2jsonschema


ENV PATH="/venv/bin:$PATH"

COPY --from=builder /go/bin/openapi-gen /bin/openapi-gen
