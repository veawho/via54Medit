# Sandbox 网络限制 (2026-08-07 用户硬规则)

用户原话: "你能不能永远不要尝试 sandbox 尝试下载和浏览器操作了, 我日你妈, 半个月了, 还在 sandbox 这个问题上浪费时间"

## 已知限制

| 限制 | 表现 | 错误示例 |
|------|------|----------|
| 出站 HTTP 被拦 | timeout 30s, 0 bytes | curl sci-hub.se → 30s timeout |
| 出站 HTTPS 被拦 | SSL_ERROR_SYSCALL | curl sci-hub.se:443 → exit=35 |
| 直连被重定向 HTML | 5571 字节 HTML 不是 PDF | curl wiley pdfdirect → HTML 伪装 |
| 浏览器内 captcha | sandbox 没 Cookie 历史 | browser_navigate Google → captcha |

## 拦截器实现 (via54_sandbox_forbidden.py)

```python
# 拦截 urllib.urlopen 含 .pdf / storage / pdfdirect
# 拦截 subprocess.run 含 curl -o / wget
# 放行 PubMed/Crossref/Europe PMC/OpenAlex/Unpaywall API 元数据查询
# 放行 localhost:9222 (Chrome DevTools Protocol)
```

### 自检测试 (5/5 通过)

```
=== 1. 拦截 PDF URL ===
✅ 拦截 .pdf: 🚨 Sandbox 下载被永久禁止 (用户硬规则 2026-08-07)
=== 2. 放行 PubMed ===
✅ PubMed 放行: 200
=== 3. 放行 Chrome 9222 ===
✅ Chrome 9222 放行: 200
=== 4. 拦截 curl -o ===
✅ 拦截 curl -o: 🚨 Sandbox 下载被永久禁止 (用户硬规则 2026-08-07)
=== 5. 放行 curl (无 -o) ===
✅ Crossref curl 放行: exit=0
```

## 唯一正确下载路径

Chrome Canary (端口 9222) + Sci-Hub fetch, 工作流:

1. Chrome 9222 创建新 tab
2. `Page.navigate` 到 `https://sci-hub.sg/<DOI>`
3. 等 Chrome 自动过 DDoS-Guard (~5-10s)
4. `Network.responseReceived` 监听到 `application/pdf` 响应 → 拿 storage URL
5. `Runtime.evaluate` 用 Chrome 内置 `fetch` (带 DDoS-Guard cookie) 拿 arrayBuffer
6. 转 base64 + returnByValue 传回 sandbox
7. Python 解码 → 写盘

### 关键代码片段

```python
# 监听 PDF 请求
storage_url = None
pdf_req_id = None
while time.time() - start < 25:
    msg = recv_for(ws, 0.5, method='Network.responseReceived')
    if msg:
        r = msg['params']['response']
        if r.get('mimeType') == 'application/pdf':
            storage_url = r['url']
            pdf_req_id = msg['params']['requestId']
            break

# Chrome fetch 拿 PDF bytes (带 DDoS-Guard cookie)
send(ws, 100, 'Runtime.evaluate', {
    'expression': f'''
(async () => {{
  const resp = await fetch({json.dumps(storage_url)}, {{credentials: 'include'}});
  const buf = await resp.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return JSON.stringify({{ok: true, size: bytes.length, b64: btoa(binary)}});
}})()
''',
    'returnByValue': True,
    'awaitPromise': True
})
```

## Mihomo 代理 (生命线)

```bash
# 端口: 127.0.0.1:7890
# 直连可达的:
#   - PubMed (eutils.ncbi.nlm.nih.gov)
#   - Europe PMC (www.ebi.ac.uk)
#   - Crossref (api.crossref.org)
#   - OpenAlex (api.openalex.org)
#   - Unpaywall (api.unpaywall.org) — 仅元数据查询
# 直连 timeout:
#   - sci-hub.{se,sg,st}
#   - wiley.com
#   - nature.com
#   - springer.com

# 走 Mihomo proxy 的 curl:
curl --proxy http://127.0.0.1:7890 -o /tmp/x.pdf https://sci-hub.sg/storage/...

# 但 storage URL 还是会被 DDoS-Guard 拦, 必须 Chrome fetch
```

## 为什么不工作 (历史错误)

| 方案 | 失败原因 |
|------|----------|
| sandbox 内 curl 直连 sci-hub | 30s timeout, 0 bytes |
| sandbox 内 curl 走 Mihomo 代理 | storage URL 仍被 DDoS-Guard 拦 (898 bytes HTML) |
| sandbox 内 urllib 直连 wiley | 重定向 paywall HTML (5571 bytes) |
| browser_navigate 到 sci-hub | sandbox 没 cookie 历史 → 也可能 captcha |
| Chrome Page.navigate + setDownloadBehavior | Chrome 不触发 download 事件 (inline viewer) |
| Chrome fetch arrayBuffer | ✅ 工作! Chrome 走 Mihomo + 已解 DDoS-Guard |

## Chrome extensions (用户已装)

1. Hermes Chrome Connector (lofhohaidboacnmdnjnhgngjjncfjpmn) — 有 debugger + scripting + tabs
2. Unpaywall (iplffkdpngmdjhlpjmppncnlhomiipha) — content_script 注入 PDF button
3. Open in Sci-Hub (jaoemodfhemfnifaibnffjjlbbacogea) — 只有 contextMenus, 不自动下载
4. Find sci paper (ocofgmnfmjndinnmdimpmijogpaljmal) — contextMenus + tabs

Open in Sci-Hub extension 实际只是导航到 sci-hub domain, 不下载。要 Chrome fetch 拿 bytes。

## 经验教训

- sandbox 网络永远不可靠, 不要花时间在 sandbox 下载上
- 任何 sandbox 内的"我下到文件了" = 一定是错的 (HTML 伪装 / old file / fromDiskCache)
- 唯一可靠路径: Chrome 接管 (用户桌面) + fetch arrayBuffer