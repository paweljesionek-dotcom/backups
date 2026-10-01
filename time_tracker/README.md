# Tracker czasu (Windows + macOS)

Agent w tle sprawdza co 5 s, które okno ma fokus, i zapisuje to lokalnie. Z nazwy pliku, ścieżki, tytułu okna i adresu karty
dopasowuje czas do projektu i marki (we.make, 10design…). Panel web pokazuje dzień, pozwala poprawić niepewne bloki i zatwierdzić dzień.
Zatwierdzone wpisy idą **bezpośrednio do Twojego programu** (HTTP) albo do CSV. Toggla nie używamy.

Użytkownik nie instaluje Pythona: instalator zawiera wszystko.

## Instalacja (gotowy instalator, bez Pythona)

Instalatory buduje GitHub Actions (workflow "Build time tracker installers": Actions > wybierz przebieg > Artifacts):

- **Windows:** `TimeTracker-Windows` > `TimeTracker-Setup-*.exe`. Uruchom, Dalej, Zakończ. Bez uprawnień administratora, startuje z Windows.
  SmartScreen może pokazać "Nieznany wydawca" (instalator nie jest podpisany): "Więcej informacji" > "Uruchom mimo to".
- **macOS:** `TimeTracker-macOS-AppleSilicon` (M1 i nowsze) albo `-Intel` > `.dmg`. Przeciągnij aplikację do Programów.
  Pierwsze otwarcie: prawy przycisk na aplikacji > Otwórz (aplikacja nie jest notaryzowana). Potem wskaż zgodę "Dostępność"
  (aplikacja otworzy właściwe ustawienia i wyjaśni), włącz TimeTracker i uruchom aplikację ponownie. Ikona jest w pasku menu.

Po uruchomieniu w zasobniku/pasku menu jest ikona: Otwórz panel, Wstrzymaj (prywatne), Uruchamiaj z systemem, Zakończ.
Projekty, reguły i eksport ustawiasz w panelu: **Ustawienia** na dole strony (nie musisz ruszać plików).
Ustaw w nich też `device_name` ("PC biuro", "MacBook").

### Dla programisty (uruchamianie z kodu)

`python -m tracker app` (Python 3.9+, `pip install pystray pillow`, na Windows też `tzdata`). Budowanie lokalnie:
`pyinstaller build/TimeTracker.spec`, a na Windows dodatkowo `iscc build\installer.iss`.

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

Podpisane i notaryzowane instalatory (bez ostrzeżeń systemu; wymaga płatnych certyfikatów), podział/scalanie bloków w panelu (jest dopisywanie i usuwanie ręcznych),
2FA panelu (jest hasło), przypomnienie o 17:00, rozszerzenie Safari, osobne reguły wyciągania nazw dokumentów dla Figmy/Canvy/Notion.

Testy: `python -m unittest tests.test_tracker`
