# services/recommendation_service.py
# Qui gestisco il flusso "end-to-end" della raccomandazione:
# 1) capisco se l'utente sta salutando o vuole un consiglio
# 2) scelgo i candidati dalla mia libreria (ranking semplice)
# 3) arricchisco il migliore con fonti esterne
# 4) chiedo all'LLM due frasi (trama breve + perché consigliato)
# 5) ritorno: o un messaggio guida (mode="message") o una BookCard (mode="book")

from __future__ import annotations

from typing import List, Optional, Dict, Any
from fastapi import HTTPException

from api.schemas import BookCard, Award as AwardDTO
from core.models import Book
from rag.scoring import overlap_score
from services.enrichment_service import EnrichmentService
from llm.ollama_client import LLMClient

# prendo i libri locali (la mia "base di verità")
from data.libri import LIBRI  # deve essere una lista di dict con almeno titolo/autore/temi


class RecommendationService:
    """Coordina ranking → enrichment → LLM → costruzione risposta."""

    def __init__(self, enrichment: EnrichmentService, llm: LLMClient):
        self.enrichment = enrichment
        self.llm = llm
        self._books: List[Book] = [Book(**b) for b in LIBRI]

        # Lista semplice di saluti (small talk). Basta per evitare consigli su "ciao".
        self._saluti = {
            "ciao", "hey", "hei", "salve", "buongiorno", "buona sera", "buonasera",
            "hello", "hi", "yo"
        }

    # ---------- API pubblica ----------

    def recommend(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Se è small talk → message, altrimenti costruisco e ritorno una BookCard."""
        if not query or len(query.strip()) < 2:
            raise HTTPException(status_code=400, detail="Query troppo corta")

        q = query.strip().lower()

        # 1) Small talk / saluti → mando un messaggio guida, niente libro
        if q in self._saluti or any(q.startswith(s) for s in self._saluti):
            return {
                "mode": "message",
                "message": (
                    "Ciao! Dimmi che genere e durata vuoi.\n"
                    "Esempi: “consigliami un giallo breve”, "
                    "“fantascienza sotto le 200 pagine”, “un classico d’avventura”."
                ),
            }

        # (Opzionale) se preferisco usare il classificatore LLM:
        # intent = (self.llm.classify_intent(query) or "").strip()
        # if intent == "saluto":
        #     return {"mode": "message", "message": "Ciao! ... (stesso testo di cui sopra)"}

        # 2) Ranking semplice (overlap tra query e titolo/temi)
        ranked = sorted(self._books, key=lambda b: overlap_score(query, b), reverse=True)
        if not ranked:
            raise HTTPException(status_code=404, detail="Nessun libro disponibile in libreria")

        best = ranked[0]

        # 3) Arricchimento con fonti esterne (OL→WP→WD + fusion)
        fused = self.enrichment.enrich(best)

        # 4) LLM “writer controllato”: chiedo solo 2 campi in JSON
        llm_payload = {
            "titolo": fused.titolo,
            "autore": fused.autore,
            "temi": fused.temi,
            "pagine": fused.pagine,
            "anno_pubblicazione": fused.anno_pubblicazione,
            "summary_wp": fused.trama_breve or "",
            "query_utente": query,
        }
        llm_out = self.llm.write_json_summary(llm_payload)

        trama_breve = (llm_out or {}).get("trama_breve") or fused.trama_breve
        perche = (llm_out or {}).get("perche_consigliato")

        # 5) Compongo la BookCard finale
        premi_dto = [AwardDTO(name=a.name, year=a.year) for a in fused.premi_rilevanza]

        card = BookCard(
            titolo=fused.titolo,
            autore=fused.autore,
            copertina_url=fused.copertina_url,
            anno_pubblicazione=fused.anno_pubblicazione,
            pagine=fused.pagine,
            temi=fused.temi,
            complessita=fused.complessita,
            premi_rilevanza=premi_dto,
            trama_breve=trama_breve,
            perche_consigliato=perche,
        )

        # Ritorno nel formato atteso dalla route (mode + result)
        return {
            "mode": "book",
            "result": card,
        }
