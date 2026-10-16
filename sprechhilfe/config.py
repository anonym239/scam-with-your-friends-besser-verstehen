"""Einstellungen aus %APPDATA%\\Sprechhilfe\\einstellungen.ini (beim ersten Start mit Erklärungen angelegt)."""
import configparser
import os
from dataclasses import dataclass, field

APP_NAME = "Sprechhilfe"

DEFAULT_INI = """\
; Einstellungen für die Sprechhilfe (Scam With Your Friends auf Deutsch).
; Nach dem Ändern speichern und die Sprechhilfe neu starten.
; Zeilen mit ; davor sind nur Erklärungen.

[Sprechhilfe]
; Wie du sprichst:
;   halten     = Taste gedrückt halten, sprechen, loslassen -> Text kommt ins Spiel (empfohlen,
;                dann landet nicht im Spiel, was du mit deinen Freunden redest)
;   umschalten = Taste einmal drücken = Aufnahme an, nochmal drücken = fertig
;   immer      = hört ständig zu und schickt jeden Satz nach einer kurzen Pause ab
modus = halten

; Die Sprech-Taste. Mehrere zur Auswahl mit Komma trennen, Kombinationen mit +.
; Beispiele: F8, maus4 (vordere Seitentaste der Maus), maus5, mausmitte, v, strg+leertaste, num0
sprechtaste = F8, maus4

; Diese Taste schaltet die Sprechhilfe an und aus (Pause).
pausetaste = F9

; Mikrofon: leer = Windows-Standard. Sonst ein Teil des Namens, z. B.  mikrofon = HyperX
mikrofon =

; Textfeld merken: Zeig im Spiel mit der Maus auf das Textfeld und drück diese Taste (einmal reicht).
; Danach klickt die Sprechhilfe vor jedem Satz selbst ins Textfeld, damit wirklich jeder Satz ankommt,
; auch wenn das Spiel nach dem Abschicken das Textfeld schließt. Nochmal drücken = neue Stelle merken.
feld_merken_taste = F10

; Taste(n), die VOR dem Tippen gedrückt werden, um im Spiel das Textfeld zu öffnen.
; Meist nicht nötig, wenn du das Textfeld gemerkt hast. Beispiele: enter, t, y, strg+t
chattaste =

; Taste nach dem Tippen zum Abschicken. Leer = nicht abschicken (dann selbst Enter drücken).
absendetaste = enter

; So kommt der Text ins Spiel:
;   tippen    = Buchstabe für Buchstabe (geht fast überall)
;   einfuegen = über die Zwischenablage mit Strg+V (schneller, falls das Spiel Strg+V kann)
eingabe = tippen

; Pause zwischen zwei Buchstaben in Millisekunden (höher, falls Buchstaben fehlen).
tippverzoegerung = 8

; Wartezeit in Millisekunden nach dem Klick/der Chattaste, bis das Textfeld bereit ist.
wartezeit = 150

; Wartezeit in Millisekunden zwischen dem letzten Buchstaben und dem Abschicken.
absende_wartezeit = 150

; Nur tippen, wenn das Spiel im Vordergrund ist. Leer = immer ins aktuelle Fenster tippen.
; Ein Teil des Fenstertitels, z. B.  nur_in_fenster = Scam
nur_in_fenster =

; Spracherkennungs-Modell (läuft komplett auf deinem PC, ohne Internet, ohne Konto):
;   auto           = mit eingerichteter NVIDIA-Grafikkarte: large-v3-turbo (am genauesten),
;                    sonst auf dem Prozessor: medium bei starken PCs, small bei schwächeren
;   small          = ~460 MB, schnell, gut
;   medium         = ~1,5 GB, versteht deutlich besser, auf dem Prozessor etwas langsamer
;   large-v3-turbo = ~1,6 GB, am genauesten, am besten mit Grafikkarte
modell = auto

; Rechner: auto, cpu oder cuda (NVIDIA-Grafikkarte)
geraet = auto

; Sprache, die du sprichst:
;   auto = erkennt selbst, welche Sprache du sprichst (Deutsch, Englisch, Türkisch, Russisch, …)
;          und tippt es genau so, wie du es gesagt hast (es wird NICHT übersetzt)
;   de / en / tr / ru / pl / ar / … = immer diese eine Sprache (am zuverlässigsten, wenn du nur die sprichst)
sprache = auto

; Bei sprache = auto: Wenn sich die Erkennung nicht sicher ist, wird diese Sprache genommen.
hauptsprache = de

; Bei sprache = auto: nur diese Sprachen zulassen (mit Komma). Leer = alle ~100 Sprachen.
; Hilft, wenn Deutsch manchmal als Niederländisch o. Ä. erkannt wird. Beispiel:  erlaubte_sprachen = de, en, tr
erlaubte_sprachen =

; Wörter, die oft falsch verstanden werden (Namen usw.), mit Komma getrennt.
; Beispiel:  wichtige_woerter = Sparkasse, PayPal, IBAN, Amazon
wichtige_woerter =

; Kurze Töne beim Start und Ende der Aufnahme.
toene = ja

; Punkt am Satzende weglassen (ja/nein).
punkt_weglassen = nein

; Nur bei modus = immer: wie lange Stille (Sekunden) einen Satz beendet.
satzpause = 0.8

; Nur bei modus = immer: Lautstärke, ab der es als Sprechen zählt. auto = selbst einmessen.
; Zahl zwischen 100 (sehr empfindlich) und 3000 (nur laut).
schwelle = auto

[Ersetzungen]
; Was immer wieder falsch erkannt wird, hier korrigieren:   falsch = richtig
; Beispiel:
; pay pal = PayPal
"""


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def ini_path():
    return os.path.join(data_dir(), "einstellungen.ini")


