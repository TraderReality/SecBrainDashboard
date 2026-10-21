#!/usr/bin/env bash

# Installs the user-local KDE/GNOME desktop entry and regenerates it from the
# repository template, so updates never depend on a manually edited launcher.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template="$project_root/desktop/secbrain-watcher.desktop.in"
applications_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
desktop_file="$applications_dir/secbrain-watcher.desktop"

if [[ ! -f "$template" ]]; then
    printf 'Desktop-Vorlage fehlt: %s\n' "$template" >&2
    exit 1
fi

mkdir -p "$applications_dir"
sed "s|@PROJECT_ROOT@|$project_root|g" "$template" > "$desktop_file"
chmod 644 "$desktop_file"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$applications_dir" >/dev/null 2>&1 || true
fi

printf 'Startmenü-Eintrag installiert: %s\n' "$desktop_file"
