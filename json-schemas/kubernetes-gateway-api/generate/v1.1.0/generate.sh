set -e

#: Settings
VERSION="v1.1.0"
REPOSITORY="github.com/kubernetes-sigs/gateway-api"

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
cd "${SOURCES_ROOT}" && git apply --allow-empty "${ROOT}/generate/${VERSION}/patch.diff"

#: Download dependencies
cd "${SOURCES_ROOT}" && go mod vendor

#: Generate OpenAPI golang scheme
GO111MODULE=off openapi-gen -v 4 -h "${ROOT}/generate/boilerplate.go.txt" \
    --input-dirs "${REPOSITORY}/apis/v1" \
    --input-dirs "k8s.io/apimachinery/pkg/apis/meta/v1,k8s.io/apimachinery/pkg/runtime,k8s.io/apimachinery/pkg/version,k8s.io/api/core/v1" \
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
