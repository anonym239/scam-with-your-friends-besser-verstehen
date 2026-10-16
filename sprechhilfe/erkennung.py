"""Spracherkennung mit Whisper (faster-whisper), komplett auf dem eigenen PC.

Das Modell wird beim ersten Start einmal heruntergeladen und liegt dann in %APPDATA%\\Sprechhilfe\\modelle.
Danach braucht die Erkennung kein Internet mehr; nichts von dem, was du sagst, verlässt den PC.
"""
import os

import numpy as np

from .config import data_dir

RATE_SECOND = 16000

# Whisper "hört" bei Stille oder Rauschen gern diese Sätze aus Fernseh-Untertiteln.
_HALLUCINATIONS = {
    "untertitel im auftrag des zdf", "untertitel der amara.org-community", "untertitelung im auftrag des zdf",
    "untertitel im auftrag des zdf, 2017", "untertitelung im auftrag des zdf, 2017", "untertitelung des zdf, 2020",
    "vielen dank fürs zuschauen", "danke fürs zuschauen", "vielen dank für's zuschauen",
    "thank you for watching", "thanks for watching", "you", "untertitel von stephanie geiges",
    "copyright wdr 2021", "swr 2020", "mehr infos auf www.swr.de",
}


def is_hallucination(text):
    plain = text.lower().strip(" .!?,…")
    if not plain:
        return True
    if plain in _HALLUCINATIONS:
        return True
    return "untertitel" in plain and ("zdf" in plain or "amara" in plain or "community" in plain)


def pick_language(probs, main="de", allowed=()):
    """Welche Sprache gesprochen wurde, aus Whispers Wahrscheinlichkeiten [(Sprache, p), …] (absteigend).

    Sicher erkannt (p >= 0,6) -> diese Sprache. Unsicher, aber die Hauptsprache ist im Rennen (p >= 0,1) -> die
    Hauptsprache. Sonst die wahrscheinlichste. `allowed` beschränkt die Auswahl.
    """
    if allowed:
        probs = [(lang, p) for lang, p in probs if lang in allowed]
        if not probs:
            return main
    if not probs:
        return main
    top, p_top = probs[0]
    if top == main or p_top >= 0.6:
        return top
    p_main = dict(probs).get(main, 0.0)
    return main if p_main >= 0.1 else top


def loudness_normalize(samples):
    """Leise Mikrofone anheben (Whisper versteht leise Aufnahmen schlechter). float32 rein, float32 raus."""
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if 0.02 < peak < 0.5:
        samples = samples * (0.7 / peak)
    return samples.astype(np.float32)


_MODEL_FILES = ("model.bin", "config.json", "tokenizer.json")


def model_folder(name, cache, log=print):
    """Ordner mit dem Modell. Lädt es beim ersten Mal herunter, als normale Dateien (ohne Windows-Verknüpfungen,
    die ohne Entwicklermodus mit „WinError 1314“ scheitern). Ist es schon da, wird das Internet nicht gebraucht."""
    folder = os.path.join(cache, name)
    if all(os.path.isfile(os.path.join(folder, f)) for f in _MODEL_FILES):
        return folder
    from faster_whisper.utils import download_model
    log(f"Lade das Modell „{name}“ herunter (nur beim ersten Mal, bitte warten) …")
    download_model(name, output_dir=folder)
    if not all(os.path.isfile(os.path.join(folder, f)) for f in _MODEL_FILES):
        raise OSError("Download unvollständig")
    return folder


def remove_old_cache(cache):
    """Räumt den alten Zwischenspeicher früherer Versionen weg (models--…), der viel Platz belegen kann."""
    import shutil
    for entry in os.listdir(cache):
        if entry.startswith("models--") or entry == ".locks":
            shutil.rmtree(os.path.join(cache, entry), ignore_errors=True)


def auto_model(device):
    if device == "cuda":
        return "large-v3-turbo"
    return "medium" if (os.cpu_count() or 4) >= 12 else "small"


