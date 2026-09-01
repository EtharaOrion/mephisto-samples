#!/usr/bin/env sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HERE/bin"
cp "$HERE/src/scheduler.py" "$HERE/bin/schedule"
chmod 0755 "$HERE/bin/schedule"
