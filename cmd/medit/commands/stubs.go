package commands

import (
	"github.com/spf13/cobra"
)

// stubCmd is a helper to make Phase 0 stubs consistent.
func stubCmd(use, short, phase string) *cobra.Command {
	return &cobra.Command{
		Use:   use,
		Short: short,
		Run: func(cmd *cobra.Command, args []string) {
			cmd.Printf("[%s] %s — 将在 %s 实现\n",
				"Phase 0 stub", use, phase)
			cmd.Printf("详见 docs/ROADMAP.md\n")
		},
	}
}

// Phase 0 stubs removed — real impls in pubmed.go / antfu.go /
// openalex_s2.go / ask_search.go / pico_grade.go.
// (anno2ppt, enrich, index, query stay as Phase 2-3 placeholders.)

var enrichCmd = stubCmd(
	"enrich <refs.json>",
	"三方 enrich (PubMed+OpenAlex+S2)",
	"Phase 2",
)

var indexCmd = stubCmd(
	"index <file/dir>",
	"入 Qdrant + FTS5 知识库",
	"Phase 2",
)

var queryCmd = stubCmd(
	"query <query>",
	"检索本地知识库",
	"Phase 2",
)

var anno2pptCmd = stubCmd(
	"anno2ppt <package>",
	"证据包 → antfu 样式 PPT",
	"Phase 3",
)
