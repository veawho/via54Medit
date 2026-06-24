// Logger is the contract every foundation / source / router package uses.
//
// All methods are safe for concurrent use. Implementations:
//   - defaultLogger wraps slog.Logger
//   - noopLogger discards everything (use in tests and library mode)
package foundation

import (
	"context"
	"io"
	"log/slog"
	"os"
	"sync"
)

type Logger interface {
	// Debug logs a debug message with optional key/value pairs.
	// Keys are strings; values may be any type slog accepts.
	Debug(msg string, args ...any)

	// Info logs an informational message.
	Info(msg string, args ...any)

	// Warn logs a warning.
	Warn(msg string, args ...any)

	// Error logs an error.
	Error(msg string, args ...any)

	// With returns a child logger with the given key/value pairs
	// pre-attached to every log line. Useful for adding conv_id, source, etc.
	With(args ...any) Logger
}

// --- defaultLogger (slog-backed) ---

type defaultLogger struct {
	l *slog.Logger
}

// New returns a JSON Logger writing to stderr at the given level.
//
// Recognized levels: "debug" | "info" | "warn" | "error" (case-insensitive).
// Unknown level falls back to Info.
//
// Example:
//
//	lg := NewLogger("info")
//	lg.Info("ask started", "conv_id", "abc123", "query_len", 42)
func NewLogger(level string) Logger {
	return NewLoggerWith(os.Stderr, level)
}

// NewLoggerWith is NewLogger but writes to the given io.Writer (mainly for tests).
func NewLoggerWith(w io.Writer, level string) Logger {
	lvl := parseLevel(level)
	h := slog.NewJSONHandler(w, &slog.HandlerOptions{
		Level:     lvl,
		AddSource: false, // source paths are noise in audit JSON
	})
	return &defaultLogger{l: slog.New(h)}
}

func parseLevel(s string) slog.Level {
	switch toLower(s) {
	case "debug":
		return slog.LevelDebug
	case "warn", "warning":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}

func toLower(s string) string {
	// avoid strings.ToLower allocation for the common single-word cases
	if len(s) == 0 {
		return s
	}
	b := make([]byte, len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c >= 'A' && c <= 'Z' {
			c += 'a' - 'A'
		}
		b[i] = c
	}
	return string(b)
}

func (d *defaultLogger) Debug(msg string, args ...any) { d.l.Debug(msg, args...) }
func (d *defaultLogger) Info(msg string, args ...any)  { d.l.Info(msg, args...) }
func (d *defaultLogger) Warn(msg string, args ...any)  { d.l.Warn(msg, args...) }
func (d *defaultLogger) Error(msg string, args ...any) { d.l.Error(msg, args...) }

func (d *defaultLogger) With(args ...any) Logger {
	return &defaultLogger{l: d.l.With(args...)}
}

// --- noopLogger (zero-cost for tests) ---

type noopLogger struct{}

// NoopLogger returns a Logger that discards everything. Use in tests and
// library mode where the host application provides its own logger.
func NoopLogger() Logger { return noopLogger{} }

func (noopLogger) Debug(string, ...any) {}
func (noopLogger) Info(string, ...any)  {}
func (noopLogger) Warn(string, ...any)  {}
func (noopLogger) Error(string, ...any) {}
func (noopLogger) With(...any) Logger   { return noopLogger{} }

// --- Default singleton (used by packages that don't take a Logger arg) ---

var (
	defaultMu sync.RWMutex
	default_  Logger = NewLogger("info")
)

// SetDefaultLogger replaces the process-wide default logger. Call from main()
// before any goroutines start. Returns the previous default for restore.
func SetDefaultLogger(l Logger) Logger {
	defaultMu.Lock()
	defer defaultMu.Unlock()
	old := default_
	default_ = l
	return old
}

// DefaultLogger returns the process-wide default logger. Safe for concurrent use.
// Equivalent to slog.Default() but typed as our interface.
func DefaultLogger() Logger {
	defaultMu.RLock()
	defer defaultMu.RUnlock()
	return default_
}

// --- Context helpers (for conv_id propagation) ---

type ctxKey struct{}

// WithConvID returns a context carrying a conv_id that Default will
// attach to every log line. Use in router / source to trace a question
// across the 4 parallel sources.
func WithConvID(ctx context.Context, convID string) context.Context {
	return context.WithValue(ctx, ctxKey{}, convID)
}

// ConvIDFrom extracts the conv_id, or "" if absent.
func ConvIDFrom(ctx context.Context) string {
	if v, ok := ctx.Value(ctxKey{}).(string); ok {
		return v
	}
	return ""
}
