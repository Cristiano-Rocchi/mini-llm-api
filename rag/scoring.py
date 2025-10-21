# rag/scoring.py
# Qui tengo la logica di "ranking" e il mapping dei generi.
# Serve per capire quali libri sono più simili alla richiesta dell'utente.

from typing import List
from core.models import Book


def overlap_score(query: str, book: Book) -> int:
    """Conta quante parole del titolo o dei temi compaiono nella query."""
    query_words = set(query.lower().split())
    titolo_words = set(book.titolo.lower().split())
    temi_words = set([t.lower() for t in book.temi])
    return len(query_words & (titolo_words | temi_words))


TAXONOMY_MAP = {
    "mystery": "Giallo / Mistero",
    "detective": "Giallo / Mistero",
    "fantasy": "Fantasy / Avventura",
    "adventure": "Fantasy / Avventura",
    "science": "Saggio / Scienza",
    "fiction": "Fantascienza / Distopia",
    "philosophy": "Filosofia / Pensiero",
    "history": "Storico / Biografico",
    "psychology": "Psicologia / Società",
    "economy": "Saggistica economica / politica",
}


def map_subjects_to_taxonomy(subjects: List[str]) -> List[str]:
    """Converte i soggetti OpenLibrary/Wikidata nella tassonomia MVP."""
    mapped = set()
    for s in subjects:
        s_lower = s.lower()
        for key, label in TAXONOMY_MAP.items():
            if key in s_lower:
                mapped.add(label)
    return list(mapped) if mapped else ["Altro / Generale"]
