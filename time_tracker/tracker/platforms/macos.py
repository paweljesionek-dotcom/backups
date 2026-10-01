"""macOS: osascript + ioreg, bez zależności. Wymaga zgody Accessibility
(Ustawienia systemowe > Prywatność i ochrona > Dostępność) dla terminala/Pythona."""
import re
import subprocess
from urllib.parse import unquote, urlparse

_FRONT = '''
tell application "System Events"
  set p to first application process whose frontmost is true
  set pname to name of p
  set wtitle to ""
  set wdoc to ""
  try
    set wtitle to value of attribute "AXTitle" of window 1 of p
  end try
  try
    set wdoc to value of attribute "AXDocument" of window 1 of p
  end try
  return pname & "\\n" & wtitle & "\\n" & wdoc
end tell
'''

_CHROMIUM = {"Google Chrome": "Google Chrome", "Brave Browser": "Brave Browser",
             "Microsoft Edge": "Microsoft Edge", "Arc": "Arc"}


def _osa(script, timeout=3):
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


class MacProvider:
    os_name = "macos"

    def idle_seconds(self):
        try:
            out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=3).stdout
            m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
            return int(m.group(1)) // 1_000_000_000 if m else 0
        except (subprocess.TimeoutExpired, OSError):
            return 0

    def foreground(self):
        raw = _osa(_FRONT)
        if not raw:
            return None
        parts = (raw.split("\n") + ["", "", ""])[:3]
        app, title, doc = parts
        doc_path = unquote(urlparse(doc).path) if doc.startswith("file://") else ""
        url, incognito = "", False
        if app in _CHROMIUM:  # awaryjnie, gdy nie ma rozszerzenia
            res = _osa(f'tell application "{app}" to return (mode of front window) & "\\n" & (URL of active tab of front window)')
            if res:
                mode, _, url = res.partition("\n")
                incognito = mode.strip() == "incognito"
        elif app == "Safari":
            url = _osa('tell application "Safari" to return URL of front document')
        return {"app": app, "title": title, "doc_path": doc_path, "url": url, "incognito": incognito}
