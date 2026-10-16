import unittest

import numpy as np

from sprechhilfe import audio, config, keys, text
from sprechhilfe.erkennung import is_hallucination


class KeysTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(keys.parse_hotkeys("F8, maus4"), [(0x77,), (0x05,)])
        self.assertEqual(keys.parse_combo("strg+t"), (0x11, 0x54))
        self.assertEqual(keys.parse_combo("Strg + Leertaste"), (0x11, 0x20))
        self.assertEqual(keys.parse_combo("num+"), (0x6B,))
        self.assertEqual(keys.parse_combo("+"), (0xBB,))
        self.assertEqual(keys.parse_combo("strg++"), (0x11, 0xBB))
        self.assertEqual(keys.parse_hotkeys(""), [])
        self.assertTrue(keys.is_mouse((0x05,)))

    def test_unknown(self):
        with self.assertRaises(keys.KeyError_):
            keys.parse_combo("gibtsnicht")


class ConfigTest(unittest.TestCase):
    def test_defaults_file(self):
        s = config.parse(config.DEFAULT_INI)
        self.assertEqual(s.modus, "halten")
        self.assertEqual(s.sprechtaste, "F8, maus4")
        self.assertEqual(s.chattaste, "")
        self.assertEqual(s.absendetaste, "enter")
        self.assertTrue(s.toene)
        self.assertEqual(s.ersetzungen, {})
        keys.parse_hotkeys(s.sprechtaste)
        keys.parse_hotkeys(s.pausetaste)

    def test_values(self):
        s = config.parse("[Sprechhilfe]\nmodus = IMMER\nsatzpause = 1,5\ntoene = nein\ntippverzoegerung = x\n"
                         "eingabe = einfügen\n[Ersetzungen]\npay pal = PayPal\n")
        self.assertEqual(s.modus, "immer")
        self.assertEqual(s.satzpause, 1.5)
        self.assertFalse(s.toene)
        self.assertEqual(s.tippverzoegerung, 8)
        self.assertEqual(s.eingabe, "einfuegen")
        self.assertEqual(s.ersetzungen, {"pay pal": "PayPal"})

    def test_bad_mode(self):
        self.assertEqual(config.parse("[Sprechhilfe]\nmodus = quatsch\n").modus, "halten")


class TextTest(unittest.TestCase):
    def test_replacements(self):
        r = {"pay pal": "PayPal", "spar kasse": "Sparkasse"}
        self.assertEqual(text.finish("Zahlen Sie mit  Pay Pal bei der Spar Kasse.", r),
                         "Zahlen Sie mit PayPal bei der Sparkasse.")
        self.assertEqual(text.apply_replacements("Paypalkonto", {"paypal": "X"}), "Paypalkonto")

    def test_period(self):
        self.assertEqual(text.finish("Hallo.", drop_period=True), "Hallo")
        self.assertEqual(text.finish("Hallo?", drop_period=True), "Hallo?")
        self.assertEqual(text.finish("Hallo.", drop_period=False), "Hallo.")

    def test_hallucination(self):
        self.assertTrue(is_hallucination("Untertitel im Auftrag des ZDF, 2018"))
        self.assertTrue(is_hallucination(" . "))
        self.assertFalse(is_hallucination("Guten Tag, hier ist Ihre Bank."))
        self.assertFalse(is_hallucination("Tschüss!"))


