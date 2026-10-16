"""Die Sprechhilfe: hört dir zu und tippt genau das, was du gesagt hast, ins Spiel.

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

from . import audio, config, gpu, keys, text
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


def _message_box(message, title="Sprechhilfe", yes_no=False):
    """Zeigt eine Meldung. Mit yes_no: True bei „Ja“."""
    if sys.platform == "win32":
        import ctypes
        flags = 0x10000 | (0x20 | 0x04 if yes_no else 0x40)   # immer vorne; Frage- bzw. Info-Symbol
        return ctypes.windll.user32.MessageBoxW(None, message, title, flags) == 6
    print(message)
    return False


class App:
    def __init__(self, settings, on_state=None, on_notify=None):
        self.s = settings
        self.on_state = on_state or (lambda **kw: None)
        self.on_notify = on_notify or (lambda message: None)
        self.talk_keys = keys.parse_hotkeys(settings.sprechtaste)
        self.pause_keys = keys.parse_hotkeys(settings.pausetaste)
        self.field_keys = keys.parse_hotkeys(settings.feld_merken_taste)
        self.chat_key = keys.parse_combo(settings.chattaste) if settings.chattaste.strip() else ()
        self.send_key = keys.parse_combo(settings.absendetaste) if settings.absendetaste.strip() else ()
        for combo in (self.chat_key, self.send_key):
            if keys.is_mouse(combo):
                raise keys.KeyError_("Maustasten gehen nicht als Chat- oder Absendetaste")
        self.paused = False
        self.ready = False
        self.recording = False
        self.last_text = ""
        self.field = config.load_state().get("textfeld")     # gemerkte Stelle des Textfelds (Anteil x, y)
        self.jobs = queue.Queue()
        self._type_lock = threading.Lock()
        self.recognizer = Recognizer(settings.modell, settings.geraet, settings.sprache, settings.wichtige_woerter,
                                     settings.hauptsprache, settings.erlaubte_sprachen)
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

    def remember_field(self):
        """Merkt sich, wo im Spielfenster das Textfeld ist (Maus zeigt gerade darauf)."""
        position = keys.mouse_in_window()
        if not position or not (0 <= position[0] <= 1 and 0 <= position[1] <= 1):
            log("Textfeld merken ging nicht: Die Maus ist nicht im Fenster vorne.")
            _beep(300, 200, self.s.toene)
            return
        self.field = [round(position[0], 4), round(position[1], 4)]
        config.save_state(textfeld=self.field, textfeld_fenster=keys.foreground_title())
        log(f"Textfeld gemerkt ({keys.foreground_title()}): {self.field}")
        _beep(1500, 60, self.s.toene)
        _beep(1800, 60, self.s.toene)
        self.on_notify("Textfeld gemerkt. Ab jetzt klickt die Sprechhilfe vor jedem Satz selbst hinein.")

    def forget_field(self):
        self.field = None
        config.save_state(textfeld=None)
        log("Textfeld vergessen.")

    def retype_last(self):
        if self.last_text:
            # Kurz warten, damit nach dem Klick ins Menü das Spiel wieder vorne ist.
            threading.Thread(target=lambda: (time.sleep(1.5), self._deliver(self.last_text)), daemon=True).start()

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
                spoken = self.recognizer.transcribe(samples, continuous=self.s.modus == "immer")
                result = text.finish(spoken, self.s.ersetzungen, self.s.punkt_weglassen)
                if not result:
                    log("(nichts verstanden – bitte nochmal sagen)")
                    _beep(300, 150, self.s.toene)
                    self.on_state(status="Nicht verstanden – bitte nochmal sagen")
                else:
                    seconds = time.monotonic() - started
                    log(f"Verstanden [{self.recognizer.last_language}] ({seconds:.1f} s): {result}")
                    self.last_text = result
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
        with self._type_lock:
            title = keys.foreground_title()
            if self.s.nur_in_fenster and self.s.nur_in_fenster.lower() not in title.lower():
                log(f"  nicht getippt: das Spiel ist nicht vorne (vorne ist „{title}“)")
                self.on_notify(f"Nicht getippt, weil „{title}“ vorne ist. Text: {result}")
                return
            if self.field:
                keys.click_in_window(*self.field)
                time.sleep(self.s.wartezeit / 1000)
            if self.chat_key:
                keys.press(self.chat_key)
                time.sleep(self.s.wartezeit / 1000)
            if self.s.eingabe == "einfuegen":
                keys.paste_text(result)
            else:
                keys.type_text(result, self.s.tippverzoegerung)
            if self.send_key:
                time.sleep(self.s.absende_wartezeit / 1000)
                keys.press(self.send_key)
            _history(result)
            _beep(1200, 40, self.s.toene)

    # ---- Hauptschleife ---------------------------------------------------------------------------------------
    def run(self):
        self.on_state(state="laden", status="Lade Spracherkennung …")
        self.recognizer.load(lambda m: (log(m), self.on_state(status=m[:110])))
        log(f"Spracherkennung bereit: {self.recognizer.description}, Sprache: {self.s.sprache}")
        self.recorder.start()
        log(f"Mikrofon: {self.recorder.device_name}")
        if self.field:
            log(f"Gemerktes Textfeld: {self.field}")
        threading.Thread(target=self._worker, name="Erkennung", daemon=True).start()
        self.ready = True
        log(self.how_to())
        self._idle_state()
        _beep(880, 80, self.s.toene)

        talk_was = pause_was = field_was = False
        pressed_at = 0.0
        while True:
            time.sleep(0.01)
            pause_now = keys.any_down(self.pause_keys)
            if pause_now and not pause_was:
                self.toggle_pause()
            pause_was = pause_now
            field_now = keys.any_down(self.field_keys)
            if field_now and not field_was:
                self.remember_field()
            field_was = field_now
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
                pressed_at = time.monotonic()
                self.on_state(state="aufnahme", status="Aufnahme … sprich jetzt")
                _beep(1000, 60, self.s.toene)
            elif stop:
                time.sleep(0.35)          # das letzte Wort noch mitnehmen
                samples = self.recorder.end()
                self.recording = False
                _beep(700, 60, self.s.toene)
                if self.s.modus == "halten" and time.monotonic() - pressed_at < 0.5:
                    log("(Taste nur kurz angetippt – zum Sprechen gedrückt halten)")
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
    """Für den automatischen Build: prüft, dass alles eingepackt ist, und erkennt eine Testaufnahme."""
    out = os.path.join(config.data_dir(), "selbsttest.txt")
    lines = []
    try:
        import numpy as np
        import sounddevice  # noqa: F401
        import pystray  # noqa: F401
        from . import tray
        tray.draw_icon("bereit")
        keys.parse_hotkeys("F8, maus4, strg+t, num+")
        lines.append(f"Grafikkarte: {gpu.has_nvidia()}")
        recognizer = Recognizer(os.environ.get("SPRECHHILFE_TESTMODELL", "tiny"), "cpu", "auto")
        recognizer.load(lambda m: None)
        if recognizer.transcribe(np.zeros(16000, dtype=np.int16)):
            raise AssertionError("Stille wurde als Text erkannt")
        # Echte Sprachaufnahmen (vom Build erzeugt): SPRECHHILFE_TESTWAV = "de=pfad.wav;en=pfad.wav"
        for entry in filter(None, os.environ.get("SPRECHHILFE_TESTWAV", "").split(";")):
            expected, path = entry.split("=", 1)
            import wave
            with wave.open(path) as w:
                rate, channels = w.getframerate(), w.getnchannels()
                data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            if channels > 1:
                data = data[::channels]
            result = recognizer.transcribe(audio.resample(data, rate))
            lines.append(f"Testaufnahme {expected}: {result!r} [erkannt: {recognizer.last_language}]")
            if not result:
                raise AssertionError(f"Testaufnahme {expected} wurde nicht erkannt")
            if recognizer.last_language != expected:
                raise AssertionError(f"Testaufnahme {expected} als {recognizer.last_language} erkannt")
        message, code = "OK", 0
    except Exception as error:
        message, code = f"FEHLER: {error!r}", 1
        import traceback
        lines.append(traceback.format_exc())
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join([message] + lines) + "\n")
    return code


def _setup_gpu(settings, tray_ui):
    """Beim ersten Start mit NVIDIA-Karte einmal fragen, ob sie für genauere Erkennung eingerichtet werden soll."""
    if settings.geraet == "cpu" or gpu.installed() or not gpu.has_nvidia():
        return
    if config.load_state().get("grafikkarte_gefragt"):
        return
    config.save_state(grafikkarte_gefragt=True)
    if _message_box("Du hast eine NVIDIA-Grafikkarte.\n\nSoll die Sprechhilfe sie nutzen? Dann versteht sie dich "
                    "deutlich genauer (größeres Modell) und schneller.\n\nDafür wird einmalig ca. 1,2 GB von NVIDIA "
                    "heruntergeladen (braucht ca. 2 GB Platz). Danach läuft alles offline.\n\n"
                    "Später geht das auch per Rechtsklick aufs Symbol → „Grafikkarte einrichten“.",
                    yes_no=True):
        _install_gpu(tray_ui)


def _install_gpu(tray_ui):
    tray_ui.set("laden", "Grafikkarte einrichten …")
    try:
        gpu.install(lambda status: tray_ui.set(status=status))
        log("Grafikkarte eingerichtet.")
        return True
    except Exception as error:
        log(f"Grafikkarte einrichten fehlgeschlagen: {error}")
        _message_box(f"Die Grafikkarte konnte nicht eingerichtet werden:\n\n{error}\n\n"
                     "Die Sprechhilfe läuft trotzdem, dann eben auf dem Prozessor.")
        return False


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

    holder = {}

    def on_state(state=None, status=None, last=None):
        if "tray" in holder:
            holder["tray"].set(state, status, last)

    def on_notify(message):
        if "tray" in holder:
            holder["tray"].notify(message)

    try:
        settings = config.load()
        app = App(settings, on_state, on_notify)
        from .tray import Tray

        def quit_app():
            holder["tray"].stop()
            os._exit(0)

        def restart():
            subprocess.Popen(_restart_command())
            quit_app()

        def setup_gpu_from_menu():
            def work():
                if _install_gpu(holder["tray"]):
                    _message_box("Grafikkarte eingerichtet. Die Sprechhilfe startet jetzt neu.")
                    restart()
            threading.Thread(target=work, daemon=True).start()

        holder["tray"] = Tray(
            on_pause=app.toggle_pause, on_settings=lambda: _open_in_editor(config.ini_path()),
            on_log=lambda: _open_in_editor(log_path()), on_mics=_show_mics, on_restart=restart, on_quit=quit_app,
            is_paused=lambda: app.paused, on_retype=app.retype_last, on_forget_field=app.forget_field,
            has_field=lambda: bool(app.field), on_setup_gpu=setup_gpu_from_menu,
            gpu_offer=lambda: holder.get("gpu_offer", False))
    except keys.KeyError_ as error:
        _message_box(f"Unbekannte Taste in den Einstellungen: {error}\n\nBitte in\n{config.ini_path()}\nkorrigieren.")
        return
    except Exception as error:
        _message_box(f"Die Sprechhilfe konnte nicht starten:\n\n{error}")
        return
    tray_ui = holder["tray"]

    def background():
        try:
            _setup_gpu(settings, tray_ui)
            holder["gpu_offer"] = settings.geraet != "cpu" and not gpu.installed() and gpu.has_nvidia()
            models = os.path.join(config.data_dir(), "modelle")
            if not os.path.isdir(models) or not os.listdir(models):
                tray_ui.notify("Erster Start: Die Spracherkennung wird einmalig heruntergeladen (einige Hundert MB "
                               "bis 1,6 GB). Das Symbol wird grün, sobald es losgeht.")
            app.run()
        except Exception as error:
            log(f"Fehler: {error}")
            tray_ui.set("fehler", f"Fehler: {error}"[:110])
            _message_box(f"Die Sprechhilfe hat ein Problem:\n\n{error}\n\nDetails stehen im Protokoll "
                         f"(Rechtsklick aufs Symbol).")

    def announce_when_ready():
        while not app.ready:
            time.sleep(0.5)
        hint = "" if app.field else f" Tipp: Maus aufs Textfeld im Spiel und {settings.feld_merken_taste} drücken."
        tray_ui.notify(f"Bereit ({app.recognizer.description}). {app.how_to()}{hint}")

    def setup():
        threading.Thread(target=background, name="Sprechhilfe", daemon=True).start()
        threading.Thread(target=announce_when_ready, daemon=True).start()

    tray_ui.run(setup)
