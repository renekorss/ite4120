#!/bin/sh
set -eu
mkdir -p artifacts
image_list=$(mktemp)
trap 'rm -f "$image_list"' EXIT HUP INT TERM
docker compose -f compose.yaml -f compose.mock.yaml -f compose.api.yaml config --images > "$image_list"
sort -u "$image_list" -o "$image_list"
while IFS= read -r image; do
  name=$(printf '%s' "$image" | tr '/:@' '____')
  docker scout sbom --format spdx "$image" > "artifacts/$name.spdx.json"
done < "$image_list"
