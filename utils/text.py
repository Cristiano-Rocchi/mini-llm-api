# utils/text.py
# Qui metto piccole funzioni di testo comuni, per non ripeterle in giro.

import re
import unicodedata


def normalize_title(s: str) -> str:
    """Rende il titolo confrontabile: minuscolo, senza accenti né punteggiatura."""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return s.strip()


def slugify(title: str) -> str:
    """Crea uno slug semplice (per cache, chiavi, ecc.)."""
    return normalize_title(title).replace(" ", "-")
