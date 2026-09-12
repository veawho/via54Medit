<div align="center">

# via54Medit

> **🌐 Language**: [🇨🇳 中文文档](./README.md) | [🇺🇸 English](#) (current)

[![CI](https://github.com/veawho/via54Medit/actions/workflows/ci.yml/badge.svg)](https://github.com/veawho/via54Medit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/veawho/via54Medit?include_prereleases&color=blue)](https://github.com/veawho/via54Medit/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE-AGPL-3.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE-MIT)

**Multi-Source Medical Literature Router, PICO Extractor, and Evidence Synthesis Engine for Evidence-Based Medicine (EBM)**

</div>

---

## 📌 Overview & Value Proposition

`via54Medit` is a multi-source scientific literature retrieval, semantic routing, and evidence synthesis engine built for clinical researchers, medical writers, and systematic review pipelines:

- **Natural Language Question Answering**: Concurrently queries 4 medical literature sources (Antfu Clinical RAG + PubMed + OpenAlex + Semantic Scholar).
- **Deduplication & Fusion**: SimHash Hamming distance deduplication with citation, recency, FWCI, and multi-source overlap ranking.
- **Cognitive Extraction & Grading**: LLM-driven PICO (Population, Intervention, Comparison, Outcome) element extraction and GRADE evidence quality assessment.
- **Dual-Source Architecture & Layout Fidelity**: L0–L6 6-layer verification architecture supporting journal paper and ClinicalTrials.gov (NCT) data complementarity, backed by native Microsoft Office rendering engines for PPT citation cards (`anno2ppt`).
- **Telemetry & Collaborative Sync**: Decoupled `medit-telemetry` module for tracking human efficiency, 100% exact LLM gateway token ledger accounting, and automated Feishu/Lark Bitable synchronization.

---

## 🚀 Cross-Platform Installation

Supported platforms: **Windows (amd64/arm64)**, **macOS (Apple Silicon & Intel)**, and **Linux (amd64/arm64)**. Pure Go static compilation (`CGO_ENABLED=0`) with zero dynamic library dependencies.

### Option A: Package Managers (Recommended)

#### Windows (Scoop)
```powershell
scoop bucket add veawho https://github.com/veawho/scoop-bucket
scoop install medit
```

#### macOS / Linux (Homebrew)
```bash
brew install veawho/tap/medit
```

### Option B: Pre-built Binaries
Download pre-compiled release archives (`.zip`, `.tar.gz`, `.deb`, `.rpm`, `.apk`) directly from [GitHub Releases](https://github.com/veawho/via54Medit/releases) and add the executable to your system `PATH`.

### Option C: Build from Source
```bash
git clone https://github.com/veawho/via54Medit.git
cd via54Medit

# Build static binaries (outputs to bin/medit and bin/medit-mcp)
make build
```

---

## 🛠️ Multi-Device Bootstrap & Self-Healing

For any newly provisioned workstation, server, or team machine:

```bash
# 1. Full device bootstrap: environment scan + dependency repair + render test + test suite
python3 scripts/bootstrap_device.py

# 2. Deep capability scan without modifying system (read-only)
python3 scripts/deploy_scan.py --check

# 3. Dry-run planned installation commands
python3 scripts/bootstrap_device.py --dry-run

# 4. Built-in Go health check
medit doctor
```

---

## 💻 Common CLI Commands

```bash
# Evidence-based literature search & synthesis
medit ask "First-line systemic therapy advances in hepatocellular carcinoma"
medit pico "Atezolizumab plus bevacizumab for unresectable HCC"
medit grade evidence_package.json
medit anno2ppt evidence_package.json

# Direct source search
medit pubmed search "Nivolumab HCC"
medit openalex search "Immunotherapy Hepatocellular"
medit s2 search "Atezolizumab Bevacizumab"
medit antfu search "Hepatocellular carcinoma systemic therapy"

# Medical planning & strategy
medit medplan run --instruction "Launch Medical Strategy" --name DrugX --indication "HCC"

# System doctor & version
medit doctor
medit version
```

---

## 🤖 AI Agent & MCP (Model Context Protocol) Integration

`via54Medit` includes a stdio MCP server (`bin/medit-mcp`) exposing 4 specialized tools:
* `medit_ask`: 4-source concurrent literature search and LLM summary
* `medit_pico`: Clinical PICO structured extraction
* `medit_grade`: GRADE evidence level rating
* `medit_anno2ppt`: Evidence package export to PowerPoint slides

### Claude Desktop / Cursor / Trae Configuration:

```json
{
  "mcpServers": {
    "medit": {
      "command": "medit-mcp",
      "args": []
    }
  }
}
```

---

## 📊 Telemetry & Lark/Feishu Automation (`medit-telemetry`)

Decoupled efficiency tracker and exact LLM token ledger accounting with 30-second proactive scanning and cloud dashboard synchronization:

* **Windows PowerShell Deployment**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Silent
  ```
* **Cross-Platform Python Deployment**:
  ```bash
  python telemetry/deploy.py --silent
  ```
* **Features**:
  * Precision time saved accounting (retrieval: 7 min/paper, download: 2 min/paper, highlight: 4 min/paper);
  * 100% exact token count aligned with provider billing invoices;
  * Background daemon with LaunchAgent (macOS) and Startup VBS (Windows);
  * Holiday deferral and pre-warning notifications.

For complete options and guides, see [docs/TELEMETRY_DEPLOY.md](docs/TELEMETRY_DEPLOY.md).

---

## 🧪 Testing

```bash
make test        # Run Go race detector tests (go test -race)
make test-py     # Run Python test suites (telemetry, repo hygiene, LLM ledger, forbidden zones)
```

---

## 📄 License & Community Standards

- **Dual Licensing**:
  - Core Codebase: [AGPL-3.0 License](LICENSE-AGPL-3.0)
  - Templates, Configs, and Documentation: [MIT License](LICENSE-MIT)
- **Code of Conduct**: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- **Contribution Guide**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Security Policy**: [SECURITY.md](SECURITY.md)
- **Citation**: [CITATION.cff](CITATION.cff)
