#!/usr/bin/env bash

# Opens the production Watcher on the Synology NAS. The local backend remains
# available only as an explicit rollback path so a NAS outage cannot silently
# create a second writable Main instance.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$project_root/.venv/bin/python"
backend_dir="$project_root/dashboard/backend"
nas_watcher_url="${SECBRAIN_WATCHER_URL:-http://192.168.0.79:18080}"
local_watcher_url="http://127.0.0.1:8080"
watcher_url="$nas_watcher_url"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/secbrain-watcher"
log_file="$state_dir/backend.log"
service_name="secbrain-watcher.service"

notify_error() {
    local message="$1"
    if command -v notify-send >/dev/null 2>&1; then
        notify-send --urgency=critical "SECBrain Watcher" "$message"
    fi
    printf '%s\n' "$message" >&2
}

watcher_is_ready() {
    "$python_bin" - "$watcher_url/api/status" <<'PY'
import sys
from urllib.request import urlopen

try:
    with urlopen(sys.argv[1], timeout=0.8) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

open_watcher() {
    if [[ "${SECBRAIN_WATCHER_NO_OPEN:-0}" != "1" ]]; then
        xdg-open "$watcher_url" >/dev/null 2>&1 &
    fi
}

if [[ "${1:-}" != "--local-rollback" ]]; then
    if watcher_is_ready; then
        open_watcher
        exit 0
    fi
    notify_error "NAS-Main ist unter $watcher_url nicht erreichbar. Der lokale Main wurde nicht automatisch gestartet. Für einen bewussten Rückfall: $0 --local-rollback"
    exit 1
fi

watcher_url="$local_watcher_url"

if [[ ! -x "$python_bin" ]]; then
    notify_error "Die virtuelle Python-Umgebung für den lokalen Rückfall fehlt."
    exit 1
fi

if watcher_is_ready; then
    open_watcher
    exit 0
fi

mkdir -p "$state_dir"

if command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    systemctl --user stop "$service_name" >/dev/null 2>&1 || true
    systemctl --user reset-failed "$service_name" >/dev/null 2>&1 || true
    systemd-run --user \
        --unit="${service_name%.service}" \
        --collect \
        --quiet \
        --property=Restart=on-failure \
        --property=RestartSec=2s \
        --property="StandardOutput=append:$log_file" \
        --property="StandardError=append:$log_file" \
        "$python_bin" -m uvicorn dashboard_api:app \
        --app-dir "$backend_dir" \
        --host 127.0.0.1 \
        --port 8080
else
    # Fallback for systems without a usable user-systemd session.
    setsid -f "$python_bin" -m uvicorn dashboard_api:app \
        --app-dir "$backend_dir" \
        --host 127.0.0.1 \
        --port 8080 \
        >>"$log_file" 2>&1
fi

for _attempt in {1..50}; do
    if watcher_is_ready; then
        open_watcher
        exit 0
    fi
    sleep 0.2
done

notify_error "Der Watcher konnte nicht gestartet werden. Details stehen in $log_file"
exit 1
