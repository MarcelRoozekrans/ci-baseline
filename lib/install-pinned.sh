#!/usr/bin/env bash
# Usage: install-pinned.sh <url> <sha256> <dest-dir>
# Downloads <url>, verifies its SHA-256, installs into <dest-dir> and appends
# <dest-dir> to $GITHUB_PATH. Handles .tar.gz, .zip and bare binaries.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <url> <sha256> <dest-dir>" >&2
  exit 2
fi

url=$1
sha=$2
dest=$3

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

file="$tmp/download"
curl --fail --silent --show-error --location --retry 3 --output "$file" "$url"

if ! echo "$sha  $file" | sha256sum --check --status; then
  echo "::error::checksum mismatch for $url"
  exit 1
fi

mkdir -p "$dest"
case "$url" in
  *.tar.gz | *.tgz) tar -xzf "$file" -C "$dest" ;;
  *.zip) unzip -q -o "$file" -d "$dest" ;;
  *) cp "$file" "$dest/$(basename "${url%%\?*}")" ;;
esac
chmod -R +x "$dest" 2>/dev/null || true

echo "$dest" >> "${GITHUB_PATH:?GITHUB_PATH must be set}"
