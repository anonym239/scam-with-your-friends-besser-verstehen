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
        self.assertEqual(s.tippverzoegerung, 4)
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
        a.recognizer.transcribe = lambda samples: "Bitte zahlen Sie mit pay pal."
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
