#!/usr/bin/env bash
# Temizci'yi kullanıcı dizinine kurar (root gerekmez).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
APP_DIR="$HOME/.local/share/applications"

mkdir -p "$BIN_DIR" "$ICON_DIR" "$APP_DIR"
chmod +x "$ROOT/temizci"

ln -sf "$ROOT/temizci" "$BIN_DIR/temizci"
cp "$ROOT/assets/temizci.svg" "$ICON_DIR/temizci.svg"

cat > "$APP_DIR/temizci.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Temizci
GenericName=Disk Temizleyici
Comment=Önbellekleri, eski yedekleri ve gereksiz dosyaları güvenle temizle
Exec=$ROOT/temizci gui
Icon=temizci
Terminal=false
Categories=System;Utility;Settings;
Keywords=disk;temizlik;cache;cleaner;storage;
StartupNotify=true
EOF

chmod +x "$APP_DIR/temizci.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true

echo "Temizci kuruldu."
echo "  Komut : temizci gui"
echo "  Menü  : Temizci"
echo "  Kaldır: rm -f \"$BIN_DIR/temizci\" \"$APP_DIR/temizci.desktop\" \"$ICON_DIR/temizci.svg\""
