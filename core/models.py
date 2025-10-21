# core/models.py
# Qui tengo le classi principali che rappresentano i dati del sistema.
# Non contengono logica, solo struttura e tipi base.

from typing import List, Optional, Dict
from pydantic import BaseModel


class Book(BaseModel):
    """Libro della mia libreria locale."""
    titolo: str
    autore: str
    isbn: Optional[str] = None
    temi: List[str] = []  # generi o parole chiave principali


class Award(BaseModel):
    """Premio o riconoscimento legato a un libro."""
    name: str
    year: Optional[int] = None


class EnrichmentRecord(BaseModel):
    """Dati arricchiti (unione OL + WP + WD)."""
    titolo: str
    autore: str
    copertina_url: Optional[str] = None
    anno_pubblicazione: Optional[int] = None
    pagine: Optional[int] = None
    temi: List[str] = []
    premi_rilevanza: List[Award] = []
    trama_breve: Optional[str] = None
    complessita: Optional[int] = None
    tempo_lettura_ore: Optional[float] = None
    fonti: Dict[str, str] = {}        # es. {"ol": "...", "wp": "...", "wd": "..."}
    confidence: Dict[str, float] = {} # es. {"anno_pubblicazione": 0.9}


class UserProfile(BaseModel):
    """Preferenze o storico dell’utente."""
    user_id: str
    generi_like: List[str] = []
    generi_dislike: List[str] = []
    consigli_recenti: List[str] = []  # titoli già proposti
