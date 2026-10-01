import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")

FILE_EXT = (
    "pln|skp|dwg|dxf|rvt|3dm|3ds|max|blend|c4d|psd|psb|ai|indd|idml|fig|sketch|xd|"
    "docx?|xlsx?|pptx?|pdf|key|pages|numbers|odt|ods|md|txt|jpe?g|png|svg|"
    "mp4|mov|prproj|aep|lrcat|zip"
)
_WIN_PATH = re.compile(r'[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]+')
_POSIX_PATH = re.compile(r'(?:/Users|/home|/Volumes)/[^\r\n:*?"<>|]+')
_FILE_NAME = re.compile(r'([^\\/:*?"<>|\r\n\[\]]+?\.(?:%s))\b' % FILE_EXT, re.I)


def now_ts():
    return int(time.time())


def day_of(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d")


def day_bounds(day):
    """[start, end) jako epoch UTC dla doby w Europe/Warsaw."""
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=TZ)
    nxt = (d + timedelta(days=1)).replace(tzinfo=TZ)
    return int(d.timestamp()), int(nxt.timestamp())


def hhmm(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%H:%M")


def parse_hhmm(day, text):
    h, m = [int(x) for x in text.split(":")]
    d = datetime.strptime(day, "%Y-%m-%d").replace(hour=h, minute=m, tzinfo=TZ)
    return int(d.timestamp())


def fmt_dur(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    return f"{h} h {rem // 60:02d} min" if h else f"{rem // 60} min"


def domain_of(url):
    if not url:
        return ""
    try:
        host = urlparse(url if "//" in url else "//" + url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def extract_path_and_file(title, doc_path=""):
    """Zwraca (pełna_ścieżka_lub_'', nazwa_pliku_lub_'')."""
    for text in (doc_path, title):
        if not text:
            continue
        m = _WIN_PATH.search(text) or _POSIX_PATH.search(text)
        if m:
            p = m.group(0).strip()
            return p, re.split(r"[\\/]", p)[-1]
    m = _FILE_NAME.search(title or "")
    if m:
        return "", m.group(1).strip(" -–—")
    return "", ""
