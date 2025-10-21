# tools/wikipedia_client.py
# Client leggero per Wikipedia. Mi serve trovare la pagina giusta (libro)
# e tirare giù un riassunto breve. Provo IT, poi fallback EN.

from typing import Optional
from pydantic import BaseModel
import requests
import urllib.parse

TIMEOUT = 10
UA = {"User-Agent": "mini-llm-api/0.1 (+demo)"}

API_SEARCH = "https://{lang}.wikipedia.org/w/api.php"
API_SUMMARY = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"


class WPPage(BaseModel):
    """Info minime sulla pagina wikipedia che ho deciso di usare."""
    lang: str
    title: str
    url: str
    summary: Optional[str] = None


def _search(lang: str, query: str) -> Optional[str]:
    """Uso l'API di search per beccare il title migliore."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 1,
    }
    try:
        r = requests.get(API_SEARCH.format(lang=lang), params=params, headers=UA, timeout=TIMEOUT)
        if r.status_code == 200:
            js = r.json()
            hits = js.get("query", {}).get("search", [])
            if hits:
                return hits[0].get("title")
    except Exception:
        return None
    return None


def _summary(lang: str, title: str) -> Optional[str]:
    """Prendo il riassunto 'ufficiale' via REST v1. Se non c'è, None."""
    try:
        url = API_SUMMARY.format(lang=lang, title=urllib.parse.quote(title))
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        if r.status_code == 200:
            js = r.json()
            # controllo minimo per non prendere summary di film/album se posso evitarlo
            return js.get("extract") or js.get("description")
    except Exception:
        return None
    return None


def best_page(title: str, author: str) -> Optional[WPPage]:
    """Heuristica semplice: cerco 'titolo autore romanzo' in IT, poi in EN."""
    if not title:
        return None

    for lang, hint in (("it", "romanzo"), ("en", "novel")):
        query = f'{title} {author} {hint}'.strip()
        found_title = _search(lang, query) or _search(lang, f"{title} {hint}") or _search(lang, title)
        if not found_title:
            continue

        # costruisco l'URL canonico
        url = f"https://{lang}.wikipedia.org/wiki/{found_title.replace(' ', '_')}"
        sm = _summary(lang, found_title)

        # se il summary esiste, ho finito; altrimenti provo il prossimo lang
        if sm:
            return WPPage(lang=lang, title=found_title, url=url, summary=sm)

        # anche senza summary, mi tengo la pagina (meglio di niente)
        return WPPage(lang=lang, title=found_title, url=url, summary=None)

    return None
