VERSION="v1.4.6"

docker run -it --rm -v "$(pwd):/src" -w "/src" schema-builder sh "/src/generate/${VERSION}/generate.sh"
