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

// 13 subcommands — all Phase 0 stubs

var askCmd = stubCmd(
	"ask <query>",
	"一句话循证检索 (4 源并发 + 融合 + 摘要)",
	"Phase 2",
)

var searchCmd = stubCmd(
	"search <query>",
	"原始多源检索 (无 LLM 摘要)",
	"Phase 2",
)

var picoCmd = stubCmd(
	"pico <query>",
	"从自然语言抽取 PICO 四要素",
	"Phase 3",
)

var systematicCmd = stubCmd(
	"systematic <query>",
	"系统综述 (PRISMA 流程)",
	"Phase 3",
)

var gradeCmd = stubCmd(
	"grade <package>",
	"GRADE 证据评级",
	"Phase 3",
)

var pubmedCmd = stubCmd(
	"pubmed <subcmd>",
	"直查 PubMed (search/fetch/efetch)",
	"Phase 1",
)

var openalexCmd = stubCmd(
	"openalex <subcmd>",
	"直查 OpenAlex (works/authors/concepts)",
	"Phase 2",
)

var s2Cmd = stubCmd(
	"s2 <subcmd>",
	"直查 Semantic Scholar (paper/search/tldr)",
	"Phase 2",
)

var antfuCmd = stubCmd(
	"antfu <subcmd>",
	"蚂蚁阿福 (ask/screenshot/extract/chat-list)",
	"Phase 1",
)

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
