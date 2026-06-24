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

cd "$(dirname "$0")/.."

VERSION=${VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo "dev")}
PLATFORMS=("windows-amd64" "darwin-amd64" "darwin-arm64" "linux-amd64" "linux-arm64")

mkdir -p dist/${VERSION}
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

        outdir="dist/${VERSION}/${p}"
        mkdir -p "${outdir}"

        echo "  [${p}] building..."
        CGO_ENABLED=0 GOOS=${os} GOARCH=${arch} \
            go build -ldflags "-s -w \
                -X 'github.com/veawho/via54Medit/internal/version.Version=${VERSION}' \
                -X 'github.com/veawho/via54Medit/internal/version.Commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)'" \
            -o "${outdir}/medit${ext}" ./cmd/medit

        CGO_ENABLED=0 GOOS=${os} GOARCH=${arch} \
            go build -ldflags "-s -w" \
            -o "${outdir}/medit-mcp${ext}" ./cmd/medit-mcp

        # Copy shared assets.
        cp -r configs "${outdir}/" 2>/dev/null || true
        cp LICENSE-AGPL-3.0 "${outdir}/" 2>/dev/null || true
        cp LICENSE-MIT "${outdir}/" 2>/dev/null || true
        cp README.md "${outdir}/" 2>/dev/null || true
        cp README.zh-CN.md "${outdir}/" 2>/dev/null || true

        # Pack.
        cd "${outdir}/.."
        archive="medit-${VERSION}-${p}"
        if [ "$os" = "windows" ]; then
            # zip needs PowerShell on Windows or zip on Unix.
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
            sha256sum "${archive}.zip" > "${archive}.zip.sha256"
        fi
        if [ -f "${archive}.tar.gz" ]; then
            sha256sum "${archive}.tar.gz" > "${archive}.tar.gz.sha256"
        fi

        echo "    ✓ ${archive}.{zip,tar.gz}"
    ) &
done
wait

echo ""
echo "==> Release artifacts:"
ls -la dist/${VERSION}/
echo ""
echo "==> Total:"
du -sh dist/${VERSION}/
echo ""
echo "Next: upload to GitHub Releases or push to scoop bucket."
