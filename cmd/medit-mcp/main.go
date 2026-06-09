// Command medit-mcp is the via54Medit MCP Server entry point.
//
// It exposes 4 tools to MCP clients (Claude Desktop, Cursor, VS Code Copilot, etc.):
//
//   - medit_ask      : 一句话循证检索
//   - medit_pico     : PICO 抽取
//   - medit_grade    : GRADE 评级
//   - medit_anno2ppt : 证据包 → PPT
//
// Phase 0: server is a stub that lists the 4 tools but returns "not implemented".
// Phase 4: full MCP transport via modelcontextprotocol/go-sdk.
package main

import (
	"fmt"
	"os"
)

func main() {
	fmt.Fprintln(os.Stderr, "medit-mcp: Phase 0 stub — 将在 Phase 4 实现完整 MCP transport")
	fmt.Fprintln(os.Stderr, "预期工具: medit_ask / medit_pico / medit_grade / medit_anno2ppt")
	os.Exit(0)
}
