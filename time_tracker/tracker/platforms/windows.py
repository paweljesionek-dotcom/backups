"""Windows: tylko ctypes, bez zależności i bez uprawnień administratora."""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class _LASTINPUT(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class WindowsProvider:
    os_name = "windows"

    def idle_seconds(self):
        li = _LASTINPUT()
        li.cbSize = ctypes.sizeof(li)
        if not user32.GetLastInputInfo(ctypes.byref(li)):
            return 0
        return max(0, (kernel32.GetTickCount() - li.dwTime) // 1000)

    def _locked(self):
        # Przy zablokowanym ekranie pulpit wejściowy jest niedostępny.
        h = user32.OpenInputDesktop(0, False, 0x0100)
        if not h:
            return True
        user32.CloseDesktop(h)
        return False

    def _exe(self, pid):
        h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.splitext(os.path.basename(buf.value))[0]
            return ""
        finally:
            kernel32.CloseHandle(h)

    def foreground(self):
        if self._locked():
            return None
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = self._exe(pid.value)
        if app.lower() in ("logonui", "lockapp"):
            return None
        return {"app": app, "title": buf.value, "doc_path": "", "url": "", "incognito": False}
