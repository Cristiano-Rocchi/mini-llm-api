# tools/openlibrary_client.py
# Client per OpenLibrary. Qui cerco copertina, pagine e subjects (temi).
# Provo prima con ISBN (match forte), altrimenti cerco per titolo+autore.

from typing import List, Optional
from pydantic import BaseModel
import requests


OL_BASE = "https://openlibrary.org"
OL_COVERS = "https://covers.openlibrary.org/b/olid/{olid}-L.jpg"
TIMEOUT = 10  # non tengo richieste appese


class OLData(BaseModel):
    """Quello che mi interessa da OpenLibrary per l'MVP."""
    cover_url: Optional[str] = None
    pages: Optional[int] = None
    publish_year: Optional[int] = None
    subjects: List[str] = []
    isbns: List[str] = []  # può tornarmi utile per agganciare Wikidata
    olid: Optional[str] = None  # id dell'edizione (per copertine)


def _safe_get(url: str, params: dict | None = None) -> Optional[dict]:
    """GET semplice con timeout. Ritorno None se qualcosa va storto."""
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def fetch_by_isbn(isbn: str) -> Optional[OLData]:
    """Cerco un'edizione precisa tramite ISBN. Se trovo, estraggo i campi base."""
    if not isbn:
        return None
    url = f"{OL_BASE}/isbn/{isbn}.json"
    data = _safe_get(url)
    if not data:
        return None

    # alcuni campi possono stare a livelli diversi, estraggo con prudenza
    pages = data.get("number_of_pages")
    publish_year = None
    if "publish_date" in data:
        # publish_date può essere "1974" o "June 1974": prendo i numeri iniziali
        import re
        m = re.search(r"\d{4}", str(data.get("publish_date")))
        if m:
            publish_year = int(m.group(0))

    subjects = []
    if "subjects" in data and isinstance(data["subjects"], list):
        # su isbn endpoint i subjects spesso sono stringhe
        subjects = [s if isinstance(s, str) else str(s) for s in data["subjects"]]

    # provo a risalire all'OLID (chiave edizione) per la copertina
    olid = None
    if "works" in data and data["works"]:
        # a volte l'OLID “buono” per la cover è quello dell’edizione, non della work.
        pass
    if "key" in data and isinstance(data["key"], str):
        # es: "/books/OL12345M" → prendo "OL12345M"
        olid = data["key"].split("/")[-1]

    cover_url = OL_COVERS.format(olid=olid) if olid else None

    # ISBN list (alcune edizioni hanno più isbn)
    isbns = []
    for k in ("isbn_13", "isbn_10"):
        vals = data.get(k) or []
        isbns.extend(vals)

    return OLData(
        cover_url=cover_url,
        pages=pages,
        publish_year=publish_year,
        subjects=subjects,
        isbns=isbns or ([isbn] if isbn else []),
        olid=olid,
    )


def search_title_author(title: str, author: str) -> Optional[OLData]:
    """Se non ho ISBN, cerco per titolo+autore e prendo la prima corrispondenza sensata."""
    if not title:
        return None

    params = {"title": title, "author": author, "limit": 1}
    data = _safe_get(f"{OL_BASE}/search.json", params=params)
    if not data or not data.get("docs"):
        return None

    doc = data["docs"][0]
    # provo a comporre una OLData base
    pages = doc.get("number_of_pages_median")
    publish_year = None
    if "first_publish_year" in doc:
        publish_year = int(doc["first_publish_year"])

    subjects = doc.get("subject", []) or []
    olid = None
    # preferisco l'edition_key per la cover
    if "edition_key" in doc and doc["edition_key"]:
        olid = doc["edition_key"][0]

    cover_url = OL_COVERS.format(olid=olid) if olid else None
    isbns = doc.get("isbn", []) or []

    return OLData(
        cover_url=cover_url,
        pages=pages,
        publish_year=publish_year,
        subjects=subjects,
        isbns=isbns,
        olid=olid,
    )
