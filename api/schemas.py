# api/schemas.py
# Qui metto i "contratti" dell'API (request/response) con Pydantic.
# Tengo tutto pulito e tipizzato, così quando cambio la logica sotto non devo
# toccare i payload esposti all'esterno.

from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Payload in ingresso al POST /ask: quello che scrive l'utente."""
    session_id: Optional[str] = Field(
        default=None, description="ID sessione per tenere il filo della conversazione"
    )
    user_id: Optional[str] = Field(
        default=None, description="ID utente (se lo uso per preferenze/profilo)"
    )
    query: str = Field(
        ..., min_length=2, description="Domanda o richiesta dell'utente"
    )


class Award(BaseModel):
    """Premio o riconoscimento (nomino e, se c'è, l'anno)."""
    name: str
    year: Optional[int] = None


class BookCard(BaseModel):
    """Scheda libro pronta per la UI: quello che effettivamente mostro."""
    titolo: str
    autore: str
    copertina_url: Optional[str] = None
    anno_pubblicazione: Optional[int] = None
    pagine: Optional[int] = None
    temi: List[str] = []
    complessita: Optional[int] = Field(
        default=None, ge=1, le=5, description="Stima 1..5 (1 facile, 5 tosto)"
    )
    premi_rilevanza: List[Award] = []
    trama_breve: Optional[str] = None
    perche_consigliato: Optional[str] = None


class DebugInfo(BaseModel):
    """Info di debug per capire da dove vengono i dati (utile in dev)."""
    sources: Optional[Dict[str, str]] = None   # es. {"wp": "...", "ol": "...", "wd": "..."}
    confidence: Optional[Dict[str, float]] = None  # es. {"anno_pubblicazione": 0.9}


class AskResponse(BaseModel):
    """Risposta del POST /ask: può essere una scheda libro o un messaggio testuale."""
    mode: Literal["book", "message"] = "book"
    result: Optional[BookCard] = None
    message: Optional[str] = None
    debug: Optional[DebugInfo] = None