@dataclass
class Settings:
    modus: str = "halten"
    sprechtaste: str = "F8, maus4"
    pausetaste: str = "F9"
    mikrofon: str = ""
    feld_merken_taste: str = "F10"
    chattaste: str = ""
    absendetaste: str = "enter"
    eingabe: str = "tippen"
    tippverzoegerung: int = 8
    wartezeit: int = 150
    absende_wartezeit: int = 150
    nur_in_fenster: str = ""
    modell: str = "auto"
    geraet: str = "auto"
    sprache: str = "auto"
    hauptsprache: str = "de"
    erlaubte_sprachen: str = ""
    wichtige_woerter: str = ""
    toene: bool = True
    punkt_weglassen: bool = False
    satzpause: float = 0.8
    schwelle: str = "auto"
    ersetzungen: dict = field(default_factory=dict)


_TRUE = {"ja", "j", "true", "1", "an", "yes", "on"}
MODES = ("halten", "umschalten", "immer")


def parse(text):
    """Einstellungen aus dem INI-Text. Unbekanntes oder Kaputtes fällt auf den Standard zurück."""
    parser = configparser.ConfigParser(inline_comment_prefixes=None, interpolation=None, delimiters=("=",))
    parser.optionxform = str
    parser.read_string(text)
    section = parser["Sprechhilfe"] if parser.has_section("Sprechhilfe") else {}
    settings = Settings()
    for name, default in vars(Settings()).items():
        if name == "ersetzungen" or name not in section:
            continue
        raw = section[name].strip()
        try:
            if isinstance(default, bool):
                value = raw.lower() in _TRUE
            elif isinstance(default, int):
                value = int(raw)
            elif isinstance(default, float):
                value = float(raw.replace(",", "."))
            else:
                value = raw
        except ValueError:
            continue
        setattr(settings, name, value)
    settings.modus = settings.modus.lower()
    if settings.modus not in MODES:
        settings.modus = "halten"
    settings.eingabe = "einfuegen" if settings.eingabe.lower().startswith("einf") else "tippen"
    if parser.has_section("Ersetzungen"):
        settings.ersetzungen = {k.strip(): v.strip() for k, v in parser["Ersetzungen"].items() if k.strip()}
    return settings


# Standardwerte der ersten Version. Was der Nutzer davon nie geändert hat, bekommt beim Aktualisieren die neuen Werte.
_OLD_DEFAULTS = {"sprache": "de", "tippverzoegerung": "4"}


def migrate(old_text):
    """Bringt eine alte Einstellungsdatei auf den neuen Stand und behält dabei alles, was der Nutzer geändert hat."""
    import re
    old = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    old.optionxform = str
    old.read_string(old_text)
    new_text = DEFAULT_INI
    if old.has_section("Sprechhilfe"):
        for key, value in old["Sprechhilfe"].items():
            value = value.strip()
            if _OLD_DEFAULTS.get(key) == value:
                continue
            new_text, count = re.subn(rf"(?m)^{re.escape(key)} =.*$", lambda _m: f"{key} = {value}", new_text, count=1)
    if old.has_section("Ersetzungen"):
        lines = [f"{k} = {v.strip()}" for k, v in old["Ersetzungen"].items()]
        if lines:
            new_text = new_text.rstrip("\n") + "\n" + "\n".join(lines) + "\n"
    return new_text


def load():
    """Liest die Einstellungen; legt die Datei beim ersten Start an und bringt alte Dateien auf den neuen Stand."""
    path = ini_path()
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_INI)
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    if "hauptsprache" not in text:
        text = migrate(text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return parse(text)


def set_value(key, value):
    """Ändert eine Einstellung in der Datei und lässt alle Erklärungen und anderen Werte, wie sie sind."""
    import re
    load()
    path = ini_path()
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    text, count = re.subn(rf"(?m)^{re.escape(key)}[ \t]*=.*$", lambda _m: f"{key} = {value}", text, count=1)
    if not count:
        text = re.sub(r"(?m)^\[Sprechhilfe\][ \t]*$", lambda _m: f"[Sprechhilfe]\n{key} = {value}", text, count=1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def state_path():
    return os.path.join(data_dir(), "zustand.json")


def load_state():
    """Kleine Merkliste (Textfeld-Position, ob nach der Grafikkarte schon gefragt wurde)."""
    import json
    try:
        with open(state_path(), encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(**changes):
    import json
    data = load_state()
    data.update(changes)
    with open(state_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
