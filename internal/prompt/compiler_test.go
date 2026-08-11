package prompt

import (
	"context"
	"os"
	"testing"
)

// TestCompiler_NewCompiler 算法测试: 创建 + 错误处理
func TestCompiler_NewCompiler(t *testing.T) {
	_, err := NewCompiler("", "")
	if err == nil {
		t.Errorf("NewCompiler 空 script 应该报错")
	}

	// 用真 script
	c, err := NewCompiler("/Users/david/.medit/scripts/dspy_compile.py", "")
	if err != nil {
		t.Errorf("NewCompiler 应该成功, got %v", err)
	}
	if c.scriptPath == "" {
		t.Errorf("Compiler.scriptPath 应该非空")
	}
}

// TestCompiler_Compile 算法测试: 编译 + cache
func TestCompiler_Compile(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "compiler_test")
	defer os.RemoveAll(tmpDir)

	c, err := NewCompiler("/Users/david/.medit/scripts/dspy_compile.py", tmpDir)
	if err != nil {
		t.Fatalf("NewCompiler: %v", err)
	}

	req := CompileRequest{
		Signature:    "test_sig -> intent",
		TrainSet:     []map[string]string{{"nl_input": "test", "intent": "test"}},
		MetricFunc:   "exact_match",
		Optimizer:    "BootstrapFewShot",
		MaxIterations: 1,
	}

	result, err := c.Compile(context.Background(), req)
	if err != nil {
		t.Fatalf("Compile: %v", err)
	}

	if result.CachePath == "" {
		t.Errorf("result.CachePath 应该非空")
	}
	if result.Stats.DurationMS < 0 {
		t.Errorf("Stats.DurationMS 应该 ≥ 0")
	}
}

// TestCompiler_CacheHit 算法测试: 同一 signature 第二次走 cache
func TestCompiler_CacheHit(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "compiler_cache_test")
	defer os.RemoveAll(tmpDir)

	c, err := NewCompiler("/Users/david/.medit/scripts/dspy_compile.py", tmpDir)
	if err != nil {
		t.Fatalf("NewCompiler: %v", err)
	}

	sig := "cache_test_sig -> intent"
	req := CompileRequest{
		Signature:    sig,
		TrainSet:     []map[string]string{{"nl_input": "x", "intent": "y"}},
		MetricFunc:   "exact_match",
		Optimizer:    "BootstrapFewShot",
		MaxIterations: 1,
	}

	// 第一次: 编译
	first, err := c.Compile(context.Background(), req)
	if err != nil {
		t.Fatalf("Compile 1st: %v", err)
	}

	// 第二次: 应该走 cache
	second, err := c.Compile(context.Background(), req)
	if err != nil {
		t.Fatalf("Compile 2nd: %v", err)
	}

	if first.CachePath != second.CachePath {
		t.Errorf("Cache 命中路径应该一致: %s vs %s", first.CachePath, second.CachePath)
	}
}

// TestCompiler_Load 算法测试: 从 cache 加载
func TestCompiler_Load(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "compiler_load_test")
	defer os.RemoveAll(tmpDir)

	c, err := NewCompiler("/Users/david/.medit/scripts/dspy_compile.py", tmpDir)
	if err != nil {
		t.Fatalf("NewCompiler: %v", err)
	}

	// 不存在的 signature
	_, err = c.Load("nonexistent_signature_xyz")
	if err == nil {
		t.Errorf("Load 不存在的 signature 应该报错")
	}

	// 先 Compile 再 Load
	sig := "load_test_sig"
	req := CompileRequest{
		Signature:    sig,
		TrainSet:     []map[string]string{{"a": "b"}},
		MetricFunc:   "exact_match",
		Optimizer:    "BootstrapFewShot",
		MaxIterations: 1,
	}
	_, _ = c.Compile(context.Background(), req)

	loaded, err := c.Load(sig)
	if err != nil {
		t.Fatalf("Load 应该成功: %v", err)
	}
	if loaded == nil {
		t.Errorf("Load 结果应该非 nil")
	}
}

// TestCompileResult_SanityCheck 算法测试: 完整性检查
func TestCompileResult_SanityCheck(t *testing.T) {
	// nil
	var r *CompileResult
	if err := r.SanityCheck(); err == nil {
		t.Errorf("nil CompileResult SanityCheck 应该报错")
	}

	// 空 compiled_json
	r = &CompileResult{}
	if err := r.SanityCheck(); err == nil {
		t.Errorf("空 compiled_json 应该报错")
	}

	// 缺 signature
	rawJSON := []byte(`{"no_signature": true}`)
	r = &CompileResult{CompiledJSON: rawJSON}
	if err := r.SanityCheck(); err == nil {
		t.Errorf("缺 signature 应该报错")
	}

	// 完整
	rawJSON = []byte(`{"signature": "valid", "method": "test"}`)
	r = &CompileResult{CompiledJSON: rawJSON}
	if err := r.SanityCheck(); err != nil {
		t.Errorf("完整 CompileResult SanityCheck 应该通过, got %v", err)
	}
}

// TestHashSignature 算法测试: signature hash 行为
func TestHashSignature(t *testing.T) {
	// 短 sig 直接返回
	h1 := hashSignature("test")
	if h1 != "test" {
		t.Errorf("hashSignature(test) = %q, want %q", h1, "test")
	}

	// 长 sig 截断
	longSig := string(make([]byte, 100))
	for i := range longSig {
		longSig = longSig[:i] + "a" + longSig[i+1:]
	}
	h2 := hashSignature(longSig)
	if len(h2) > 32 {
		t.Errorf("hashSignature 应截断到 ≤32 chars, got %d", len(h2))
	}
}

// TestLoadCorrectionsAsTrainset 算法测试: 读 corrections 当 trainset
func TestLoadCorrectionsAsTrainset(t *testing.T) {
	trainset := loadCorrectionsAsTrainset()
	// 不管 corrections 表空不空, 都应该返回 slice
	if trainset == nil {
		t.Errorf("loadCorrectionsAsTrainset 应该返回空 slice 而非 nil")
	}
}

// TestCompiler_FilePath 算法测试: 路径处理
func TestCompiler_FilePath(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "compiler_path_test")
	defer os.RemoveAll(tmpDir)

	c, _ := NewCompiler("/Users/david/.medit/scripts/dspy_compile.py", tmpDir)
	// 算法: CachePath 是 Compile 结果, 不是 Compiler 字段
	// 这里只验证 cacheDir 创建成功
	if c.cacheDir != tmpDir {
		t.Errorf("Compiler.cacheDir = %q, want %q", c.cacheDir, tmpDir)
	}
}
