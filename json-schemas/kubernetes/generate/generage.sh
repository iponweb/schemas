ROOT="$(pwd)"

if [[ -z "${KUBERNETES_VERSION}" ]]; then
  echo "KUBERNETES_VERSION must be defined"
  exit 1
fi

#: Generate json-schema
OUTPUT_DIR="${ROOT}/${KUBERNETES_VERSION}-strict"
rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

openapi2jsonschema \
  "https://raw.githubusercontent.com/kubernetes/kubernetes/${KUBERNETES_VERSION}/api/openapi-spec/swagger.json" \
  -o "${OUTPUT_DIR}" --strict --kubernetes --expanded
