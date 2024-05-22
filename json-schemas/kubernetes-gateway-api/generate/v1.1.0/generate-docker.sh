VERSION="v1.1.0"

docker run -it --rm -v "$(pwd):/src" -w "/src" schema-builder sh "/src/generate/${VERSION}/generate.sh"
