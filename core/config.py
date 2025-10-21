# core/config.py
# File di configurazione base. Serve per tenere ordinati modelli, percorsi, ecc.

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Nome del modello Ollama
MODEL_NAME = "llama3"

# File di cache per i dati arricchiti (in /data)
CACHE_FILE = BASE_DIR / "data" / "cache.json"

# Libreria locale
LIBRARY_FILE = BASE_DIR / "data" / "libri.py"

# Parametri di fallback
DEFAULT_LANGUAGE = "it"
