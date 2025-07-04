VERSION="v0.18.2"

docker run -it --rm -v "$(pwd):/src" -w "/src" schema-builder sh "/src/generate/${VERSION}/generate.sh"
