# -*- coding: utf-8 -*-
"""tma_scihub.py — Sci-Hub 兜底下载 (项目 via54_pdf_download.py 5 策略之一)"""
import os, re, subprocess, urllib.request


def _fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def scihub_pdf(doi, out_path):
    """尝试 Sci-Hub 下载; 成功返回 True"""
    bases = ['https://sci-hub.ru', 'https://sci-hub.st', 'https://sci-hub.se']
    ua = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    for base in bases:
        try:
            url = base + '/' + doi
            r = subprocess.run(['curl', '-s', '-L', '-o', out_path, '--max-time', '90',
                                '-H', 'User-Agent: ' + ua,
                                '-H', 'Accept: application/pdf,*/*',
                                url],
                               capture_output=True, timeout=110)
            if r.returncode == 0 and os.path.exists(out_path):
                with open(out_path, 'rb') as f:
                    head = f.read(5)
                if head == b'%PDF-':
                    return True
                data = open(out_path, 'rb').read()
                txt = data.decode('utf-8', 'ignore')
                links = re.findall(r'(?:iframe|embed|src|href)\s*=\s*["\']([^"\']+\.pdf[^"\']*)["\']', txt, re.I)
                for pm in links:
                    pm2 = pm if pm.startswith('http') else (base + pm)
                    try:
                        d2 = _fetch(pm2)
                        if d2[:4] == b'%PDF':
                            open(out_path, 'wb').write(d2)
                            return True
                    except Exception:
                        pass
        except Exception:
            continue
    return False