class SegmenterTest(unittest.TestCase):
    def _tone(self, seconds, amplitude):
        t = np.arange(int(seconds * audio.RATE)) / audio.RATE
        return (np.sin(2 * np.pi * 220 * t) * amplitude).astype(np.int16)

    def test_two_sentences(self):
        seg = audio.Segmenter(pause=0.5)
        quiet = (np.random.default_rng(1).normal(0, 30, audio.RATE)).astype(np.int16)
        stream = [quiet, self._tone(1.0, 5000), quiet, self._tone(0.8, 5000), quiet]
        found = []
        for chunk in stream:
            for i in range(0, len(chunk), 1000):   # in ungeraden Stücken wie vom Mikrofon
                found += seg.feed(chunk[i:i + 1000])
        self.assertEqual(len(found), 2)
        self.assertGreater(len(found[0]), audio.RATE * 1.0)

    def test_click_is_ignored(self):
        seg = audio.Segmenter(pause=0.3)
        quiet = np.zeros(audio.RATE, dtype=np.int16)
        self.assertEqual(seg.feed(np.concatenate([quiet, self._tone(0.06, 8000), quiet])), [])

    def test_resample(self):
        samples = np.zeros(48000, dtype=np.int16)
        self.assertEqual(len(audio.resample(samples, 48000)), 16000)


if __name__ == "__main__":
    unittest.main()


class AppTest(unittest.TestCase):
    def test_worker_delivers_and_reports(self):
        import threading
        from unittest import mock
        from sprechhilfe import app as app_module
        settings = config.parse(config.DEFAULT_INI + "pay pal = PayPal\n")
        states = []
        a = app_module.App(settings, on_state=lambda **kw: states.append(kw))
        a.recognizer.transcribe = lambda samples, continuous=False: "Bitte zahlen Sie mit pay pal."
        typed = []
        with mock.patch.object(app_module.keys, "type_text", lambda t, d: typed.append(t)), \
                mock.patch.object(app_module, "_history", lambda line: None):
            threading.Thread(target=a._worker, daemon=True).start()
            a.jobs.put(np.zeros(16000, dtype=np.int16))
            for _ in range(100):
                if typed and any(s.get("state") == "bereit" for s in states):
                    break
                import time
                time.sleep(0.02)
        self.assertEqual(typed, ["Bitte zahlen Sie mit PayPal."])
        self.assertIn({"last": "Bitte zahlen Sie mit PayPal."}, states)

    def test_pause_blocks_typing(self):
        from unittest import mock
        from sprechhilfe import app as app_module
        a = app_module.App(config.parse(config.DEFAULT_INI))
        a.toggle_pause()
        with mock.patch.object(app_module.keys, "type_text") as typer:
            a._deliver("Hallo")
        typer.assert_not_called()


class FieldTest(unittest.TestCase):
    def test_click_before_typing_and_send_after(self):
        from unittest import mock
        from sprechhilfe import app as app_module
        a = app_module.App(config.parse(config.DEFAULT_INI))
        a.field = [0.5, 0.9]
        calls = []
        with mock.patch.object(app_module.keys, "click_in_window", lambda x, y: calls.append(("klick", x, y))), \
                mock.patch.object(app_module.keys, "type_text", lambda t, d: calls.append(("tippe", t))), \
                mock.patch.object(app_module.keys, "press", lambda combo: calls.append(("taste", combo))), \
                mock.patch.object(app_module, "_history", lambda line: None), \
                mock.patch.object(app_module.time, "sleep", lambda s: None):
            a._deliver("Hallo")
        self.assertEqual(calls, [("klick", 0.5, 0.9), ("tippe", "Hallo"), ("taste", (0x0D,))])


class MigrationTest(unittest.TestCase):
    def test_old_file_keeps_user_values(self):
        old = ("[Sprechhilfe]\nsprache = de\nmodell = medium\ntippverzoegerung = 4\nsprechtaste = maus5\n"
               "[Ersetzungen]\npay pal = PayPal\n")
        s = config.parse(config.migrate(old))
        self.assertEqual(s.sprache, "auto")          # alter Standard -> neuer Standard
        self.assertEqual(s.tippverzoegerung, 8)
        self.assertEqual(s.modell, "medium")         # selbst geändert -> bleibt
        self.assertEqual(s.sprechtaste, "maus5")
        self.assertEqual(s.ersetzungen, {"pay pal": "PayPal"})
        self.assertEqual(s.feld_merken_taste, "F10")


