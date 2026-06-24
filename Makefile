# Makefile for via54Medit
#
# Common targets:
#   make build           - build medit + medit-mcp for the current OS
#   make test            - run all tests with -race
#   make lint            - run go vet
#   make fmt             - gofmt -w
#   make clean           - remove build artifacts
#   make release-local   - cross-compile for all 5 platforms (no upload)
#
# Cross-compilation requires no CGO (we use pure Go for the most part).
# The bge-m3 embedding path (Phase 1.5) is pure Go HTTP, so it works
# everywhere. We use CGO=0 to make static binaries.
#
# Per ARCHITECTURE §9.2 / §19 (Phase 4.0 #5): zip artifacts for 5
# platforms, no MSI/NSIS (those are v0.5+).

GO        ?= go
VERSION   ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
COMMIT    ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILDDATE ?= $(shell date -u +%Y-%m-%dT%H:%M:%SZ)

# LDFLAGS: stamp version info into the binary.
LDFLAGS = -s -w \
          -X 'github.com/veawho/via54Medit/internal/version.Version=$(VERSION)' \
          -X 'github.com/veawho/via54Medit/internal/version.Commit=$(COMMIT)' \
          -X 'github.com/veawho/via54Medit/internal/version.BuildDate=$(BUILDDATE)' \
          -X 'github.com/veawho/via54Medit/internal/version.GoVersion=$(shell $(GO) version)'

# Platforms. We always CGO=0 for static binaries.
PLATFORMS = \
    windows-amd64 \
    darwin-amd64 \
    darwin-arm64 \
    linux-amd64 \
    linux-arm64

.PHONY: all build test lint fmt clean release-local help

all: build

help:
	@echo "via54Medit Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  build            - build medit + medit-mcp for the current OS"
	@echo "  test             - go test -race ./..."
	@echo "  lint             - go vet ./..."
	@echo "  fmt              - gofmt -w ."
	@echo "  clean            - remove build artifacts"
	@echo "  release-local    - cross-compile all 5 platforms into bin/release/"
	@echo ""
	@echo "Variables:"
	@echo "  VERSION=$(VERSION)  COMMIT=$(COMMIT)  BUILDDATE=$(BUILDDATE)"

build: bin/medit bin/medit-mcp

# Detect host OS for binary extension. On Windows (Git Bash / MSYS),
# medit and medit-mcp get a .exe suffix. On macOS/Linux, no suffix.
ifeq ($(OS),Windows_NT)
    MEDIT_BIN      := bin/medit.exe
    MEDIT_MCP_BIN  := bin/medit-mcp.exe
    MEDIT_PLAIN    := bin/medit
    MEDIT_MCP_PLAIN:= bin/medit-mcp
else
    MEDIT_BIN      := bin/medit
    MEDIT_MCP_BIN  := bin/medit-mcp
    MEDIT_PLAIN    := bin/medit
    MEDIT_MCP_PLAIN:= bin/medit-mcp
endif

# On Windows we still produce a no-suffix binary too (matching Unix
# convention) by copying. This way ./bin/medit works on both shells.
bin/medit: $(MEDIT_PLAIN)
	@true

bin/medit-mcp: $(MEDIT_MCP_PLAIN)
	@true

$(MEDIT_PLAIN):
	@mkdir -p bin
	CGO_ENABLED=0 $(GO) build -ldflags "$(LDFLAGS)" -o $@ ./cmd/medit

$(MEDIT_MCP_PLAIN):
	@mkdir -p bin
	CGO_ENABLED=0 $(GO) build -ldflags "$(LDFLAGS)" -o $@ ./cmd/medit-mcp

test:
	CGO_ENABLED=1 $(GO) test -race -timeout 90s ./...

lint:
	$(GO) vet ./...

fmt:
	$(GO)fmt -w .

clean:
	rm -rf bin/

# Cross-compile to 5 platforms. Output: bin/release/<platform>/medit(.exe)
release-local: clean
	@mkdir -p bin/release
	@for p in $(PLATFORMS); do \
	    mkdir -p bin/release/$$p; \
	    ext=""; \
	    if echo $$p | grep -q "^windows"; then ext=".exe"; fi; \
	    echo "==> building $$p"; \
	    CGO_ENABLED=0 GOOS=$$(echo $$p | cut -d- -f1) \
	                  GOARCH=$$(echo $$p | cut -d- -f2) \
	                  $(GO) build -ldflags "$(LDFLAGS)" \
	                  -o bin/release/$$p/medit$$ext ./cmd/medit; \
	    CGO_ENABLED=0 GOOS=$$(echo $$p | cut -d- -f1) \
	                  GOARCH=$$(echo $$p | cut -d- -f2) \
	                  $(GO) build -ldflags "$(LDFLAGS)" \
	                  -o bin/release/$$p/medit-mcp$$ext ./cmd/medit-mcp; \
	done
	@echo ""
	@echo "Release artifacts:"
	@ls -la bin/release/
	@echo ""
	@echo "Total size:"
	@du -sh bin/release/

# Convenience target: build the Windows .exe for local testing.
.PHONY: build-windows
build-windows:
	CGO_ENABLED=0 GOOS=windows GOARCH=amd64 \
	    $(GO) build -ldflags "$(LDFLAGS)" -o bin/medit.exe ./cmd/medit
	CGO_ENABLED=0 GOOS=windows GOARCH=amd64 \
	    $(GO) build -ldflags "$(LDFLAGS)" -o bin/medit-mcp.exe ./cmd/medit-mcp
