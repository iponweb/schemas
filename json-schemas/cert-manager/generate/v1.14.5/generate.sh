set -e

#: Settings
VERSION="v1.14.5"
REPOSITORY="github.com/cert-manager/cert-manager"

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

#: Fix sigs
#sed -i '1s;^;// +k8s:openapi-gen=true\n;' "${GOPATH}/src/sigs.k8s.io/gateway-api/apis/v1/doc.go"
sed -i '1s;^;// +k8s:openapi-gen=true\n;' "${SOURCES_ROOT}/vendor/sigs.k8s.io/gateway-api/apis/v1/doc.go"

#: Generate OpenAPI golang scheme
GO111MODULE=off openapi-gen -v 4 -h "${ROOT}/generate/boilerplate.go.txt" \
    --input-dirs "${REPOSITORY}/pkg/apis/certmanager/v1" \
    --input-dirs "${REPOSITORY}/pkg/apis/acme/v1" \
    --input-dirs "${REPOSITORY}/pkg/apis/meta/v1" \
    --input-dirs "k8s.io/apimachinery/pkg/apis/meta/v1,k8s.io/apimachinery/pkg/runtime,k8s.io/apimachinery/pkg/version,k8s.io/api/core/v1,sigs.k8s.io/gateway-api/apis/v1" \
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