class LanguageTest(unittest.TestCase):
    def test_pick(self):
        from sprechhilfe.erkennung import pick_language
        self.assertEqual(pick_language([("en", 0.9), ("de", 0.05)]), "en")       # sicher Englisch
        self.assertEqual(pick_language([("nl", 0.45), ("de", 0.4)]), "de")       # unsicher -> Hauptsprache
        self.assertEqual(pick_language([("tr", 0.5), ("az", 0.3)]), "tr")        # Deutsch nicht im Rennen
        self.assertEqual(pick_language([("nl", 0.9), ("de", 0.05), ("en", 0.04)], allowed=("de", "en")), "de")
        self.assertEqual(pick_language([]), "de")


class FakeSegment:
    def __init__(self, text, no_speech=0.1, logprob=-0.3):
        self.text, self.no_speech_prob, self.avg_logprob = text, no_speech, logprob


class FakeInfo:
    def __init__(self, language):
        self.language = language


class FakeModel:
    """Tut so, als wäre es Whisper: erster Versuch leer, zweiter Versuch mit Text."""
    def __init__(self, first, second, detected=(("de", 0.9),)):
        self.calls = []
        self.first, self.second, self.detected = first, second, list(detected)

    def detect_language(self, samples):
        return self.detected[0][0], self.detected[0][1], self.detected

    def transcribe(self, samples, **kw):
        self.calls.append(kw)
        segs = self.first if len(self.calls) == 1 else self.second
        return iter(segs), FakeInfo(kw.get("language") or "de")


class RecognizerTest(unittest.TestCase):
    def _speech(self):
        t = np.arange(16000) / 16000
        return (np.sin(2 * np.pi * 200 * t) * 6000).astype(np.int16)

    def test_retry_when_first_pass_is_empty(self):
        from sprechhilfe.erkennung import Recognizer
        r = Recognizer(language="auto")
        r.model = FakeModel([], [FakeSegment("Hallo, hier ist die Bank.")])
        self.assertEqual(r.transcribe(self._speech()), "Hallo, hier ist die Bank.")
        self.assertEqual(len(r.model.calls), 2)
        self.assertFalse(r.model.calls[1]["vad_filter"])

    def test_no_retry_on_silence(self):
        from sprechhilfe.erkennung import Recognizer
        r = Recognizer(language="de")
        r.model = FakeModel([], [FakeSegment("Untertitel im Auftrag des ZDF")])
        self.assertEqual(r.transcribe(np.zeros(16000, dtype=np.int16)), "")
        self.assertEqual(len(r.model.calls), 1)

    def test_other_language_is_kept(self):
        from sprechhilfe.erkennung import Recognizer
        r = Recognizer(language="auto")
        r.model = FakeModel([FakeSegment("Hello, this is the bank.")], [], detected=(("en", 0.95), ("de", 0.02)))
        self.assertEqual(r.transcribe(self._speech()), "Hello, this is the bank.")
        self.assertEqual(r.model.calls[0]["language"], "en")
        self.assertEqual(r.last_language, "en")

    def test_push_to_talk_keeps_quiet_segments(self):
        from sprechhilfe.erkennung import Recognizer
        r = Recognizer(language="de")
        r.model = FakeModel([FakeSegment("Ja.", no_speech=0.8, logprob=-0.9)], [])
        self.assertEqual(r.transcribe(self._speech()), "Ja.")
        self.assertFalse(r.model.calls[0]["vad_filter"])


class GpuTest(unittest.TestCase):
    def test_dll_members(self):
        from sprechhilfe import gpu
        names = ["nvidia/cublas/bin/cublas64_12.dll", "nvidia/cublas/include/x.h", "nvidia/cudnn/bin/cudnn_ops64_9.dll",
                 "nvidia_cublas_cu12-12.9.1.4.dist-info/RECORD"]
        self.assertEqual(gpu.dll_members(names), ["nvidia/cublas/bin/cublas64_12.dll",
                                                  "nvidia/cudnn/bin/cudnn_ops64_9.dll"])
