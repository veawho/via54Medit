# Contributing to via54Medit

Thank you for your interest in contributing to via54Medit! We welcome contributions, bug reports, feature suggestions, and pull requests from the community.

## Code of Conduct

Please note that this project is released with a [Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project, you agree to abide by its terms.

## Getting Started

### Prerequisites

- **Go**: 1.22+ (recommended 1.24+ or 1.26+)
- **Python**: 3.10+ (recommended 3.11+)
- **Node.js**: 18+ (for mmx-cli / lark-cli integration, optional for core EBM router)
- **Git**: 2.30+

### Setting Up Your Local Environment

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/<your-username>/via54Medit.git
   cd via54Medit
   ```

2. Build local binaries:
   ```bash
   make build
   ```

3. Install Python toolchain dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run local deployment / capability verification:
   ```bash
   python3 scripts/deploy_scan.py --check
   ```

## Development & Testing Workflow

Before opening a pull request, ensure all tests pass locally:

```bash
# 1. Run Go race tests and linter
make test
make lint

# 2. Run Python test suites (telemetry, repo hygiene, LLM ledger, forbidden zones)
make test-py

# 3. Verify cross-platform deployment scanner and import invariants
python3 scripts/deploy_scan.py --dry-run
```

## Cross-Platform & Multi-Device Guidelines

To ensure via54Medit runs reliably across Windows, macOS, and Linux:

- **No Hardcoded Machine Paths**: Never hardcode developer home paths (e.g. `/Users/username/`, `C:\Users\username\`) or POSIX-only temporary directories (`/tmp/`). Always use:
  - `os.path.expanduser("~")` or `pathlib.Path.home()`
  - `tempfile.gettempdir()` for temporary files
  - Derived environment variables (`$VIA54_HOME`, `$MEDIT_HOME`, etc.)
- **Safe Path Joins**: Use `pathlib.Path` or `os.path.join()`.
- **Platform Capability Isolation**: Platform-specific logic (e.g. Windows COM / pywin32, macOS AppleScript) must be protected with platform guards and documented in `scripts/deploy_scan.py`.
- **Line Endings**: Repository line endings are normalized via `.gitattributes`. Always preserve LF for `.sh` and Makefile, and CRLF for `.bat` and `.ps1`.

## Submitting Pull Requests

1. Create a feature or fix branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Commit your changes with clear, descriptive commit messages following [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add new literature provider`
   - `fix: resolve file descriptor leak in telemetry daemon`
   - `docs: update cross-platform installation steps`
3. Push to your fork and submit a Pull Request against `main`.
4. Fill in the PR template (`.github/PULL_REQUEST_TEMPLATE.md`) with context, changes made, and verification steps.

## Licensing

By contributing to via54Medit, you agree that your contributions will be licensed under the project's dual license:
- AGPL-3.0 for core codebase
- MIT for configs, templates, and documentation
