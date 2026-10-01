"""Aplikacja desktopowa: agent + panel w jednym procesie, ikona w zasobniku. To uruchamia instalator."""
import os
import subprocess
import sys
import threading
import webbrowser

from . import autostart, config as C
from .agent import Agent
from .platforms import get_provider
from .server import make_server

MAC_HINT = ('Tracker czasu potrzebuje zgody "Dostępność", żeby widzieć tytuły okien.\\n\\n'
            'W następnym oknie dodaj "TimeTracker" do listy i włącz przełącznik. Potem wybierz w ikonie '
            'paska menu: Zakończ, i uruchom aplikację ponownie.')


def _mac_first_run_help():
    flag = C.HOME / ".mac_permissions_shown"
    if sys.platform != "darwin" or flag.exists():
        return
    flag.write_text("1")
    subprocess.run(["osascript", "-e", f'display dialog "{MAC_HINT}" buttons {{"Otwórz ustawienia"}} default button 1 with title "Tracker czasu"'],
                   capture_output=True)
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
    if getattr(sys, "frozen", False):
        autostart.set_enabled(True)  # pierwsze uruchomienie: startuj razem z systemem


def _icon_image(paused):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=(200, 140, 30, 255) if paused else (47, 91, 216, 255))
    if paused:
        d.rectangle((22, 20, 29, 44), fill="white")
        d.rectangle((35, 20, 42, 44), fill="white")
    else:
        d.line((32, 32, 32, 16), fill="white", width=5)
        d.line((32, 32, 44, 38), fill="white", width=5)
    return img


def run_app(cfg, db, open_panel=True, tray=True):
    url = f"http://127.0.0.1:{cfg['panel_port']}"
    try:
        srv = make_server(cfg, db, "127.0.0.1", cfg["panel_port"])
    except OSError:  # port zajęty = aplikacja już działa
        webbrowser.open(url)
        return
    C.ensure_config()
    _mac_first_run_help()
    agent = Agent(cfg, db, get_provider())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=agent.run, daemon=True).start()
    if open_panel:
        webbrowser.open(url)

    try:
        if not tray:
            raise ImportError
        import pystray
    except ImportError:
        print(f"Panel: {url} (Ctrl+C kończy)", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return

    def toggle_pause(icon, item):
        agent.paused = not agent.paused
        icon.icon = _icon_image(agent.paused)

    def toggle_autostart(icon, item):
        autostart.set_enabled(not autostart.enabled())

    def quit_(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Otwórz panel", lambda i, it: webbrowser.open(url), default=True),
        pystray.MenuItem(lambda it: "Wznów śledzenie" if agent.paused else "Wstrzymaj (prywatne)", toggle_pause),
        pystray.MenuItem("Uruchamiaj z systemem", toggle_autostart, checked=lambda it: autostart.enabled()),
        pystray.MenuItem("Zakończ", quit_))
    icon = pystray.Icon("tracker", _icon_image(False), "Tracker czasu", menu)
    icon.run()  # musi działać w głównym wątku (macOS)
    os._exit(0)
