import sys


def get_provider():
    if sys.platform == "win32":
        from .windows import WindowsProvider
        return WindowsProvider()
    if sys.platform == "darwin":
        from .macos import MacProvider
        return MacProvider()
    raise RuntimeError("Obsługiwane systemy: Windows i macOS")
