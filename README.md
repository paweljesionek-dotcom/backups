# Drive -> Notion backup agent

Skrypt jednorazowego uruchomienia (uruchamiany raz na dobę przez cron), który
przeszukuje wskazany dysk udostępniony (shared drive) Google Workspace,
wykrywa nowe pliki i nowe wersje istniejących plików, i zapisuje każdą z nich
jako osobną stronę w bazie danych Notion wraz z załącznikiem i metadanymi.
Wpisy starsze niż `RETENTION_DAYS` (domyślnie 30) są automatycznie
archiwizowane w Notion (odpowiednik usunięcia do kosza).

Między uruchomieniami skrypt nie trzyma żadnego stanu poza lokalnym plikiem
SQLite (`backup_state.sqlite3`) - nie ma procesu działającego w tle.

## Struktura projektu

```
backup.py                  # punkt wejścia - uruchamiane przez cron / ręcznie
backup_agent/
  config.py                # wczytywanie konfiguracji ze zmiennych środowiskowych
  db.py                     # lokalny stan w SQLite (backed_up_versions)
  drive_client.py           # listowanie i pobieranie plików z Google Drive
  notion_client.py          # upload plików i zarządzanie stronami w Notion
  logging_setup.py          # logowanie do pliku i konsoli
requirements.txt
.env.example
```

## 1. Konfiguracja Google (Service Account + shared drive)

Nie jest wymagana domain-wide delegation - service account jest po prostu
dodawany jako zwykły członek konkretnego shared drive.

1. W [Google Cloud Console](https://console.cloud.google.com/) utwórz (lub
   wybierz) projekt.
2. Włącz **Google Drive API**: *APIs & Services -> Library -> Google Drive
   API -> Enable*.
3. Utwórz service account: *APIs & Services -> Credentials -> Create
   Credentials -> Service account*. Nazwa dowolna, np. `drive-notion-backup`.
4. Po utworzeniu wejdź w service account -> zakładka *Keys* -> *Add Key ->
   Create new key -> JSON*. Pobrany plik JSON to Twój
   `GOOGLE_SERVICE_ACCOUNT_JSON`.
5. Skopiuj adres e-mail service account (postać
   `nazwa@projekt.iam.gserviceaccount.com`).
6. W Google Drive otwórz shared drive, który chcesz backupować -> **Manage
   members** -> dodaj adres e-mail service account jako członka z rolą
   **Content manager** (wystarcza do odczytu i eksportu plików; przy tej
   integracji service account niczego nie zapisuje na dysku).
7. ID shared drive znajdziesz w URL po otwarciu dysku w przeglądarce:
   `https://drive.google.com/drive/folders/<GOOGLE_SHARED_DRIVE_ID>` (dla
   głównego widoku shared drive to ten sam identyfikator, który Drive API
   nazywa `driveId`).

## 2. Konfiguracja Notion (integracja + baza danych)

1. Wejdź na https://www.notion.so/my-integrations -> **New integration**.
   Nadaj nazwę (np. `Drive Backup`), wybierz workspace, zapisz. Skopiuj
   **Internal Integration Secret** - to jest `NOTION_API_KEY`.
2. Utwórz nową bazę danych (Database) w Notion z następującymi properties
   (nazwy muszą się zgadzać dokładnie - kod odwołuje się do nich po nazwie):

   | Nazwa property         | Typ              |
   |-------------------------|------------------|
   | `Name`                  | Title (domyślne) |
   | `Source File ID`        | Text             |
   | `Drive Link`            | URL              |
   | `Version/Revision ID`   | Text             |
   | `Backed Up At`          | Date             |
   | `Original Modified At`  | Date             |
   | `Attachment`            | Files & media    |

3. Udostępnij bazę integracji: w bazie danych kliknij **...** (menu) ->
   **Connections** -> wybierz utworzoną integrację (`Drive Backup`). Bez
   tego kroku API zwróci błąd 404 przy próbie zapisu.
4. ID bazy danych (`NOTION_DATABASE_ID`) to 32-znakowy identyfikator z URL
   bazy, np. `https://www.notion.so/workspace/<NOTION_DATABASE_ID>?v=...`.
