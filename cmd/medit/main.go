// Command medit is the via54Medit CLI entry point.
//
// [CN] via54Medit 命令行工具入口。
// [EN] Command-line interface entry point for via54Medit.
//
// Usage:
//
//	medit [global flags] <subcommand> [args]
//
// Global flags:
//
//	--config string         Config file (default ~/.medit/config.yaml)
//	--embedder string       Embedder backend (default bge-m3)
//	--vectorstore string    Vector store backend (default qdrant)
//	--provider string       LLM provider (default hermes)
//	--lang string           Language: zh/en/auto (default auto)
//	-v, --verbose           Verbose logging
//	--no-color              Disable ANSI colors
//
// Subcommands: see root.go.
package main

import (
	"fmt"
	"os"

	"github.com/veawho/via54Medit/cmd/medit/commands"
)

func main() {
	if err := commands.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}
