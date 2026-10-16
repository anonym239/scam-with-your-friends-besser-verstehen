"""Die Sprechhilfe: hört dir auf Deutsch zu und tippt genau das, was du gesagt hast, ins Spiel.

Läuft unsichtbar im Hintergrund, nur ein Mikrofon-Symbol unten rechts in der Taskleiste. Alles passiert auf dem
eigenen PC: keine KI im Internet, kein Konto, kein API-Schlüssel, keine Cloud.
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
_log_lock = threading.Lock()


def _beep(freq, ms, enabled):
    if not enabled or sys.platform != "win32":
        return
    import winsound
    threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()


def log_path():
    return os.path.join(config.data_dir(), "protokoll.txt")


def log(message):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {message}"
    with _log_lock:
        try:
            with open(log_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
    if sys.stdout is not None:
        try:
            print(line, flush=True)
        except Exception:
            pass


def _history(line):
    try:
        with open(os.path.join(config.data_dir(), "verlauf.txt"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {line}\n")
    except OSError:
        pass


def _open_in_editor(path):
    if sys.platform == "win32":
        subprocess.Popen(["notepad.exe", path])
    else:
        print(path)


def _message_box(message, title="Sprechhilfe"):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x40 | 0x10000)
    else:
        print(message)


class App:
    def __init__(self, settings, on_state=None):
        self.s = settings
        self.on_state = on_state or (lambda **kw: None)
        self.talk_keys = keys.parse_hotkeys(settings.sprechtaste)
        self.pause_keys = keys.parse_hotkeys(settings.pausetaste)
        self.chat_key = keys.parse_combo(settings.chattaste) if settings.chattaste.strip() else ()
        self.send_key = keys.parse_combo(settings.absendetaste) if settings.absendetaste.strip() else ()
        for combo in (self.chat_key, self.send_key):
            if keys.is_mouse(combo):
                raise keys.KeyError_("Maustasten gehen nicht als Chat- oder Absendetaste")
        self.paused = False
        self.ready = False
        self.recording = False
        self.jobs = queue.Queue()
        self.recognizer = Recognizer(settings.modell, settings.geraet, settings.sprache, settings.wichtige_woerter)
        threshold = None if settings.schwelle.lower() == "auto" else float(settings.schwelle.replace(",", "."))
        self.segmenter = audio.Segmenter(pause=settings.satzpause, threshold=threshold)
        self.recorder = audio.Recorder(audio.find_device(settings.mikrofon),
                                       on_frame=self._on_frame if settings.modus == "immer" else None)

    def how_to(self):
        if self.s.modus == "halten":
            return f"Halte {self.s.sprechtaste} gedrückt und sprich. Loslassen = Text ins Spiel."
        if self.s.modus == "umschalten":
            return f"Drück {self.s.sprechtaste}, sprich, nochmal drücken = Text ins Spiel."
        return "Sprich einfach. Nach jeder kurzen Pause kommt der Satz ins Spiel."

    def _idle_state(self):
        if self.paused:
            self.on_state(state="pause", status=f"Pause ({self.s.pausetaste} = weiter)")
        else:
            self.on_state(state="bereit", status=self.how_to())

    def toggle_pause(self):
        self.paused = not self.paused
        if self.recording:
            self.recorder.end()
            self.recording = False
        log("Pause an." if self.paused else "Pause aus.")
        _beep(500 if self.paused else 900, 120, self.s.toene)
        if self.ready:
            self._idle_state()

    # ---- Aufnahme -------------------------------------------------------------------------------------------
    def _on_frame(self, samples):
        if self.paused or not self.ready:
            return
        was = self.segmenter.speaking
        for sentence in self.segmenter.feed(samples):
            self.jobs.put(sentence)
        if self.segmenter.speaking and not was:
            self.on_state(state="aufnahme", status="Ich höre …")

    # ---- Erkennen und Tippen (eigener Thread, damit die Taste nie hängt) -------------------------------------
    def _worker(self):
        while True:
            samples = self.jobs.get()
            self.on_state(state="erkennt", status="Erkenne …")
            try:
                started = time.monotonic()
                spoken = self.recognizer.transcribe(samples)
                result = text.finish(spoken, self.s.ersetzungen, self.s.punkt_weglassen)
                if not result:
                    log("(nichts verstanden)")
                else:
                    log(f"Verstanden ({time.monotonic() - started:.1f} s): {result}")
                    self._deliver(result)
                    self.on_state(last=result)
            except Exception as error:
                log(f"Fehler: {error}")
            if self.jobs.empty() and not self.recording:
                self._idle_state()

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
        self.on_state(state="laden", status="Lade Spracherkennung …")
        self.recognizer.load(lambda m: (log(m), self.on_state(status=m[:110])))
        log(f"Spracherkennung bereit: {self.recognizer.description}")
        self.recorder.start()
        log(f"Mikrofon: {self.recorder.device_name}")
        threading.Thread(target=self._worker, name="Erkennung", daemon=True).start()
        self.ready = True
        log(self.how_to())
        self._idle_state()
        _beep(880, 80, self.s.toene)

        talk_was = pause_was = False
        while True:
            time.sleep(0.01)
            pause_now = keys.any_down(self.pause_keys)
            if pause_now and not pause_was:
                self.toggle_pause()
            pause_was = pause_now
            if self.paused or self.s.modus == "immer":
                continue

            talk_now = keys.any_down(self.talk_keys)
            if self.s.modus == "halten":
                start, stop = talk_now and not talk_was, self.recording and not talk_now
            else:  # umschalten
                pressed = talk_now and not talk_was
                start, stop = pressed and not self.recording, pressed and self.recording
            talk_was = talk_now

            if start:
                self.recorder.begin()
                self.recording = True
                self.on_state(state="aufnahme", status="Aufnahme … sprich jetzt")
                _beep(1000, 60, self.s.toene)
            elif stop:
                time.sleep(0.25)          # das letzte Wort noch mitnehmen
                samples = self.recorder.end()
                self.recording = False
                _beep(700, 60, self.s.toene)
                if len(samples) < audio.RATE * 0.3:
                    log("(zu kurz)")
                    self._idle_state()
                else:
                    self.jobs.put(samples)


# ---- Start -----------------------------------------------------------------------------------------------------
_mutex = None


def _single_instance(wait):
    """Nur eine Sprechhilfe gleichzeitig (sonst würde doppelt getippt)."""
    global _mutex
    if sys.platform != "win32":
        return True
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    deadline = time.monotonic() + (8 if wait else 0)
    while True:
        handle = kernel32.CreateMutexW(None, False, "Local\\Sprechhilfe-SWYF")
        if ctypes.get_last_error() != 183:      # ERROR_ALREADY_EXISTS
            _mutex = handle
            return True
        kernel32.CloseHandle(handle)
        if time.monotonic() > deadline:
            return False
        time.sleep(0.3)


def _restart_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--neustart"]
    return [sys.executable, "-m", "sprechhilfe", "--neustart"]


def _show_mics():
    path = os.path.join(config.data_dir(), "mikrofone.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Deine Mikrofone. Einen Teil des Namens bei  mikrofon =  in den Einstellungen eintragen.\n\n")
        for _, name in audio.input_devices():
            f.write(f"  {name}\n")
    _open_in_editor(path)


def _selftest():
    """Für den automatischen Build: lädt das kleinste Modell und erkennt Stille (prüft, dass alles eingepackt ist)."""
    out = os.path.join(config.data_dir(), "selbsttest.txt")
    try:
        import numpy as np
        import sounddevice  # noqa: F401
        from . import tray
        tray.draw_icon("bereit")
        import pystray  # noqa: F401
        keys.parse_hotkeys("F8, maus4, strg+t, num+")
        recognizer = Recognizer("tiny", "cpu", "de")
        recognizer.load(lambda m: None)
        recognizer.transcribe(np.zeros(16000, dtype=np.int16))
        message, code = "OK", 0
    except Exception as error:
        message, code = f"FEHLER: {error!r}", 1
    with open(out, "w", encoding="utf-8") as f:
        f.write(message + "\n")
    return code


def main():
    # Ohne Konsolenfenster gibt es kein stdout/stderr; Fortschrittsbalken beim Download würden sonst abstürzen.
    if sys.stdout is None or sys.stderr is None:
        devnull = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    if "--selbsttest" in sys.argv:
        sys.exit(_selftest())
    if "--einstellungen" in sys.argv:
        config.load()
        _open_in_editor(config.ini_path())
        return

    if not _single_instance(wait="--neustart" in sys.argv):
        _message_box("Die Sprechhilfe läuft schon.\n\nDu findest sie unten rechts in der Taskleiste "
                     "(Mikrofon-Symbol, eventuell hinter dem Pfeil ^).")
        return

    with open(log_path(), "w", encoding="utf-8") as f:
        f.write(f"Sprechhilfe {VERSION}\n")

    try:
        settings = config.load()
        tray_ui = None
        app = None
        from .tray import Tray

        def on_state(state=None, status=None, last=None):
            if tray_ui:
                tray_ui.set(state, status, last)

        app = App(settings, on_state)

        def quit_app():
            tray_ui.stop()
            os._exit(0)

        def restart():
            subprocess.Popen(_restart_command())
            quit_app()

        tray_ui = Tray(on_pause=app.toggle_pause, on_settings=lambda: _open_in_editor(config.ini_path()),
                       on_log=lambda: _open_in_editor(log_path()), on_mics=_show_mics, on_restart=restart,
                       on_quit=quit_app, is_paused=lambda: app.paused)
    except keys.KeyError_ as error:
        _message_box(f"Unbekannte Taste in den Einstellungen: {error}\n\nBitte in\n{config.ini_path()}\nkorrigieren.")
        return
    except Exception as error:
        _message_box(f"Die Sprechhilfe konnte nicht starten:\n\n{error}")
        return

    def background():
        first = not os.path.isdir(os.path.join(config.data_dir(), "modelle")) or \
            not os.listdir(os.path.join(config.data_dir(), "modelle"))
        if first:
            tray_ui.notify("Erster Start: Die Spracherkennung wird einmalig heruntergeladen (ein paar Hundert MB). "
                           "Das Symbol wird grün, sobald es losgeht.")
        try:
            app.run()
        except Exception as error:
            log(f"Fehler: {error}")
            tray_ui.set("fehler", f"Fehler: {error}"[:110])
            _message_box(f"Die Sprechhilfe hat ein Problem:\n\n{error}\n\nDetails stehen im Protokoll "
                         f"(Rechtsklick aufs Symbol).")

    def announce_when_ready():
        while not app.ready:
            time.sleep(0.5)
        tray_ui.notify(f"Bereit! {app.how_to()}")

    def setup():
        threading.Thread(target=background, name="Sprechhilfe", daemon=True).start()
        threading.Thread(target=announce_when_ready, daemon=True).start()

    tray_ui.run(setup)
