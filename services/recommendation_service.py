# services/recommendation_service.py
# Qui gestisco il flusso "end-to-end" della raccomandazione:
# 1) capisco se l'utente sta salutando / chiacchiera / inventario / consiglio
# 2) per inventario: rispondo con conteggi o liste
# 3) per consiglio: ranking → enrichment → LLM
# 4) ritorno: o un messaggio (mode="message") o una BookCard (mode="book")

from __future__ import annotations
from typing import List, Optional, Dict, Any
from fastapi import HTTPException

from api.schemas import BookCard, Award as AwardDTO
from core.models import Book
from rag.scoring import overlap_score
from services.enrichment_service import EnrichmentService
from llm.ollama_client import LLMClient
from data.libri import LIBRI
from memory.session_store import SessionStore


class RecommendationService:
    """Coordina ranking → enrichment → LLM → costruzione risposta."""

    def __init__(self, enrichment: EnrichmentService, llm: LLMClient, session_store: Optional[SessionStore] = None):
        self.enrichment = enrichment
        self.llm = llm
        self.session_store = session_store
        self._books: List[Book] = [Book(**b) for b in LIBRI]

    # ---------- Helpers inventario ----------

    def _library_count(self) -> int:
        """Quanti libri totali ho in libreria."""
        return len(self._books)

    def _list_titles(self, limit: int = 12) -> list[str]:
        """Primi N titoli (ordinati alfabeticamente)."""
        return [b.titolo for b in sorted(self._books, key=lambda x: x.titolo)][:limit]

    def _looks_like_inventory(self, text: str) -> bool:
        """Euristica: frasi che iniziano con 'quali', 'quanti', ecc. vengono considerate inventario."""
        t = text.strip().lower()
        starters = ("quali", "quanti", "quante", "lista", "mostra", "elenca")
        if t.startswith(starters):
            return True
        if "quali libri" in t or "che libri" in t or "hai in libreria" in t:
            return True
        return False

    def _filter_by_genre_keyword(self, text: str, limit: int = 12) -> tuple[list[str], int, str | None]:
        """Rileva un genere (plurali/sinonimi/autori/indizi nel titolo) e ritorna
        (titoli, totale, label_tema). Non richiede che i 'temi' abbiano la tassonomia perfetta.
        """
        t = text.lower()

        # 1) parole chiave per ogni genere (query + titolo + temi)
        MAP = {
            "Giallo / Mistero": [
                "giallo", "gialli", "mistero", "noir", "poliziesco", "detective", "thriller",
                # indizi tipici nei titoli
                "assassinio", "omicidio", "delitto", "indagine", "investig", "enig", "colpevole",
                # personaggi/autori iconici
                "poirot", "sherlock", "maigret", "agatha christie", "conan doyle", "simenon", "camilleri"
            ],
            "Fantasy / Avventura": [
                "fantasy", "fantasie", "avventura", "epico", "epica", "spada", "magia", "streg",
                "elf", "drag", "hobbit", "narnia", "tolkien"
            ],
            "Fantascienza / Distopia": [
                "fantascienza", "sci-fi", "scifi", "distopia", "distopico", "robot", "spazio",
                "astron", "cyber", "android", "asimov", "philip k. dick", "valis", "1984"
            ],
            "Filosofia / Pensiero": ["filosofia", "filosofico", "pensiero", "metafisica", "sofista", "platone", "aristotele"],
            "Saggio / Scienza": ["saggio", "saggi", "scienza", "scientifico", "fisica", "quantistica", "cosmologia"],
            "Storico / Biografico": ["storico", "storia", "biografico", "biografia", "memorie"],
            "Psicologia / Società": ["psicologia", "psicologico", "società", "sociale", "psico"],
            "Saggistica economica / politica": ["economia", "economico", "politica", "politico", "capitale", "mercato"],
            "Classici / Letteratura": ["classico", "classici", "letteratura", "dostoevskij", "orwell", "verne"],
        }

        # 2) capisco quale "famiglia" cerca l'utente
        target_label = None
        target_keywords: list[str] = []
        for label, kws in MAP.items():
            if any(kw in t for kw in kws):
                target_label = label
                target_keywords = kws
                break

        # se non capisco il genere, esco
        if not target_keywords:
            return ([], 0, target_label)

        # 3) cerco corrispondenze su: titolo + temi testuali + autore
        hits: list[Book] = []
        for b in self._books:
            text_fields = (
                (b.titolo or "").lower()
                + " "
                + " ".join((b.temi or [])).lower()
                + " "
                + (b.autore or "").lower()
            )
            if any(kw in text_fields for kw in target_keywords):
                hits.append(b)

        if not hits:
            return ([], 0, target_label)

        titles = [b.titolo for b in sorted(hits, key=lambda x: x.titolo)[:limit]]
        return (titles, len(hits), target_label)

    # ---------- API pubblica ----------

    def recommend(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not query or len(query.strip()) < 2:
            raise HTTPException(status_code=400, detail="Query troppo corta")

        q = query.strip()

        # salvo il turno utente in cronologia (se ho session_id)
        if self.session_store and session_id:
            self.session_store.append_message(session_id, "user", q)

        # Intent classificato (euristica → poi LLM)
        intent = "inventario" if self._looks_like_inventory(q) else (self.llm.classify_intent(q) or "altro").strip().lower()

        # --- INVENTARIO: "quali/quanti libri", "quanti gialli", "lista fantasy" ---
        if intent == "inventario":
            total = self._library_count()
            titles_gen, count_gen, label_gen = self._filter_by_genre_keyword(q, limit=12)
            if count_gen > 0:
                head = f"In libreria ho {count_gen} titoli per «{label_gen}». Eccone alcuni:"
                msg = head + "\n- " + "\n- ".join(titles_gen)
            else:
                preview = self._list_titles(limit=12)
                head = f"In libreria ho {total} libri. Ecco una breve lista iniziale:"
                msg = head + "\n- " + "\n- ".join(preview)

            if self.session_store and session_id:
                self.session_store.append_message(session_id, "assistant", msg)
            return {"mode": "message", "message": msg}

        # --- Small talk / saluto / altro → risposta breve cordiale ---
        if intent in {"saluto", "chiacchiera", "altro"}:
            msg = self.llm.small_talk(q)
            msg = (msg or "Ciao!").rstrip() + " Se vuoi, dimmi genere, mood o lunghezza e ti consiglio un titolo."
            if self.session_store and session_id:
                self.session_store.append_message(session_id, "assistant", msg)
            return {"mode": "message", "message": msg}

        # --- Info libro specifico → guida ---
        if intent == "info_libro":
            msg = "Dimmi il titolo esatto (e se vuoi l’autore) così ti do informazioni sul libro dalla mia libreria."
            if self.session_store and session_id:
                self.session_store.append_message(session_id, "assistant", msg)
            return {"mode": "message", "message": msg}

        # --- Consiglio libro ---
        ranked = sorted(self._books, key=lambda b: overlap_score(q, b), reverse=True)
        if not ranked:
            raise HTTPException(status_code=404, detail="Nessun libro disponibile in libreria")
        best = ranked[0]

        fused = self.enrichment.enrich(best)
        llm_payload = {
            "titolo": fused.titolo,
            "autore": fused.autore,
            "temi": fused.temi,
            "pagine": fused.pagine,
            "anno_pubblicazione": fused.anno_pubblicazione,
            "summary_wp": fused.trama_breve or "",
            "query_utente": q,
        }
        llm_out = self.llm.write_json_summary(llm_payload)

        trama_breve = (llm_out or {}).get("trama_breve") or fused.trama_breve
        perche = (llm_out or {}).get("perche_consigliato")

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

        # salvo una breve traccia della risposta assistant
        if self.session_store and session_id:
            brief = f"Consiglio: {card.titolo} — {card.perche_consigliato or ''}".strip()
            self.session_store.append_message(session_id, "assistant", brief)

        return {"mode": "book", "result": card}
