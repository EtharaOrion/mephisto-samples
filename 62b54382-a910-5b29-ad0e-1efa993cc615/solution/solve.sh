
set -eu

BPFC="/usr/local/bin/bpfc-oracle"
if [ ! -x "$BPFC" ]; then
    echo "solve.sh: oracle binary missing at $BPFC" >&2
    exit 2
fi

exec "$BPFC" "$@"
