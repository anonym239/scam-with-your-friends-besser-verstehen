"""Die Sprechhilfe: hört dir auf Deutsch zu und tippt genau das, was du gesagt hast, ins Spiel.

Läuft als kleines Fenster im Hintergrund. Alles passiert auf dem eigenen PC: keine KI im Internet, kein Konto,
kein API-Schlüssel, keine Cloud.
"""
import datetime
import os
import queue
import subprocess
import sys
import threading
import time

from . import audio, config, keys, text
from .erkennung import Recognizer

VERSION = os.environ.get("SPRECHHILFE_VERSION", "1.0")


def _beep(freq, ms, enabled):
    if not enabled or sys.platform != "win32":
        return
    import winsound
    threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()


def log(message=""):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}" if message else "", flush=True)


def _history(line):
    try:
        with open(os.path.join(config.data_dir(), "verlauf.txt"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {line}\n")
    except OSError:
        pass


class App:
    def __init__(self, settings):
        self.s = settings
        self.talk_keys = keys.parse_hotkeys(settings.sprechtaste)
        self.pause_keys = keys.parse_hotkeys(settings.pausetaste)
        self.chat_key = keys.parse_combo(settings.chattaste) if settings.chattaste.strip() else ()
        self.send_key = keys.parse_combo(settings.absendetaste) if settings.absendetaste.strip() else ()
        for combo in (self.chat_key, self.send_key):
            if keys.is_mouse(combo):
                raise keys.KeyError_("Maustasten gehen nicht als Chat- oder Absendetaste")
        self.paused = False
        self.jobs = queue.Queue()
        self.recognizer = Recognizer(settings.modell, settings.geraet, settings.sprache, settings.wichtige_woerter)
        threshold = None if settings.schwelle.lower() == "auto" else float(settings.schwelle)
        self.segmenter = audio.Segmenter(pause=settings.satzpause, threshold=threshold)
        self.recorder = audio.Recorder(audio.find_device(settings.mikrofon),
                                       on_frame=self._on_frame if settings.modus == "immer" else None)

    # ---- Aufnahme -------------------------------------------------------------------------------------------
    def _on_frame(self, samples):
        if self.paused:
            return
        was = self.segmenter.speaking
        for sentence in self.segmenter.feed(samples):
            self.jobs.put(sentence)
        if self.segmenter.speaking and not was:
            print("  … ich höre", flush=True)

    # ---- Erkennen und Tippen (eigener Thread, damit die Taste nie hängt) -------------------------------------
    def _worker(self):
        while True:
            samples = self.jobs.get()
            try:
                started = time.monotonic()
                spoken = self.recognizer.transcribe(samples)
                result = text.finish(spoken, self.s.ersetzungen, self.s.punkt_weglassen)
                if not result:
                    log("(nichts verstanden)")
                    continue
                log(f"Verstanden ({time.monotonic() - started:.1f} s): {result}")
                self._deliver(result)
            except Exception as error:
                log(f"Fehler: {error}")

    def _deliver(self, result):
        if self.paused:
            log("  pausiert, nicht getippt")
            return
        title = keys.foreground_title()
        if self.s.nur_in_fenster and self.s.nur_in_fenster.lower() not in title.lower():
            log(f"  nicht getippt: das Spiel ist nicht vorne (vorne ist „{title}“)")
            return
        if self.chat_key:
            keys.press(self.chat_key)
            time.sleep(self.s.wartezeit / 1000)
        if self.s.eingabe == "einfuegen":
            keys.paste_text(result)
        else:
            keys.type_text(result, self.s.tippverzoegerung)
        if self.send_key:
            time.sleep(0.05)
            keys.press(self.send_key)
        _history(result)
        _beep(1200, 40, self.s.toene)

    # ---- Hauptschleife ---------------------------------------------------------------------------------------
    def run(self):
        self.recognizer.load(log)
        log(f"Spracherkennung bereit: {self.recognizer.description}")
        self.recorder.start()
        log(f"Mikrofon: {self.recorder.device_name}")
        threading.Thread(target=self._worker, name="Erkennung", daemon=True).start()
        self._print_help()
        _beep(880, 80, self.s.toene)

        recording = False
        talk_was = pause_was = False
        while True:
            time.sleep(0.01)
            pause_now = keys.any_down(self.pause_keys)
            if pause_now and not pause_was:
                self.paused = not self.paused
                if recording:
                    self.recorder.end()
                    recording = False
                log("⏸  PAUSE: die Sprechhilfe hört nicht zu." if self.paused else "▶  Wieder an.")
                _beep(500 if self.paused else 900, 120, self.s.toene)
            pause_was = pause_now
            if self.paused or self.s.modus == "immer":
                continue

            talk_now = keys.any_down(self.talk_keys)
            if self.s.modus == "halten":
                start, stop = talk_now and not talk_was, recording and not talk_now
            else:  # umschalten
                pressed = talk_now and not talk_was
                start, stop = pressed and not recording, pressed and recording
            talk_was = talk_now

            if start:
                self.recorder.begin()
                recording = True
                print("  ● Aufnahme … sprich jetzt", flush=True)
                _beep(1000, 60, self.s.toene)
            elif stop:
                time.sleep(0.25)          # das letzte Wort noch mitnehmen
                samples = self.recorder.end()
                recording = False
                _beep(700, 60, self.s.toene)
                if len(samples) < audio.RATE * 0.3:
                    log("(zu kurz)")
                else:
                    self.jobs.put(samples)

    def _print_help(self):
        print()
        if self.s.modus == "halten":
            print(f"  ► Halte {self.s.sprechtaste} gedrückt und sprich Deutsch. Beim Loslassen wird getippt.")
        elif self.s.modus == "umschalten":
            print(f"  ► Drück {self.s.sprechtaste}, sprich, und drück nochmal. Dann wird getippt.")
        else:
            print("  ► Sprich einfach. Nach jeder kurzen Pause wird der Satz getippt.")
        print(f"  ► {self.s.pausetaste} = Pause an/aus.  Beenden: dieses Fenster schließen.")
        print(f"  ► Einstellungen: {config.ini_path()}")
        print()


def _open_settings():
    path = config.ini_path()
    config.load()
    if sys.platform == "win32":
        subprocess.Popen(["notepad.exe", path])
    else:
        print(path)


def _selftest():
    """Für den automatischen Build: lädt das kleinste Modell und erkennt Stille (prüft, dass alles eingepackt ist)."""
    out = os.path.join(config.data_dir(), "selbsttest.txt")
    try:
        import sounddevice  # noqa: F401
        import numpy as np
        keys.parse_hotkeys("F8, maus4, strg+t, num+")
        recognizer = Recognizer("tiny", "cpu", "de")
        recognizer.load(lambda m: None)
        recognizer.transcribe(np.zeros(16000, dtype=np.int16))
        message, code = "OK", 0
    except Exception as error:
        message, code = f"FEHLER: {error!r}", 1
    with open(out, "w", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message)
    return code


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--selbsttest" in sys.argv:
        sys.exit(_selftest())
    if "--einstellungen" in sys.argv:
        _open_settings()
        return
    if "--mikrofone" in sys.argv:
        for index, name in audio.input_devices():
            print(f"{index:3}  {name}")
        return

    keys.set_console_title("Sprechhilfe – Scam With Your Friends auf Deutsch")
    print(f"Sprechhilfe {VERSION} – Deutsch sprechen, das Spiel bekommt den Text.\n")
    try:
        settings = config.load()
        app = App(settings)
        app.run()
    except KeyboardInterrupt:
        return
    except keys.KeyError_ as error:
        print(f"\nUnbekannte Taste in den Einstellungen: {error}")
        print(f"Bitte in {config.ini_path()} korrigieren.")
    except Exception as error:
        print(f"\nDas hat nicht geklappt: {error}")
    if sys.platform == "win32":
        input("\nEnter drücken zum Schließen …")
