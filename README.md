# Sprechhilfe – Scam With Your Friends auf Deutsch

Du sprichst **Deutsch**, und die Sprechhilfe tippt **genau das, was du gesagt hast**, in das Textfeld vom Spiel. So muss der Anrufer im Spiel nicht mehr raten, was die (englische) Spracherkennung vom Spiel aus deinem Deutsch gemacht hat.

- Läuft **komplett auf deinem PC**: keine Cloud, kein Konto, kein API-Schlüssel, kein Abo.
- Nur beim **allerersten Start** lädt sie einmalig das Spracherkennungs-Modell herunter. Danach geht alles **ohne Internet**.
- Was du sagst, verlässt deinen PC nicht.

> Ehrlich gesagt: Ganz ohne „KI“ geht Spracherkennung nicht. Jede Spracherkennung, auch die in Windows oder im Handy, ist ein gelerntes Modell. Hier ist es **Whisper**, das offline auf deinem PC läuft, wie ein normales Programm. Es schickt nichts ins Internet und fragt keinen Server.

## Download – mit einem Klick

Unter **[Releases](../../releases/latest)** gibt es:

| Datei | Wofür |
| --- | --- |
| **`Sprechhilfe.exe`** | **Herunterladen, doppelklicken, fertig.** Keine Installation. |
| `Sprechhilfe-Setup.exe` | Installer mit Startmenü und „beim Anmelden automatisch starten“ (ohne Admin-Rechte) |
| `Sprechhilfe-Windows-portable.zip` | Ordner-Version zum Entpacken (startet etwas schneller als die Ein-Datei-Version) |

Fragt Windows SmartScreen beim ersten Start nach: **„Weitere Informationen“ → „Trotzdem ausführen“**. Das Programm ist nicht bei Microsoft signiert, deshalb fragt Windows.

Es öffnet sich **kein Fenster**. Die Sprechhilfe läuft unsichtbar im Hintergrund, nur ein **Mikrofon-Symbol unten rechts in der Taskleiste** (eventuell hinter dem Pfeil `^`):

| Farbe | Bedeutung |
| --- | --- |
| grau | lädt (beim ersten Start: Modell wird heruntergeladen) |
| grün | bereit, wartet auf deine Taste |
| rot | nimmt auf |
| blau | erkennt und tippt |
| gelb | Pause |

**Rechtsklick aufs Symbol:** Pause, Einstellungen öffnen, Neu starten (nach dem Ändern der Einstellungen), Protokoll („Was wurde verstanden?“), Mikrofone anzeigen, Beenden.

## Überschneidet sich das mit dem Mikrofon vom Spiel? (Wichtig!)

**Ja, wenn du nichts umstellst.** Windows lässt mehrere Programme gleichzeitig aufs Mikrofon hören. Hört das Spiel selbst auch zu, kommt alles **doppelt** an: einmal falsch vom Spiel und einmal richtig von der Sprechhilfe.

Das Spiel darf also **nicht selbst mithören**. Dann gibt es nur einen Weg ins Spiel, nämlich den getippten Text. So stellst du das ein, je nachdem, was dein Spiel in den Einstellungen anbietet:

1. **Am besten:** In den Spieleinstellungen auf **Text eingeben / Tippen** stellen, oder die **Sprachaufnahme (Voice Input) ausschalten**. Die Sprechhilfe tippt dann für dich.
2. Hat das Spiel **Push-to-Talk** (Taste zum Sprechen): Leg die Spiel-Taste auf eine Taste, die du nie drückst. Die Sprechhilfe nimmt eine **andere** Taste (Standard: `F8` oder die Seitentaste `Maus4`). Dann hört das Spiel nie zu.
3. Oder im Spiel als Mikrofon ein Gerät wählen, das nicht dein echtes ist (falls angeboten).

