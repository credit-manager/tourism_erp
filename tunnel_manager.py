import os, sys, re, time, subprocess, urllib.request, urllib.error, shutil

NTFY_TOPIC = "mahmoud-erp-2026"
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
TUNNEL_LOG = os.path.join(os.environ.get("TEMP", os.getcwd()), "cf_tunnel.log")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _get_cloudflared_path():
    cf = shutil.which("cloudflared")
    if cf:
        return cf
    local = os.path.join(BASE_DIR, "cloudflared", "cloudflared.exe")
    if os.path.isfile(local):
        return local
    return None

def _download_cloudflared(target_dir):
    exe_path = os.path.join(target_dir, "cloudflared.exe")
    os.makedirs(target_dir, exist_ok=True)
    try:
        urllib.request.urlretrieve(CLOUDFLARED_URL, exe_path)
        return exe_path
    except Exception:
        return None

def _start_tunnel(cf_path):
    try:
        with open(TUNNEL_LOG, "w") as f:
            f.write("")
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        proc = subprocess.Popen(
            [cf_path, "tunnel", "--url", "http://localhost:8000"],
            stdout=subprocess.DEVNULL,
            stderr=open(TUNNEL_LOG, "a"),
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return proc
    except Exception:
        return None

def _extract_url(timeout=30):
    for _ in range(timeout):
        time.sleep(1)
        try:
            with open(TUNNEL_LOG, "r") as f:
                content = f.read()
                m = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', content)
                if m:
                    return m.group(0).strip()
        except Exception:
            pass
    return None

def _save_url_to_file(url):
    desktop = os.path.join(os.path.expanduser("~"), "Desktop", "erp_url.txt")
    url_paths = [desktop, os.path.join(BASE_DIR, "erp_url.txt")]
    for p in url_paths:
        try:
            with open(p, "w") as f:
                f.write(url + "\n")
        except Exception:
            pass

def _send_via_ntfy(url):
    try:
        data = url.encode("utf-8")
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=data,
            headers={"Title": "ERP Ready", "Priority": "high", "Tags": "rocket"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

def _send_via_pushover(url):
    pass

def _notify(url):
    _save_url_to_file(url)
    _send_via_ntfy(url)

def start(blocking=False):
    cf_path = _get_cloudflared_path()
    if not cf_path:
        dl_dir = os.path.join(BASE_DIR, "cloudflared")
        cf_path = _download_cloudflared(dl_dir)
        if not cf_path:
            return
    proc = _start_tunnel(cf_path)
    if not proc:
        return
    url = _extract_url()
    if url:
        _notify(url)
    if blocking:
        proc.wait()
