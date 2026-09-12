#!/usr/bin/env python3
"""verify_sandbox_interceptor.py - 验证 sandbox 拦截器工作正常

用法: python3 verify_sandbox_interceptor.py
退出码: 0 = 全部通过, 1 = 有失败
"""
import os
import sys
import subprocess
import tempfile

#: 被验证的 via54_sandbox_forbidden.py 属 hermes 侧运行时 (不在本仓库)。
#: 其他设备不使用 hermes, 故默认不再假设该路径; 需要时显式设置 HERMES_VIA54_DIR。
_HERMES_VIA54_DIR = os.environ.get("HERMES_VIA54_DIR")
if _HERMES_VIA54_DIR:
    sys.path.insert(0, os.path.expanduser(_HERMES_VIA54_DIR))

print('=' * 60)
print('Sandbox 拦截器自检 (2026-08-07 用户硬规则)')
print('=' * 60)

passed = 0
failed = 0


def check(name, ok, detail=''):
    global passed, failed
    if ok:
        passed += 1
        print(f'  ✅ {name}: {detail}')
    else:
        failed += 1
        print(f'  ❌ {name}: {detail}')


# 1. 拦截器模块能导入
try:
    import via54_sandbox_forbidden
    check('模块导入', True, 'via54_sandbox_forbidden.py')
except Exception as e:
    check('模块导入', False, str(e))
    sys.exit(1)

# 2. 拦截 .pdf URL
try:
    import urllib.request
    urllib.request.urlopen('https://sci-hub.sg/storage/x.pdf')
    check('拦截 .pdf URL', False, '应该 raise 但没')
except RuntimeError as e:
    check('拦截 .pdf URL', True, 'raise')

# 3. 拦截 /storage/ URL
try:
    urllib.request.urlopen('https://sci-hub.sg/storage/x')
    check('拦截 /storage/', False)
except RuntimeError:
    check('拦截 /storage/', True, 'raise')

# 4. 拦截 pdfdirect URL
try:
    urllib.request.urlopen('https://onlinelibrary.wiley.com/doi/pdfdirect/10.1111/bjh.17147')
    check('拦截 pdfdirect', False)
except RuntimeError:
    check('拦截 pdfdirect', True, 'raise')

# 5. 放行 PubMed API
try:
    r = urllib.request.urlopen('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=test&retmax=1')
    check('放行 PubMed API', True, f'status={r.status}')
except Exception as e:
    check('放行 PubMed API', False, str(e)[:100])

# 6. 放行 Europe PMC
try:
    r = urllib.request.urlopen('https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=test&format=json')
    check('放行 Europe PMC', True, f'status={r.status}')
except Exception as e:
    check('放行 Europe PMC', False, str(e)[:100])

# 7. 放行 Chrome 9222
try:
    r = urllib.request.urlopen('http://localhost:9222/json/version')
    check('放行 Chrome 9222', True, f'status={r.status}')
except Exception as e:
    check('放行 Chrome 9222', False, str(e)[:100])

# 8. 放行 Unpaywall API
try:
    r = urllib.request.urlopen('https://api.unpaywall.org/v2/10.1038/s41581-023-00704-1?email=devin@tma-research.org')
    check('放行 Unpaywall API', True, f'status={r.status}')
except Exception as e:
    check('放行 Unpaywall API', False, str(e)[:100])

# 9. 拦截 curl -o
try:
    import subprocess
    subprocess.run(['curl', '-o', os.path.join(tempfile.gettempdir(), 'x'), 'https://example.com/x.pdf'])
    check('拦截 curl -o', False)
except RuntimeError:
    check('拦截 curl -o', True, 'raise')

# 10. 放行 curl (无 -o)
try:
    r = subprocess.run(['curl', '-sSL', 'https://api.crossref.org/works/10.1/test'],
                        capture_output=True, timeout=10)
    check('放行 curl (查询)', True, f'exit={r.returncode}')
except Exception as e:
    check('放行 curl (查询)', False, str(e)[:100])

print()
print('=' * 60)
print(f'结果: {passed} 通过 / {failed} 失败')
print('=' * 60)

sys.exit(0 if failed == 0 else 1)