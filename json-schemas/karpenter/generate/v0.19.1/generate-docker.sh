VERSION="v0.19.1"

docker run -it --rm -v "$(pwd):/src" -w "/src" schema-builder sh "/src/generate/${VERSION}/generate.sh"
