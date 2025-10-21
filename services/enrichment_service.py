# services/enrichment_service.py
# Qui faccio l'arricchimento dei dati di un libro:
# chiamo OpenLibrary, Wikipedia e Wikidata, poi "fondo" tutto con
# delle regole semplici (priorità per campo, dedup, confidence).
# Tengo anche una cache su file per non stressare le API.

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, List

from core.models import Book, EnrichmentRecord, Award
from core import config
from tools.openlibrary_client import fetch_by_isbn, search_title_author, OLData
from tools.wikipedia_client import best_page, WPPage
from tools.wikidata_client import from_isbn as wd_from_isbn, from_wikipedia as wd_from_wikipedia, WDData
from rag.scoring import map_subjects_to_taxonomy


class EnrichmentService:
    """Orchestra le fonti esterne e produce un record 'fuso' pronto per la UI/LLM."""

    def __init__(self, cache_path: Path | None = None):
        self.cache_path = Path(cache_path or config.CACHE_FILE)
        self.cache: Dict[str, dict] = self._load_cache()

    # ---------- Cache ----------

    def _cache_key(self, book: Book) -> str:
        # chiave semplice per cache (autore|titolo|isbn?)
        parts = [book.autore.strip().lower(), book.titolo.strip().lower()]
        if book.isbn:
            parts.append(book.isbn.strip())
        return "|".join(parts)

    def _load_cache(self) -> Dict[str, dict]:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    # ---------- API pubblica ----------

    def enrich(self, book: Book) -> EnrichmentRecord:
        """Arricchisce un libro usando OL→WP→WD e fonde i risultati in un record unico."""
        key = self._cache_key(book)
        if key in self.cache:
            return EnrichmentRecord(**self.cache[key]["fused"])

        # 1) OpenLibrary
        ol: Optional[OLData] = None
        if book.isbn:
            ol = fetch_by_isbn(book.isbn)
        if not ol:
            ol = search_title_author(book.titolo, book.autore)

        # 2) Wikipedia (IT→EN)
        wp: Optional[WPPage] = best_page(book.titolo, book.autore)

        # 3) Wikidata (aggancio via ISBN se possibile, altrimenti da WP)
        wd: Optional[WDData] = None
        candidate_isbn = None
        if ol and ol.isbns:
            candidate_isbn = ol.isbns[0]
            wd = wd_from_isbn(candidate_isbn)
        if not wd and wp:
            wd = wd_from_wikipedia(wp.lang, wp.title)

        # 4) Fusion
        fused = self._fuse(book=book, ol=ol, wp=wp, wd=wd)

        # 5) Salvo in cache
        self.cache[key] = {
            "from_lib": book.model_dump(),
            "ol": ol.model_dump() if ol else None,
            "wp": wp.model_dump() if wp else None,
            "wd": wd.model_dump() if wd else None,
            "fused": fused.model_dump(),
        }
        self._save_cache()

        return fused

    # ---------- Fusion rules ----------

    def _fuse(self, book: Book, ol: Optional[OLData], wp: Optional[WPPage], wd: Optional[WDData]) -> EnrichmentRecord:
        """Applico le regole di priorità per ogni campo + stime semplici."""

        # Titolo e autore: prendo quelli "di casa" (libri miei)
        titolo = book.titolo
        autore = book.autore

        # Copertina: preferisco OL
        copertina_url = ol.cover_url if ol else None

        # Pagine: OL, poi fallback None
        pagine = ol.pages if (ol and ol.pages) else None

        # Anno: WD > WP > OL
        anno_pubblicazione = None
        conf_anno = 0.0
        if wd and wd.first_publication_year:
            anno_pubblicazione = wd.first_publication_year
            conf_anno = 0.9
        elif ol and ol.publish_year:
            anno_pubblicazione = ol.publish_year
            conf_anno = 0.6
        # (da WP potrei anche estrarre dall'infobox, ma per MVP mi basta così)

        # Temi/Genere: unione tra OL.subjects, WD.genre e temi locali
        subjects: List[str] = []
        if ol and ol.subjects:
            subjects.extend(ol.subjects)
        if wd and wd.genre:
            subjects.extend(wd.genre)
        if book.temi:
            subjects.extend(book.temi)

        temi = map_subjects_to_taxonomy(subjects)

        # Premi/rilevanza da WD
        premi = []
        if wd and wd.awards:
            for a in wd.awards:
                premi.append(Award(name=a.name, year=a.year))

        # Trama breve da WP (se c'è)
        trama_breve = wp.summary if (wp and wp.summary) else None

        # Complessità lettura: stima semplice
        complessita = self._compute_complexity(pagine, subjects)

        # Tempo lettura: stimato in ore (arrotondo a .5)
        tempo_lettura_ore = self._estimate_read_time(pagine)

        # Fonti + confidence base
        fonti = {
            "ol": "OpenLibrary" if ol else "",
            "wp": wp.url if wp else "",
            "wd": f"https://www.wikidata.org/wiki/{wd.qid}" if (wd and wd.qid) else "",
        }
        confidence = {
            "anno_pubblicazione": conf_anno,
            "pagine": 0.8 if (ol and ol.pages) else 0.0,
            "temi": 0.7 if subjects else 0.0,
        }

        return EnrichmentRecord(
            titolo=titolo,
            autore=autore,
            copertina_url=copertina_url,
            anno_pubblicazione=anno_pubblicazione,
            pagine=pagine,
            temi=temi,
            premi_rilevanza=premi,
            trama_breve=trama_breve,
            complessita=complessita,
            tempo_lettura_ore=tempo_lettura_ore,
            fonti=fonti,
            confidence=confidence,
        )

    # ---------- Helpers ----------

    def _compute_complexity(self, pagine: Optional[int], subjects: List[str]) -> Optional[int]:
        """Stimo la difficoltà 1..5: base sulle pagine, ±1 se temi molto tecnici/filosofici."""
        if not pagine:
            base = 3
        elif pagine <= 200:
            base = 2
        elif pagine <= 400:
            base = 3
        else:
            base = 4

        # piccoli aggiustamenti
        s = " ".join(subjects).lower()
        if any(k in s for k in ["philosophy", "metaphysics", "theory", "economics", "physics"]):
            base += 1
        if any(k in s for k in ["young adult", "children", "fairy", "adventure"]):
            base -= 1

        return max(1, min(5, base))

    def _estimate_read_time(self, pagine: Optional[int]) -> Optional[float]:
        """Tempo lettura in ore: 250 parole/pagina, 220 wpm. Arrotondo a 0.5h."""
        if not pagine:
            return None
        words = pagine * 250
        hours = words / (220 * 60)
        # arrotondo a mezz'ora
        return round(hours * 2) / 2
