package lookup

import (
	"fmt"
	"testing"
)

// TestRadixTree_PutGet 算法测试: Put + Get 基本功能
func TestRadixTree_PutGet(t *testing.T) {
	tr := NewRadixTree(100)

	// 插入
	tr.Put("abc123def456", "Row 5 - NCCN HCC v2.2025")
	tr.Put("abc999fff", "Row 2 - GLOBOCAN 2022")

	// 查询
	v, ok := tr.Get("abc123def456")
	if !ok || v != "Row 5 - NCCN HCC v2.2025" {
		t.Errorf("Get(abc123def456) = (%q, %v), want ('Row 5...', true)", v, ok)
	}
	v, ok = tr.Get("abc999fff")
	if !ok || v != "Row 2 - GLOBOCAN 2022" {
		t.Errorf("Get(abc999fff) = (%q, %v), want ('Row 2...', true)", v, ok)
	}

	// 不存在
	_, ok = tr.Get("xyz000")
	if ok {
		t.Errorf("Get(xyz000) 应该返回 not found")
	}
}

// TestRadixTree_LRUEviction 算法测试: LRU 驱逐
func TestRadixTree_LRUEviction(t *testing.T) {
	tr := NewRadixTree(3) // cap = 3

	tr.Put("aaa", "1")
	tr.Put("bbb", "2")
	tr.Put("ccc", "3")
	// 此时 size = 3

	tr.Put("ddd", "4") // 触发驱逐
	if tr.Size() != 3 {
		t.Errorf("Size after eviction = %d, want 3", tr.Size())
	}

	// aaa 已被驱逐
	_, ok := tr.Get("aaa")
	if ok {
		t.Errorf("aaa 应该被驱逐")
	}

	// bbb, ccc, ddd 应该还在
	for _, k := range []string{"bbb", "ccc", "ddd"} {
		if _, ok := tr.Get(k); !ok {
			t.Errorf("%s 应该存在", k)
		}
	}
}

// TestRadixTree_Overwrite 算法测试: 覆盖已有 key
func TestRadixTree_Overwrite(t *testing.T) {
	tr := NewRadixTree(100)

	tr.Put("key1", "value1")
	tr.Put("key1", "value2") // 覆盖

	v, ok := tr.Get("key1")
	if !ok || v != "value2" {
		t.Errorf("After overwrite Get(key1) = (%q, %v), want ('value2', true)", v, ok)
	}
	if tr.Size() != 1 {
		t.Errorf("Size after overwrite = %d, want 1", tr.Size())
	}
}

// TestRadixTree_PrefixSharing 算法测试: radix tree 前缀共享 (SGLang 风格)
func TestRadixTree_PrefixSharing(t *testing.T) {
	tr := NewRadixTree(100)

	// 多个 MD5 共享前缀 (例如 1M PDF 都是 'a' 开头)
	tr.Put("abc123", "1")
	tr.Put("abc456", "2")
	tr.Put("abc789", "3")
	tr.Put("abd000", "4")
	tr.Put("xyz000", "5")

	if tr.Size() != 5 {
		t.Errorf("Size = %d, want 5", tr.Size())
	}

	// 全部能查到
	for i, k := range []string{"abc123", "abc456", "abc789", "abd000", "xyz000"} {
		v, ok := tr.Get(k)
		if !ok {
			t.Errorf("Get(%s) not found", k)
		}
		if v != fmt.Sprintf("%d", i+1) {
			t.Errorf("Get(%s) = %q, want %q", k, v, fmt.Sprintf("%d", i+1))
		}
	}
}

// TestRadixTree_Concurrent 算法测试: 并发读写
func TestRadixTree_Concurrent(t *testing.T) {
	tr := NewRadixTree(1000)

	// 100 个并发 Put
	done := make(chan bool, 100)
	for i := 0; i < 100; i++ {
		i := i
		go func() {
			md5 := fmt.Sprintf("md5_%03d", i)
			tr.Put(md5, fmt.Sprintf("value_%d", i))
			done <- true
		}()
	}
	for i := 0; i < 100; i++ {
		<-done
	}

	// 100 个并发 Get
	for i := 0; i < 100; i++ {
		i := i
		go func() {
			md5 := fmt.Sprintf("md5_%03d", i)
			v, ok := tr.Get(md5)
			expected := fmt.Sprintf("value_%d", i)
			if !ok || v != expected {
				t.Errorf("Get(%s) = (%q, %v), want (%q, true)", md5, v, ok, expected)
			}
			done <- true
		}()
	}
	for i := 0; i < 100; i++ {
		<-done
	}
}

// TestRadixTree_Stats 算法测试: Stats 输出
func TestRadixTree_Stats(t *testing.T) {
	tr := NewRadixTree(50)
	tr.Put("a", "1")
	tr.Put("b", "2")
	tr.Put("c", "3")

	s := tr.Stats()
	if s.Entries != 3 {
		t.Errorf("Stats.Entries = %d, want 3", s.Entries)
	}
	if s.MaxEntries != 50 {
		t.Errorf("Stats.MaxEntries = %d, want 50", s.MaxEntries)
	}
}
