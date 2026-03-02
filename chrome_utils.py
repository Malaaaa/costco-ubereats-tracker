"""Chrome DevTools Protocol (CDP) connection utilities for WSL → Windows Chrome."""

import subprocess
import time
import requests

from config import CHROME_PATH, PROFILE_PATH, CDP_PORT


def get_wsl_host_ip():
    """Extract the Windows host IP from WSL's /etc/resolv.conf."""
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if line.startswith("nameserver"):
                    return line.split()[1]
    except Exception:
        pass
    return "127.0.0.1"


def start_windows_chrome():
    """Launch a clean Windows Chrome instance with CDP debugging enabled."""
    subprocess.run([
        "powershell.exe", "-Command",
        "Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue"
    ])
    time.sleep(2)

    ps_cmd = (
        f"Start-Process '{CHROME_PATH}' "
        f"-ArgumentList '--remote-debugging-port={CDP_PORT}', "
        f"'--remote-debugging-address=0.0.0.0', "
        f"'--user-data-dir={PROFILE_PATH}'"
    )
    subprocess.run(["powershell.exe", "-Command", ps_cmd])
    time.sleep(5)


def stop_windows_chrome():
    """Force-close all Windows Chrome processes."""
    subprocess.run([
        "powershell.exe", "-Command",
        "Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue"
    ])


def find_cdp_url():
    """Probe known IPs to find the active Chrome CDP endpoint.

    Returns the base CDP URL (e.g. 'http://172.x.x.x:9322') or None.
    """
    ips_to_try = [get_wsl_host_ip(), "127.0.0.1", "localhost", "10.0.0.1"]

    for ip in ips_to_try:
        url = f"http://{ip}:{CDP_PORT}/json/version"
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                print(f"[+] Found CDP endpoint at {url}")
                return f"http://{ip}:{CDP_PORT}"
        except Exception:
            continue

    # Fallback: try the default gateway
    try:
        output = subprocess.check_output(
            "ip route | awk '/default/ { print $3 }'", shell=True
        )
        ip = output.decode("utf-8").strip()
        url = f"http://{ip}:{CDP_PORT}/json/version"
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            print(f"[+] Found CDP endpoint at {url}")
            return f"http://{ip}:{CDP_PORT}"
    except Exception:
        pass

    return None