class Recognizer:
    def __init__(self, model="auto", device="auto", language="auto", hotwords="", main_language="de",
                 allowed_languages=""):
        self.model_name = model
        self.device = device
        self.language = (language or "auto").strip().lower()
        self.main = (main_language or "de").strip().lower()
        self.allowed = tuple(x.strip().lower() for x in allowed_languages.split(",") if x.strip())
        self.hotwords = hotwords.strip() or None
        self.model = None
        self.description = ""
        self.last_language = ""

    def _attempts(self):
        from . import gpu
        wanted = self.model_name
        cpu = ("cpu", "int8", auto_model("cpu") if wanted == "auto" else wanted)
        cuda = ("cuda", "int8_float16", auto_model("cuda") if wanted == "auto" else wanted)
        if self.device == "cpu":
            return [cpu]
        if self.device == "cuda":
            return [cuda]
        return [cuda, cpu] if gpu.has_nvidia() else [cpu]

    def load(self, log=print):
        from . import gpu
        gpu.activate()
        from faster_whisper import WhisperModel
        cache = os.path.join(data_dir(), "modelle")
        os.makedirs(cache, exist_ok=True)
        last = None
        for device, compute, name in self._attempts():
            where = "Grafikkarte" if device == "cuda" else "Prozessor"
            try:
                path = model_folder(name, cache, log)
            except Exception as error:
                raise RuntimeError(f"Das Modell „{name}“ konnte nicht heruntergeladen werden: {error}. "
                                   "Bitte Internetverbindung und freien Speicherplatz prüfen.") from error
            try:
                log(f"Starte Spracherkennung „{name}“ auf {where} …")
                model = WhisperModel(path, device=device, compute_type=compute,
                                     cpu_threads=max(2, (os.cpu_count() or 4) - 2))
                # Probelauf: fehlen CUDA-Bibliotheken, merkt man das erst hier.
                list(model.transcribe(np.zeros(RATE_SECOND, dtype=np.float32), language=self.main)[0])
                self.model = model
                self.description = f"{name} auf {where}"
                remove_old_cache(cache)
                return
            except Exception as error:
                last = error
                if device == "cuda":
                    log(f"  Grafikkarte geht nicht ({error}), nehme den Prozessor.")
        raise RuntimeError(f"Spracherkennung konnte nicht laden: {last}")

    def detect(self, samples):
        if self.language != "auto":
            return self.language
        try:
            _, _, probs = self.model.detect_language(samples)
        except Exception:
            return self.main
        return pick_language(probs, self.main, self.allowed)

    def _run(self, samples, language, vad, strict):
        segments, info = self.model.transcribe(
            samples, language=language, beam_size=5, vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 700, "speech_pad_ms": 400} if vad else None,
            condition_on_previous_text=False, without_timestamps=True, hotwords=self.hotwords,
            # Im zweiten Versuch nichts als "Stille" verwerfen.
            no_speech_threshold=0.6 if strict else None, log_prob_threshold=-1.0 if strict else None)
        parts = []
        for segment in segments:
            if strict and segment.no_speech_prob > 0.9 and segment.avg_logprob < -1.0:
                continue
            text = segment.text.strip()
            if text and not is_hallucination(text):
                parts.append(text)
        return " ".join(" ".join(parts).split()), info.language

    def transcribe(self, samples, continuous=False):
        """int16- oder float32-Audio mit 16 kHz -> Text in der gesprochenen Sprache (nicht übersetzt).

        Kommt beim ersten Versuch nichts heraus, obwohl laut genug gesprochen wurde, folgt ein zweiter, großzügigerer
        Versuch (ohne Stille-Filter, Sprache frei). So gehen kaum noch Sätze verloren.
        """
        if samples.dtype != np.float32:
            samples = samples.astype(np.float32) / 32768.0
        if len(samples) < RATE_SECOND * 0.2:
            return ""
        loud_enough = float(np.sqrt(np.mean(samples ** 2))) > 0.005
        samples = loudness_normalize(samples)
        language = self.detect(samples)
        text, used = self._run(samples, language, vad=continuous, strict=True)
        if not text and loud_enough:
            retry_language = None if self.language == "auto" and not self.allowed else language
            text, used = self._run(samples, retry_language, vad=False, strict=False)
        self.last_language = used or language
        return text
