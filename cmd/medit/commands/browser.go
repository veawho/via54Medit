// Package commands — browser subcommand (跨平台 Chrome 自动接入).
//
// medit browser start|health — 新设备部署入口: 自动探测本机
// Chrome/Edge/Chromium, 以独立 profile 启动带 --remote-debugging-port
// 的调试实例 (不干扰日常浏览器), 供 antfu / fulltext Tier2 使用。
package commands

import (
	"context"
	"fmt"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/source"
)

// DefaultCDPPort is the standard DevTools port used repo-wide.
const DefaultCDPPort = 9223

var browserCmd = &cobra.Command{
	Use:   "browser",
	Short: "跨平台 Chrome 自动接入 (探测/启动调试实例/健康检查)",
	Long: `browser 让 CDP 依赖功能 (antfu, fulltext Tier2) 摆脱手动启动 Chrome:
自动探测本机 Chrome/Edge/Chromium, 以独立 profile 启动
--remote-debugging-port 调试实例 (不影响日常浏览器会话)。

  medit browser start    探测并启动调试实例 (已运行则跳过)
  medit browser health   检查 CDP 端口可达性
  medit browser stop     关闭调试实例 (按 profile 目录)`,
}

var browserPort int

func init() {
	browserCmd.AddCommand(browserStartCmd)
	browserCmd.AddCommand(browserHealthCmd)
	browserCmd.AddCommand(browserStopCmd)
	browserCmd.PersistentFlags().IntVar(&browserPort, "port", DefaultCDPPort, "DevTools 调试端口")
}

var browserStartCmd = &cobra.Command{
	Use:   "start",
	Short: "探测并启动 Chrome 调试实例",
	Args:  cobra.NoArgs,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cdp := fmt.Sprintf("http://127.0.0.1:%d", browserPort)
		ctx, cancel := context.WithTimeout(cmd.Context(), 30*time.Second)
		defer cancel()
		chrome, err := source.EnsureChromeCDP(ctx, cdp, browserPort)
		if err != nil {
			return err
		}
		out := cmd.OutOrStdout()
		if chrome == "" {
			fmt.Fprintf(out, "CDP 已就绪: %s (已有实例运行)\n", cdp)
		} else {
			fmt.Fprintf(out, "已启动调试实例: %s\n", chrome)
			fmt.Fprintf(out, "CDP 就绪: %s | profile: %s\n", cdp, source.DebugProfileDir(browserPort))
		}
		return nil
	},
}

var browserHealthCmd = &cobra.Command{
	Use:   "health",
	Short: "检查 CDP 端口可达性",
	Args:  cobra.NoArgs,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cdp := fmt.Sprintf("http://127.0.0.1:%d", browserPort)
		ctx, cancel := context.WithTimeout(cmd.Context(), 5*time.Second)
		defer cancel()
		if err := source.ChromeHealth(ctx, cdp); err != nil {
			return fmt.Errorf("CDP %s 不可达: %w (运行 `medit browser start` 自动启动)", cdp, err)
		}
		fmt.Fprintf(cmd.OutOrStdout(), "CDP 就绪: %s\n", cdp)
		return nil
	},
}

var browserStopCmd = &cobra.Command{
	Use:   "stop",
	Short: "关闭调试实例 (按 profile 目录匹配进程)",
	Args:  cobra.NoArgs,
	RunE: func(cmd *cobra.Command, _ []string) error {
		profile := source.DebugProfileDir(browserPort)
		killed, err := stopChromeByProfile(profile)
		if err != nil {
			return err
		}
		if killed == 0 {
			fmt.Fprintln(cmd.OutOrStdout(), "未发现运行中的调试实例")
			return nil
		}
		fmt.Fprintf(cmd.OutOrStdout(), "已关闭 %d 个调试实例进程 (profile: %s)\n", killed, profile)
		return nil
	},
}

// stopChromeByProfile terminates processes whose command line contains
// the debug profile dir. Cross-platform: pgrep/pkill on unix, wmic on
// Windows (best effort; returns count).
func stopChromeByProfile(profile string) (int, error) {
	switch runtime.GOOS {
	case "windows":
		out, err := exec.Command("wmic", "process", "where", "name='chrome.exe'", "get", "ProcessId,CommandLine").Output()
		if err != nil {
			return 0, nil
		}
		killed := 0
		for _, line := range strings.Split(string(out), "\n") {
			if strings.Contains(line, profile) {
				fields := strings.Fields(line)
				if len(fields) > 0 {
					_ = exec.Command("taskkill", "/F", "/PID", fields[len(fields)-1]).Run()
					killed++
				}
			}
		}
		return killed, nil
	default:
		out, err := exec.Command("pgrep", "-f", profile).Output()
		if err != nil {
			return 0, nil // none found
		}
		killed := 0
		for _, pid := range strings.Fields(string(out)) {
			if pid != "" {
				_ = exec.Command("kill", pid).Run()
				killed++
			}
		}
		return killed, nil
	}
}
