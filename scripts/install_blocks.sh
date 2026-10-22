#!/usr/bin/env bash
# Reinstall the house catalog blocks into a HyperFrames project and restyle them.
#   install_blocks.sh [PROJECT_DIR]   (default: templates/ovs-vertical)
# --force overwrites local edits, so only run this to rebuild from the catalog.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJ="${1:-$ROOT/templates/ovs-vertical}"
cd "$PROJ"
while read -r name; do
  [ -n "$name" ] && npx -y hyperframes@0.8.185 add "$name" --force --json >/dev/null
done < "$ROOT/templates/ovs-vertical/blocks.txt"
python3 "$ROOT/scripts/restyle_blocks.py" "$PROJ" | awk '{print $1}' | sort | uniq -c
npx -y hyperframes@0.8.185 lint
