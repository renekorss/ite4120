#!/bin/sh
set -eu
mkdir -p artifacts
# Read resolved pinned references without printing secrets from Compose configuration.
image_list=$(mktemp)
trap 'rm -f "$image_list"' EXIT HUP INT TERM
docker compose config --images > "$image_list"
while IFS= read -r image; do
  name=$(printf '%s' "$image" | tr '/:@' '____')
  docker scout cves --only-severity critical,high --exit-code "$image" > "artifacts/$name.cves.txt" 2>&1
done < "$image_list"
