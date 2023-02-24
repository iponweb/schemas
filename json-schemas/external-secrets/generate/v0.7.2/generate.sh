set -e

#: Settings
VERSION="v0.7.2"
REPOSITORY="github.com/external-secrets/external-secrets"

#: Execution
ROOT="$(pwd)"

#: Clone operator sources to $GOPATH
SOURCES_ROOT="${GOPATH}/src/${REPOSITORY}"

rm -rf "${SOURCES_ROOT}"
mkdir -p "${SOURCES_ROOT}"
#: Cleanup the source directory after execution
trap 'rm -rf "${SOURCES_ROOT}"' EXIT

git clone --depth 1 --branch "${VERSION}" \
  "https://${REPOSITORY}" "${SOURCES_ROOT}"

#: Apply patch
cd "${SOURCES_ROOT}" && git apply "${ROOT}/generate/${VERSION}/patch.diff"

#: Download dependencies
cd "${SOURCES_ROOT}" && go mod vendor

#: Generate OpenAPI golang scheme
GO111MODULE=off openapi-gen -v 4 -h "${ROOT}/generate/boilerplate.go.txt" \
    --input-dirs "${REPOSITORY}/apis/externalsecrets/v1alpha1" \
    --input-dirs "${REPOSITORY}/apis/externalsecrets/v1beta1" \
    --input-dirs "${REPOSITORY}/apis/generators/v1alpha1" \
    --input-dirs "${REPOSITORY}/apis/meta/v1" \
    --input-dirs "k8s.io/apimachinery/pkg/apis/meta/v1,k8s.io/apimachinery/pkg/runtime,k8s.io/apimachinery/pkg/version" \
    --output-package "generated/openapi" \
    --output-file-base "openapi_generated" \
    --output-base "${ROOT}/generate/${VERSION}"

#: Generate OpenAPI json scheme
cd "${ROOT}/generate/${VERSION}" \
  && go mod tidy \
  && go run generate-openapi-json.go > generated/openapi/openapi.json

#: Generate json-schema
OUTPUT_DIR="${ROOT}/${VERSION}-strict"
rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

openapi2jsonschema \
  "${ROOT}/generate/${VERSION}/generated/openapi/openapi.json" \
  -o "${OUTPUT_DIR}" --strict --expanded --kubernetes
