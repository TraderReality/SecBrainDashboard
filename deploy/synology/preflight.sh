#!/usr/bin/env bash

# Read-only inventory for the Synology target. It changes neither packages,
# volumes, permissions nor network settings.
set -u

env_file="${1:-.env.synology}"

echo "▶ 1/7 · DSM und Hardware"
printf 'hostname=%s\n' "$(hostname 2>/dev/null || echo unbekannt)"
printf 'kernel=%s\n' "$(uname -srmo 2>/dev/null || echo unbekannt)"
if command -v synogetkeyvalue >/dev/null 2>&1; then
    printf 'model=%s\n' "$(synogetkeyvalue /etc.defaults/synoinfo.conf upnpmodelname 2>/dev/null || echo unbekannt)"
    printf 'dsm=%s-%s\n' \
        "$(synogetkeyvalue /etc.defaults/VERSION productversion 2>/dev/null || echo unbekannt)" \
        "$(synogetkeyvalue /etc.defaults/VERSION buildnumber 2>/dev/null || echo unbekannt)"
fi

echo "▶ 2/7 · Arbeitsspeicher"
free -h 2>/dev/null || awk '/MemTotal|MemAvailable/ {print}' /proc/meminfo

echo "▶ 3/7 · Speicherpools und Volumes"
df -h -T /volume* 2>/dev/null || echo "✗ Keine lesbaren /volume*-Pfade gefunden"
mount | grep -E ' on /volume[0-9]+' || true

echo "▶ 4/7 · Container Manager"
if command -v synopkg >/dev/null 2>&1; then
    synopkg status ContainerManager 2>&1 || synopkg status Docker 2>&1 || true
else
    echo "✗ synopkg nicht im PATH"
fi
if command -v docker >/dev/null 2>&1; then
    docker version --format 'docker-client={{.Client.Version}} docker-server={{.Server.Version}}' 2>&1 || true
    docker compose version 2>&1 || true
else
    echo "✗ docker nicht im PATH"
fi

echo "▶ 5/7 · Ausführendes Dienstkonto"
id

echo "▶ 6/7 · Geplante Pfade"
if [[ -r "$env_file" ]]; then
    while IFS='=' read -r key value; do
        case "$key" in
            SECBRAIN_MAIN_VAULT|SECBRAIN_MAIN_STATE|SECBRAIN_DEV_VAULT|SECBRAIN_DEV_STATE)
                parent="$(dirname "$value")"
                if [[ -d "$parent" ]]; then
                    printf '✓ %s parent=%s\n' "$key" "$parent"
                else
                    printf '✗ %s parent fehlt: %s\n' "$key" "$parent"
                fi
                ;;
        esac
    done < "$env_file"
else
    echo "✗ Umgebungsdatei nicht lesbar: $env_file"
fi

echo "▶ 7/7 · Ollama vom NAS aus"
ollama_url="$(sed -nE 's/^SECBRAIN_OLLAMA_URL=(.*)$/\1/p' "$env_file" 2>/dev/null | tail -1)"
if [[ -n "$ollama_url" ]] && command -v curl >/dev/null 2>&1; then
    curl --max-time 5 --fail-with-body \
        --write-out '\nHTTP %{http_code} in %{time_total}s\n' \
        "$ollama_url/api/version" 2>&1 \
        && echo "✓ Ollama erreichbar" \
        || echo "✗ Ollama nicht erreichbar; Firewall und Bind-Adresse prüfen"
else
    echo "✗ Ollama-URL oder curl fehlt"
fi

echo "✓ Read-only Preflight abgeschlossen"
