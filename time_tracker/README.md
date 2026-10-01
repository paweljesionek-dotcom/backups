# Tracker czasu (Windows + macOS)

Agent w tle sprawdza co 5 s, które okno ma fokus, i zapisuje to lokalnie. Z nazwy pliku, ścieżki, tytułu okna i adresu karty
dopasowuje czas do projektu i marki (we.make, 10design…). Panel web pokazuje dzień, pozwala poprawić niepewne bloki i zatwierdzić dzień.
Zatwierdzone wpisy idą **bezpośrednio do Twojego programu** (HTTP) albo do CSV. Toggla nie używamy.

Tylko biblioteka standardowa Pythona (3.9+). Na Windows: `pip install tzdata`.

## Instalacja (na każdym komputerze)

1. Zainstaluj Python 3.9+ (Windows: python.org, zaznacz "Add to PATH"; macOS: `brew install python`).
2. Skopiuj folder `time_tracker`, utwórz `~/.timetracker/config.json` na bazie `config.example.json`
   (Windows: `%USERPROFILE%\.timetracker\config.json`). Ustaw `device_name` ("PC biuro", "MacBook").
3. Uruchom: `python -m tracker run` (z folderu `time_tracker`).
4. Autostart: `python -m tracker install-autostart` (Windows: skrypt w folderze Autostart; macOS: LaunchAgent).
5. **macOS:** Ustawienia systemowe > Prywatność i ochrona > Dostępność, dodaj Terminal/Python. Bez tego nie ma tytułów okien.
   Przy pierwszym odczycie przeglądarki macOS zapyta o zgodę Automation.
6. Panel: `python -m tracker serve`, potem http://127.0.0.1:8765

Pauza ("prywatne"): `python -m tracker pause` / `resume`.

## Rozszerzenie przeglądarki (Chrome, Edge, Brave, Arc)

`chrome://extensions` > tryb dewelopera > "Załaduj rozpakowane" > folder `extension`. Podaje agentowi URL, tytuł i stan dźwięku
aktywnej karty (lokalnie, na 127.0.0.1). Okna incognito są pomijane. Ustaw token: w konsoli service workera
`chrome.storage.local.set({token:"<local_token z config.json>", port:47800})`. Safari: agent czyta URL przez AppleScript.

## Dwa komputery, jedna baza (chmura)

Na serwerze (np. mały VPS z HTTPS przed nim, region UE) uruchom `python -m tracker serve --host 0.0.0.0` z configiem:
`ingest_tokens: {"PC biuro": "...", "MacBook": "..."}` i `panel_password`. Na komputerach ustaw `server_url` i `device_token`.
Agenci wysyłają dane co minutę, offline buforują w SQLite. Gdy oba komputery pracują w tej samej minucie, liczy się ten
z mniejszą bezczynnością (czas się nie dubluje).

## Jak działa dopasowanie

1. **Prywatne** (`private` w configu): zapisywany tylko czas, bez tytułów i URL, nie trafia do AI ani eksportu.
2. **Reguły** (`rules` + reguły z poprawek): wygrywają ze wszystkim.
3. **Katalog projektów**: kod w nazwie pliku/tytule i folder = 92%, słowo kluczowe = 85%.
4. **Nieprodukcyjne** (`unproductive`): domyślne domeny/aplikacje. Czas liczony osobno, nie wchodzi do eksportu.
5. **AI** (opcjonalnie, `ai.enabled`): tylko dla niejasnych bloków, zbiorczo co 15 min.
6. **Kontekst sesji**: krótkie (do 5 min) wtrącenia bez własnego dokumentu dziedziczą projekt z otoczenia (60%, do sprawdzenia).

Bloki poniżej progu `review_below` (80%) trafiają do "Do sprawdzenia". Poprawka w panelu może od razu zapamiętać regułę.

## Eksport do Twojego programu

W `config.json`: `"export": {"url": "https://.../api/czas", "token": "..."}`. Po "Zatwierdź dzień" przycisk "Wyślij do programu"
robi `POST` z nagłówkiem `Authorization: Bearer <token>` (nazwę nagłówka i prefiks zmienisz w `auth_header`/`auth_prefix`):

```json
{"source":"auto-tracker","date":"2026-10-01","entries":[
  {"external_id":"2026-10-01:WM-024","date":"2026-10-01","start_ts":1790838000,"seconds":900,"minutes":15,
   "project_code":"WM-024","project_name":"Nowak","brand":"we.make","client":"Nowak","description":"Nowak_rzut_v3.pln"}]}
```

`external_id` jest stały, więc program może aktualizować wpis zamiast dublować. Format dopasuję do realnego API Twojego programu.
Zawsze dostępny jest też CSV (`;`, UTF-8 z BOM): przycisk "Pobierz CSV". `export_brands` ogranicza marki, `entry_mode`: `daily`/`blocks`,
`round_minutes`: zaokrąglenie (domyślnie 15). Eksportowane są tylko typy projekt i praca ogólna.

## Prywatność

Brak zrzutów ekranu i keyloggera (liczy się tylko, czy było wejście). Incognito pomijane. Dane lokalnie w `~/.timetracker/tracker.db`.
Surowe zdarzenia kasowane po `raw_retention_days` (90).

## Czego jeszcze nie ma (wg briefu)

Ikona w zasobniku (pauza jest z CLI), instalatory .msi/.dmg (Tauri), podział/scalanie bloków w panelu (jest dopisywanie i usuwanie ręcznych),
2FA panelu (jest hasło), przypomnienie o 17:00, rozszerzenie Safari, osobne reguły wyciągania nazw dokumentów dla Figmy/Canvy/Notion.

Testy: `python -m unittest tests.test_tracker`
