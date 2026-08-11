// promptctl — Phase 4 prompt 编译器 CLI 测试
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "github.com/veawho/via54Medit/internal/prompt"
)

func main() {
    ctx := context.Background()
    c, err := prompt.NewCompiler("/Users/david/.medit/scripts/dspy_compile.py", "")
    if err != nil {
        fmt.Println("err:", err)
        return
    }

    trainset := []map[string]string{
        {"nl_input": "处理 P5-7", "intent": "process_row"},
        {"nl_input": "审计", "intent": "audit"},
        {"nl_input": "PMC{ID} 下 PDF", "intent": "pmc_pow_bypass"},
    }

    req := prompt.CompileRequest{
        Signature:    "nl_input -> intent",
        TrainSet:     trainset,
        MetricFunc:   "exact_match",
        Optimizer:    "BootstrapFewShot",
        MaxIterations: 10,
    }

    result, err := c.Compile(ctx, req)
    if err != nil {
        fmt.Println("compile err:", err)
        return
    }
    fmt.Printf("✓ Compiled, cache: %s\n", result.CachePath)
    fmt.Printf("  Duration: %dms, Score: %.2f\n", result.Stats.DurationMS, result.Stats.FinalScore)

    if err := result.SanityCheck(); err != nil {
        fmt.Println("sanity err:", err)
    } else {
        fmt.Println("✓ Sanity check passed")
    }

    loaded, err := c.Load("nl_input -> intent")
    if err != nil {
        fmt.Println("load err:", err)
    } else {
        fmt.Printf("✓ Loaded from cache: %s\n", loaded.CachePath)
    }

    out, _ := json.MarshalIndent(result.CompiledJSON, "", "  ")
    fmt.Println(string(out))
}
