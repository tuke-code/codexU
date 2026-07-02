#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-0.1.0}"
PACKAGE="codexu-ubuntu"
BUILD_ROOT="$ROOT/dist/${PACKAGE}_${VERSION}_all"
DEBIAN_DIR="$BUILD_ROOT/DEBIAN"

rm -rf "$ROOT/dist"
install -d "$DEBIAN_DIR"
install -d "$BUILD_ROOT/usr/bin"
install -d "$BUILD_ROOT/usr/lib/codexu-ubuntu"
install -d "$BUILD_ROOT/usr/share/applications"
install -d "$BUILD_ROOT/usr/share/icons/hicolor/scalable/apps"
install -d "$BUILD_ROOT/usr/share/doc/$PACKAGE"

cp -a "$ROOT/codexu_ubuntu" "$BUILD_ROOT/usr/lib/codexu-ubuntu/"
install -m 0644 "$ROOT/packaging/codexu-ubuntu.desktop" "$BUILD_ROOT/usr/share/applications/codexu-ubuntu.desktop"
install -m 0644 "$ROOT/assets/codexu.svg" "$BUILD_ROOT/usr/share/icons/hicolor/scalable/apps/codexu.svg"
install -m 0644 "$ROOT/README.md" "$BUILD_ROOT/usr/share/doc/$PACKAGE/README.md"

cat >"$BUILD_ROOT/usr/bin/codexu-ubuntu" <<'EOF'
#!/usr/bin/env bash
export PYTHONPATH="/usr/lib/codexu-ubuntu${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m codexu_ubuntu "$@"
EOF
chmod 0755 "$BUILD_ROOT/usr/bin/codexu-ubuntu"

cat >"$DEBIAN_DIR/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: codexU Maintainers <maintainers@example.invalid>
Depends: python3, python3-gi, gir1.2-gtk-4.0
Description: Native Ubuntu desktop widget for Codex usage
 codexU Ubuntu is a native GTK4/PyGObject desktop widget that reads local
 Codex usage data, quota data, token metrics, and task board information.
EOF

dpkg-deb --build "$BUILD_ROOT" "$ROOT/dist/${PACKAGE}_${VERSION}_all.deb"
