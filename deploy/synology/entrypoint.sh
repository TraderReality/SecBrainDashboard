#!/bin/sh

set -eu

qmd_binary="${SECBRAIN_QMD_BINARY:-qmd}"
qmd_collection="${SECBRAIN_QMD_COLLECTION:-secbrain}"
vault_path="${SECBRAIN_VAULT_PATH:-/vault}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/state/qmd-cache}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/state/qmd-config}"

if [ "${qmd_binary#*/}" = "$qmd_binary" ]; then
    qmd_binary="$(command -v "$qmd_binary" || true)"
fi

if [ -z "$qmd_binary" ] || [ ! -x "$qmd_binary" ]; then
    echo "QMD-Binary wurde nicht gefunden: ${SECBRAIN_QMD_BINARY:-qmd}" >&2
    exit 1
fi

if [ ! -d "$vault_path" ]; then
    echo "Vault-Verzeichnis wurde nicht gefunden: $vault_path" >&2
    exit 1
fi

mkdir -p "$XDG_CACHE_HOME/qmd"
mkdir -p "$XDG_CONFIG_HOME/qmd"

collections="$($qmd_binary collection list)"
if printf '%s\n' "$collections" | grep -Fq "$qmd_collection (qmd://$qmd_collection/)"; then
    "$qmd_binary" update
else
    "$qmd_binary" collection add "$vault_path" \
        --name "$qmd_collection" \
        --mask '**/*.md'
fi

"$qmd_binary" status >/dev/null

exec "$@"
