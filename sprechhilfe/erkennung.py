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


class Recognizer:
    def __init__(self, model="auto", device="auto", language="de", hotwords=""):
        self.model_name = model
        self.device = device
        self.language = language or None
        self.hotwords = hotwords.strip() or None
        self.model = None
        self.description = ""

    def _attempts(self):
        wanted = self.model_name
        if self.device == "cpu":
            return [("cpu", "int8", "small" if wanted == "auto" else wanted)]
        gpu = ("cuda", "int8_float16", "medium" if wanted == "auto" else wanted)
        if self.device == "cuda":
            return [gpu]
        return [gpu, ("cpu", "int8", "small" if wanted == "auto" else wanted)]

    def load(self, log=print):
        from faster_whisper import WhisperModel
        cache = os.path.join(data_dir(), "modelle")
        os.makedirs(cache, exist_ok=True)
        last = None
        for device, compute, name in self._attempts():
            try:
                log(f"Lade Spracherkennung „{name}“ auf {'Grafikkarte' if device == 'cuda' else 'Prozessor'} …"
                    " (beim ersten Mal wird das Modell einmalig heruntergeladen, bitte warten)")
                model = WhisperModel(name, device=device, compute_type=compute, download_root=cache,
                                     cpu_threads=max(2, (os.cpu_count() or 4) - 2))
                # Probelauf: fehlen CUDA-Bibliotheken, merkt man das erst hier.
                list(model.transcribe(np.zeros(RATE_SECOND, dtype=np.float32), language=self.language)[0])
                self.model = model
                self.description = f"{name} auf {'Grafikkarte' if device == 'cuda' else 'Prozessor'}"
                return
            except Exception as error:
                last = error
                if device == "cuda":
                    log("  Grafikkarte geht nicht (fehlende NVIDIA-CUDA-Bibliotheken?), nehme den Prozessor.")
        raise RuntimeError(f"Spracherkennung konnte nicht laden: {last}")

    def transcribe(self, samples):
        """int16- oder float32-Audio mit 16 kHz -> Text."""
        if samples.dtype != np.float32:
            samples = samples.astype(np.float32) / 32768.0
        if len(samples) < RATE_SECOND * 0.3:
            return ""
        segments, _ = self.model.transcribe(
            samples, language=self.language, beam_size=5, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}, condition_on_previous_text=False,
            without_timestamps=True, hotwords=self.hotwords)
        parts = []
        for segment in segments:
            if segment.no_speech_prob > 0.7 and segment.avg_logprob < -0.8:
                continue
            text = segment.text.strip()
            if text and not is_hallucination(text):
                parts.append(text)
        return " ".join(" ".join(parts).split())

