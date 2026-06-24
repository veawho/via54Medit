# scoop-bucket/ — via54Medit scoop manifests

This directory contains the [scoop](https://scoop.sh) manifest(s) for
via54Medit, intended for use in the `veawho/scoop-bucket` repository.

## Install (for end users)

```powershell
# One-time setup
scoop bucket add veawho https://github.com/veawho/scoop-bucket
scoop install medit
```

## Update (for maintainers)

1. Tag a new release on GitHub: `git tag v0.1.0 && git push --tags`
2. GitHub Actions (or manual) runs `goreleaser release --clean`
3. This produces `medit-0.1.0-windows-amd64.zip` etc. under Releases
4. Open a PR to `veawho/scoop-bucket` with the updated `medit.json`:
   - Bump `version` field
   - Bump URLs in `autoupdate` block
   - Update SHA256 (scoop will verify on install)

## File list

- `medit.json` — Windows AMD64 manifest. The `64bit` block in `autoupdate`
  references the ZIP artifact published by goreleaser.

## Why scoop (not MSI / NSIS)?

Per ARCHITECTURE §19 (Phase 4.0 #5): no MSI/NSIS in Phase 4.0. scoop +
winget are the 2024+ standard for Windows CLI tools. MSI is a 2010-era
artifact that needs .NET Framework runtime.

## Verification

After tagging v0.1.0, install locally:

```powershell
scoop install https://raw.githubusercontent.com/veawho/scoop-bucket/main/medit.json
medit --version
```

Expected: `medit version via54Medit 0.1.0 (...)` with the SHA256
matching your `goreleaser` output.
