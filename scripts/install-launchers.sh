#!/usr/bin/env sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -d "$HOME/.local/bin" "$HOME/.config/autostart"
install -m 755 "$root/open-entropycamp-page" "$HOME/.local/bin/open-entropycamp-page"
install -m 755 "$root/codex-reminder-cards" "$HOME/.local/bin/codex-reminder-cards"
install -m 644 "$root/entropycamp.desktop" "$HOME/.config/autostart/entropycamp.desktop"
