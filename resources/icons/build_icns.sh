#!/bin/bash
# Converts resources/icons/app_icon.png (see generate_app_icon.py) into
# resources/icons/AppIcon.icns, the format macOS app bundles need. Uses
# sips/iconutil, both built into macOS -- no extra dependency for a step
# that only ever needs to run on a macOS dev machine anyway (packaging
# is macOS-only for now).
set -euo pipefail

cd "$(dirname "$0")"

SOURCE_PNG="app_icon.png"
ICONSET_DIR="AppIcon.iconset"
OUTPUT_ICNS="AppIcon.icns"

if [ ! -f "$SOURCE_PNG" ]; then
    echo "error: $SOURCE_PNG not found -- run generate_app_icon.py first" >&2
    exit 1
fi

rm -rf "$ICONSET_DIR"
mkdir "$ICONSET_DIR"

# Each size needs both a 1x and a 2x (Retina) rendition, per Apple's iconset
# naming convention; iconutil refuses to build an .icns from a directory
# missing this exact naming/size set.
declare -a sizes=(16 32 128 256 512)
for size in "${sizes[@]}"; do
    sips -z "$size" "$size" "$SOURCE_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$SOURCE_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$ICONSET_DIR" -o "$OUTPUT_ICNS"
rm -rf "$ICONSET_DIR"

echo "Wrote $(dirname "$0")/$OUTPUT_ICNS"
