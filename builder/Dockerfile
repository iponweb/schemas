FROM golang:alpine AS builder

#: install openapi-gen
#:
#: See also:
#: - https://github.com/kubernetes/kube-openapi/tree/master/cmd/openapi-gen
#:
RUN set -x \
    && go install 'k8s.io/kube-openapi/cmd/openapi-gen@5b3e3fdb0acf'

#: install setup-envtest and pre-download envtest binaries (etcd + kube-apiserver + kubectl)
#: for CRD live-discovery (used by tools/envtest.py).
#:
#: See also:
#: - https://pkg.go.dev/sigs.k8s.io/controller-runtime/tools/setup-envtest
#:
ENV ENVTEST_K8S_VERSION=1.32.x
RUN set -x \
    && go install sigs.k8s.io/controller-runtime/tools/setup-envtest@latest \
    && BINPATH=$(setup-envtest use ${ENVTEST_K8S_VERSION} --bin-dir /tmp/envtest-dl -p path) \
    && mkdir -p /usr/local/kubebuilder/bin \
    && cp "$BINPATH"/etcd "$BINPATH"/kube-apiserver "$BINPATH"/kubectl /usr/local/kubebuilder/bin/

FROM golang:alpine

#: install openapi2jsonschema and envtest system deps
#:
#: See also:
#: - https://github.com/instrumenta/openapi2jsonschema
#:
RUN set -x \
    && apk add --no-cache python3 py3-pip git openssl \
    && python3 -m venv /venv \
    && /venv/bin/pip install -U setuptools \
    && /venv/bin/pip install --no-build-isolation wheel "cython<3.0.0" openapi2jsonschema pyyaml openapi2jsonschema


ENV PATH="/venv/bin:$PATH"
ENV ENVTEST_BIN_DIR=/usr/local/kubebuilder/bin

COPY --from=builder /go/bin/openapi-gen          /bin/openapi-gen
COPY --from=builder /usr/local/kubebuilder/bin   /usr/local/kubebuilder/bin
