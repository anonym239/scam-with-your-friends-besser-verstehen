"""Mikrofon-Aufnahme (16 kHz, mono) und das Erkennen von Sprechpausen für den Dauer-Modus."""
import collections
import threading

import numpy as np

RATE = 16000          # Whisper will 16 kHz
FRAME = 480           # 30 ms


def input_devices():
    """[(Index, Name)] aller Eingabegeräte, ohne Doppelte."""
    import sounddevice as sd
    apis = sd.query_hostapis()
    preferred = next((i for i, api in enumerate(apis) if "MME" in api["name"]), None)
    result, seen = [], set()
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] < 1:
            continue
        if preferred is not None and device["hostapi"] != preferred:
            continue
        name = device["name"].strip()
        if name in seen or "Mapper" in name or "Primärer" in name:
            continue
        seen.add(name)
        result.append((index, name))
    return result


def find_device(wanted):
    """Index des ersten Geräts, dessen Name `wanted` enthält; None = Windows-Standard."""
    if not wanted:
        return None
    for index, name in input_devices():
        if wanted.lower() in name.lower():
            return index
    return None


def resample(samples, rate, target=RATE):
    if rate == target or not len(samples):
        return samples
    count = int(round(len(samples) * target / rate))
    return np.interp(np.linspace(0, len(samples) - 1, count), np.arange(len(samples)), samples).astype(samples.dtype)


def rms(samples):
    if not len(samples):
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))


class Recorder:
    """Läuft ständig mit. Hält die letzten 0,4 s vor, damit das erste Wort beim Tastendruck nicht fehlt."""

    def __init__(self, device=None, on_frame=None):
        self.device = device
        self.on_frame = on_frame          # für den Dauer-Modus: bekommt jeden Block (int16)
        self.level = 0.0
        self._stream = None
        self._lock = threading.Lock()
        self._preroll = collections.deque(maxlen=int(0.4 * RATE / FRAME) + 1)
        self._capture = None
        self.device_name = ""

    def start(self):
        import sounddevice as sd
        info = sd.query_devices(self.device, "input")
        self.device_name = info["name"]
        rate = RATE
        try:
            sd.check_input_settings(device=self.device, channels=1, samplerate=RATE, dtype="int16")
        except Exception:
            rate = int(info["default_samplerate"])   # Gerät kann kein 16 kHz: selbst umrechnen

        def callback(data, frames, time_info, status):
            samples = resample(data[:, 0].copy(), rate)
            self.level = rms(samples)
            with self._lock:
                self._preroll.append(samples)
                if self._capture is not None:
                    self._capture.append(samples)
            if self.on_frame:
                self.on_frame(samples)

        self._stream = sd.InputStream(device=self.device, channels=1, samplerate=rate, dtype="int16",
                                      blocksize=int(FRAME * rate / RATE), callback=callback)
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def begin(self):
        with self._lock:
            self._capture = list(self._preroll)

    def end(self):
        """Gibt die Aufnahme seit begin() zurück (int16)."""
        with self._lock:
            chunks, self._capture = self._capture or [], None
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)


class Segmenter:
    """Zerlegt einen Dauer-Strom in Sätze: Sprechen beginnt über der Schwelle, endet nach `pause` Sekunden Stille.

    threshold=None: misst das Grundrauschen selbst ein und nimmt das Dreifache (mindestens 250).
    """

    def __init__(self, pause=0.8, threshold=None, min_speech=0.35, max_length=25.0):
        self.pause_frames = max(1, int(pause * RATE / FRAME))
        self.fixed = threshold
        self.min_frames = int(min_speech * RATE / FRAME)
        self.max_frames = int(max_length * RATE / FRAME)
        self.noise = None
        self._pre = collections.deque(maxlen=int(0.3 * RATE / FRAME) + 1)
        self._buffer = None
        self._voiced = 0
        self._silent = 0
        self._pending = np.zeros(0, dtype=np.int16)

    @property
    def threshold(self):
        if self.fixed:
            return self.fixed
        return max(250.0, (self.noise or 0.0) * 3.0)

    @property
    def speaking(self):
        return self._buffer is not None

    def feed(self, samples):
        """Nimmt beliebig lange Stücke an; gibt fertige Sätze zurück (Liste von int16-Arrays)."""
        done = []
        self._pending = np.concatenate([self._pending, samples])
        while len(self._pending) >= FRAME:
            frame, self._pending = self._pending[:FRAME], self._pending[FRAME:]
            result = self._frame(frame)
            if result is not None:
                done.append(result)
        return done

    def _frame(self, frame):
        level = rms(frame)
        loud = level > self.threshold
        if self._buffer is None:
            if not loud:
                self.noise = level if self.noise is None else self.noise * 0.95 + level * 0.05
                self._pre.append(frame)
                return None
            self._buffer = list(self._pre) + [frame]
            self._pre.clear()
            self._voiced, self._silent = 1, 0
            return None
        self._buffer.append(frame)
        if loud:
            self._voiced += 1
            self._silent = 0
        else:
            self._silent += 1
        if self._silent >= self.pause_frames or len(self._buffer) >= self.max_frames:
            buffer, voiced = self._buffer, self._voiced
            self._buffer = None
            if voiced >= self.min_frames:
                return np.concatenate(buffer)
        return None
