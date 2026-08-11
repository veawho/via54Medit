#!/usr/bin/env bash
# scripts/release.sh - local cross-platform release builder.
#
# Builds 5 platform archives (medit + medit-mcp + configs + LICENSE) into
# dist/, then prints a summary. No upload — push to GitHub manually or
# let goreleaser handle that.
#
# Usage:
#   bash scripts/release.sh           # build with current version
#   VERSION=v0.1.0 bash scripts/release.sh
#
# Output: dist/<version>/<platform>/medit.{zip,tar.gz}
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION=${VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo "dev")}
PLATFORMS=("windows-amd64" "darwin-amd64" "darwin-arm64" "linux-amd64" "linux-arm64")

DIST_DIR="$ROOT/dist/${VERSION}"
mkdir -p "$DIST_DIR"
echo "==> Building via54Medit ${VERSION}"
echo ""

# Build all platforms in parallel for speed.
for p in "${PLATFORMS[@]}"; do
    (
        os=$(echo "$p" | cut -d- -f1)
        arch=$(echo "$p" | cut -d- -f2)
        ext=""
        if [ "$os" = "windows" ]; then
            ext=".exe"
        fi

        OUTDIR="$DIST_DIR/${p}"
        mkdir -p "$OUTDIR"

        echo "  [${p}] building..."
        CGO_ENABLED=0 GOOS=${os} GOARCH=${arch} \
            go build -ldflags "-s -w \
                -X 'github.com/veawho/via54Medit/internal/version.Version=${VERSION}' \
                -X 'github.com/veawho/via54Medit/internal/version.Commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)'" \
            -o "${OUTDIR}/medit${ext}" ./cmd/medit

        CGO_ENABLED=0 GOOS=${os} GOARCH=${arch} \
            go build -ldflags "-s -w" \
            -o "${OUTDIR}/medit-mcp${ext}" ./cmd/medit-mcp

        # Copy shared assets.
        cp -r "$ROOT/configs" "$OUTDIR/" 2>/dev/null || true
        cp "$ROOT/LICENSE-AGPL-3.0" "$OUTDIR/" 2>/dev/null || true
        cp "$ROOT/LICENSE-MIT" "$OUTDIR/" 2>/dev/null || true
        cp "$ROOT/README.md" "$OUTDIR/" 2>/dev/null || true
        cp "$ROOT/README.zh-CN.md" "$OUTDIR/" 2>/dev/null || true

        # Pack from the dist directory.
        cd "$DIST_DIR"
        archive="medit-${VERSION}-${p}"
        if [ "$os" = "windows" ]; then
            if command -v zip > /dev/null 2>&1; then
                zip -qr "${archive}.zip" "${p}"
            else
                echo "    [warn] 'zip' not found; skipping ${p}.zip"
            fi
        else
            tar -czf "${archive}.tar.gz" "${p}"
        fi

        # Compute sha256.
        if [ -f "${archive}.zip" ]; then
            shasum -a 256 "${archive}.zip" > "${archive}.zip.sha256"
        fi
        if [ -f "${archive}.tar.gz" ]; then
            shasum -a 256 "${archive}.tar.gz" > "${archive}.tar.gz.sha256"
        fi

        echo "    ✓ ${archive}.{zip,tar.gz}"
    ) &
done
wait

echo ""
echo "==> Release artifacts:"
ls -la "$DIST_DIR/"
echo ""
echo "==> Total:"
du -sh "$DIST_DIR/"
echo ""
echo "Next: upload to GitHub Releases or push to scoop bucket."
