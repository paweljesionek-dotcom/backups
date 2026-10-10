# Montażownia reelsów

Jednoplikowa aplikacja przeglądarkowa (`index.html`), bez serwera.

1. Wgrywasz reels jako wzór (nagranie ekranu albo zapisany plik). Aplikacja wyciąga z niego muzykę, liczy tempo i bity (spectral flux + autokorelacja + śledzenie bitów metodą programowania dynamicznego) i wykrywa cięcia w obrazie (różnice histogramów i pikseli między klatkami, z pominięciem pasków interfejsu Instagrama).
2. Wybierasz rytm: cięcia jak w oryginale (przyciągnięte do bitu), co bit, co 2 bity albo co takt. Cięcia można przesuwać, dodawać i usuwać na taśmie.
3. Dodajesz swoje zdjęcia i filmy. Kolejność kafelków to kolejność ujęć.
4. Render: MP4 1080×1920, 30 kl./s, H.264 + AAC przez WebCodecs (mp4-muxer). Jeśli przeglądarka nie ma tych koderów, film nagrywa się w czasie rzeczywistym przez MediaRecorder.

Uruchomienie: otwórz `index.html` w Chrome, Edge albo Safari (lokalnie lub z dowolnego hostingu statycznego, np. GitHub Pages).

Ograniczenia: Instagram nie pozwala pobrać reelsa z samego linku, więc wzór trzeba wgrać jako plik. Zdjęcia HEIC otwiera tylko Safari. Najlepszy plik (H.264 + AAC) dają Chrome/Edge na Windows i macOS oraz Safari.
