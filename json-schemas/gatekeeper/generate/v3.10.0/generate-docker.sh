VERSION="v3.10.0"

docker run -it --rm -v "$(pwd):/src" -w "/src" schema-builder sh "/src/generate/${VERSION}/generate.sh"
