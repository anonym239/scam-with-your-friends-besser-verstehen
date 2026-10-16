"""Nachbearbeitung des erkannten Texts: eigene Ersetzungen und Satzende."""
import re


def apply_replacements(text, replacements):
    """Ersetzt ganze Wörter/Wortgruppen ohne Rücksicht auf Groß-/Kleinschreibung. Längere Einträge zuerst."""
    for wrong in sorted(replacements, key=len, reverse=True):
        right = replacements[wrong]
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in wrong.split()) + r"(?!\w)"
        text = re.sub(pattern, lambda _m: right, text, flags=re.IGNORECASE)
    return text


def finish(text, replacements=None, drop_period=False):
    text = " ".join(text.split())
    if replacements:
        text = apply_replacements(text, replacements)
    if drop_period and text.endswith(".") and not text.endswith(".."):
        text = text[:-1]
    return text.strip()