**Mit deinen Freunden reden** (Discord, Steam, Spiel-Voice-Chat) geht ganz normal weiter. Die Sprechhilfe tippt nur, solange du **ihre Taste gedrückt hältst**. Was du ohne die Taste sagst, landet nicht beim Anrufer.

## So benutzt du sie

1. `Sprechhilfe.exe` doppelklicken. Unten rechts erscheint das Mikrofon-Symbol.
2. Beim ersten Start einmal warten, bis das Modell heruntergeladen ist und das Symbol **grün** wird. Windows zeigt dann „Bereit!“.
3. Im Spiel: **`F8` oder `Maus4` gedrückt halten → Deutsch sprechen → loslassen.**
4. Kurzer Ton, dann tippt die Sprechhilfe den Satz ins Spiel und drückt **Enter** zum Abschicken.
5. **`F9`** = Pause an/aus.

Was verstanden und getippt wurde, steht im Protokoll (Rechtsklick aufs Symbol) und in `%APPDATA%\Sprechhilfe\verlauf.txt`.

### Wenn im Spiel nichts ankommt

- **Das Textfeld muss offen sein.** Klick einmal hinein. Oder trag in den Einstellungen bei `chattaste` die Taste ein, mit der das Spiel das Textfeld öffnet (z. B. `enter` oder `t`). Dann drückt die Sprechhilfe sie vorher selbst.
- **Buchstaben fehlen:** `tippverzoegerung` erhöhen (z. B. `15`), oder `eingabe = einfuegen` probieren.
- **Läuft das Spiel als Administrator**, muss die Sprechhilfe das auch: Rechtsklick → „Als Administrator ausführen“.
- **Abschicken stimmt nicht:** `absendetaste` anpassen oder leer lassen, dann drückst du Enter selbst.

## Einstellungen

Rechtsklick aufs Symbol → **„Einstellungen öffnen“** öffnet `%APPDATA%\Sprechhilfe\einstellungen.ini` im Editor. Jede Zeile ist dort auf Deutsch erklärt. Nach dem Speichern: Rechtsklick → **„Neu starten“**.

| Einstellung | Standard | Bedeutung |
| --- | --- | --- |
| `modus` | `halten` | `halten` (Taste halten), `umschalten` (an/aus drücken), `immer` (hört ständig zu und schickt nach jeder Pause; nur mit Kopfhörer und wenn du nebenbei nicht mit Freunden redest) |
| `sprechtaste` | `F8, maus4` | Mehrere mit Komma, Kombis mit `+` (z. B. `strg+leertaste`, `maus5`, `mausmitte`) |
| `pausetaste` | `F9` | Pause an/aus |
| `mikrofon` | leer | Teil des Gerätenamens. Liste: Rechtsklick → „Mikrofone anzeigen“ |
| `chattaste` | leer | Taste vor dem Tippen (öffnet das Textfeld) |
| `absendetaste` | `enter` | Taste nach dem Tippen |
| `modell` | `auto` | `small` (schnell), `medium` (versteht besser), `large-v3-turbo` (am genauesten) |
| `wichtige_woerter` | leer | Namen und Wörter, die besser erkannt werden sollen |
| `nur_in_fenster` | leer | Nur tippen, wenn ein Fenster mit diesem Titel vorne ist (z. B. `Scam`) |
| `[Ersetzungen]` | – | `falsch = richtig` für Wörter, die immer wieder falsch kommen |

**Wie gut wird verstanden?** `auto` nimmt mit einer NVIDIA-Grafikkarte (wenn CUDA installiert ist) `medium`, sonst `small` auf dem Prozessor. Versteht er dich nicht gut genug, stell `modell = medium` ein. Das ist auf dem Prozessor etwas langsamer (ein paar Sekunden pro Satz), aber deutlich genauer.

## Selbst starten (ohne EXE)

```
pip install -r requirements.txt
python -m sprechhilfe
```

Tests: `python -m unittest discover -s tests -t . -v`