5. Notion File Upload API wymaga aktualnego nagłówka `Notion-Version`
   (obecnie `2025-09-03`) oraz integracji z uprawnieniem zapisu treści.
   Limity rozmiaru pliku i próg, od którego trzeba użyć trybu
   `multi_part`, mogą się zmieniać - przed produkcyjnym wdrożeniem sprawdź
   aktualną wartość w
   [dokumentacji Notion](https://developers.notion.com/docs/working-with-files-and-media)
   i w razie potrzeby zaktualizuj stałe `SINGLE_PART_LIMIT` / `PART_SIZE` w
   `backup_agent/notion_client.py`.

## 3. Instalacja

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# uzupełnij .env swoimi wartościami
```

## 4. Testowanie lokalne

```bash
source .venv/bin/activate
python backup.py
```

Wynik działania trafia zarówno na stdout, jak i do pliku wskazanego przez
`LOG_FILE` (domyślnie `./backup.log`). Kod wyjścia `0` oznacza pełny sukces,
`1` oznacza, że część plików/stron nie powiodła się (błąd per-plik nie
przerywa całego przebiegu - szczegóły są w logu), `2` oznacza błąd
konfiguracji (np. brakującą zmienną środowiskową).

Aby przetestować retencję bez czekania 30 dni, tymczasowo ustaw w `.env`
niższą wartość, np. `RETENTION_DAYS=0`, i uruchom skrypt ponownie - wszystkie
dotąd zbackupowane strony zostaną zarchiwizowane.

Stan między uruchomieniami trzymany jest w pliku SQLite wskazanym przez
`SQLITE_PATH`. Usunięcie tego pliku spowoduje, że przy następnym uruchomieniu
skrypt potraktuje wszystkie pliki jako nowe i zbackupuje je ponownie.

## 5. Harmonogram (cron)

Przykładowa linia crontab uruchamiająca backup codziennie o 3:00 w nocy
(`crontab -e`):

```cron
0 3 * * * cd /path/to/backups && /path/to/backups/.venv/bin/python backup.py >> /path/to/backups/cron.log 2>&1
```

Uwagi:

* Użyj pełnych, bezwzględnych ścieżek - cron nie ma ustawionego takiego
  samego `PATH`/cwd jak sesja interaktywna.
* `>> cron.log 2>&1` to dodatkowa siatka bezpieczeństwa na wypadek, gdyby
  skrypt nie zdążył zainicjalizować własnego logowania (np. błąd
  konfiguracji przed wczytaniem `.env`) - normalne logi z działania backupu
  i tak trafiają do `LOG_FILE` ustawionego w `.env`.
* Upewnij się, że plik `.env` znajduje się w katalogu, z którego uruchamiany
  jest skrypt (`cd /path/to/backups` w linii crontab), albo ustaw zmienne
  środowiskowe bezpośrednio w crontabie / w pliku wczytywanym przez cron.

## Jak to działa (skrót)

1. `drive_client.py` listuje wszystkie pliki na shared drive
   (`files.list` z `corpora='drive'`, paginacja przez `nextPageToken`),
   pomijając foldery.
2. Dla każdego pliku wyliczany jest identyfikator wersji
   (`headRevisionId` dla plików binarnych, `version` dla natywnych
   dokumentów Google, `modifiedTime` jako ostateczny fallback) i sprawdzane
   jest w lokalnym SQLite, czy ta wersja była już backupowana.
3. Jeśli to nowa wersja: plik jest pobierany (`files.get_media` dla plików
   binarnych, `files.export_media` do PDF dla Google Docs/Sheets/Slides/
   Drawings), wgrywany do Notion przez File Upload API
   (`/v1/file_uploads` + `/send`, automatycznie w trybie `multi_part` dla
   plików > 20 MiB), a następnie tworzona jest nowa strona w bazie Notion
   z metadanymi i podpiętym załącznikiem.
4. Po zakończeniu backupu uruchamiana jest retencja: baza Notion jest
   odpytywana o strony z `Backed Up At` starszym niż `RETENTION_DAYS` dni,
   każda taka strona jest archiwizowana (`PATCH /v1/pages/{id}` z
   `archived: true`).
5. Błąd przy pojedynczym pliku/stronie jest logowany i nie przerywa
   przebiegu całego skryptu (pozostałe pliki są nadal przetwarzane).

## Duże pliki (setki MB) i plan Notion

* Notion File Upload API ma limit rozmiaru pliku zależny od planu
  workspace: **5 MiB na darmowym planie**, **5 GiB na planach płatnych**
  (Plus/Business/Enterprise). Jeśli w praktyce backupowane są pliki rzędu
  kilkuset MB, workspace Notion **musi** być na płatnym planie - w
  przeciwnym razie upload takich plików będzie się kończyć błędem (złapanym
  per-plik, więc reszta przebiegu i tak pójdzie dalej, ale te konkretne
  pliki nigdy się nie zbackupują).
* Pliki są pobierane z Drive strumieniowo do pliku tymczasowego na dysku
  (nie do pamięci RAM), a do Notion wgrywane w kawałkach o stałym rozmiarze
  (`PART_SIZE`, domyślnie 10 MiB) czytanych bezpośrednio z dysku - dzięki
  temu zużycie RAM przez pojedynczy plik jest ograniczone do ~10 MB
  niezależnie od tego, czy plik ma 5 MB czy 5 GB. Ma to znaczenie na małym
  VPS (np. mikr.us) z ograniczoną ilością RAM.
* Pliki > 20 MiB są automatycznie wysyłane w trybie `multi_part` (wymóg
  Notion API) - nie wymaga to żadnej dodatkowej konfiguracji.
* Upewnij się, że na dysku serwera jest wolne miejsce co najmniej wielkości
  największego backupowanego pliku (plik tymczasowy jest usuwany zaraz po
  wysłaniu do Notion, także w przypadku błędu).

## Ograniczenia i uwagi

* Pliki Google Forms, Sites, Apps Script itp. nie mają eksportowalnej
  zawartości binarnej - są pomijane z odpowiednim wpisem w logu.
* Bardzo duże arkusze/dokumenty Google mogą przekroczyć limit rozmiaru
  eksportu Google Drive API - taki błąd jest łapany per-plik i logowany,
  reszta przebiegu nie jest przerywana.
* `MAX_FILE_SIZE_BYTES` pozwala z góry pomijać pliki większe niż ustalony
  limit (domyślnie 5 GiB, zgodnie z limitem Notion na płatnych planach),
  zanim skrypt zacznie je w ogóle pobierać.
