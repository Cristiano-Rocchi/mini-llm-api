# tools/wikidata_client.py
# Client per Wikidata via SPARQL. Qui provo a estrarre:
# - anno prima pubblicazione
# - premi (nome + anno)
# - generi
# - ambientazione (tempo/luogo) se capita
#
# Nota: tengo le query semplici e conservative. User-Agent obbligatorio.

from typing import List, Optional
from pydantic import BaseModel
import requests

WD_SPARQL = "https://query.wikidata.org/sparql"
TIMEOUT = 12
HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "mini-llm-api/0.1 (+demo)"
}


class WDAward(BaseModel):
    name: str
    year: Optional[int] = None


class WDData(BaseModel):
    first_publication_year: Optional[int] = None
    awards: List[WDAward] = []
    genre: List[str] = []
    setting_time: Optional[str] = None
    setting_place: Optional[str] = None
    qid: Optional[str] = None


def _run_sparql(query: str) -> Optional[dict]:
    try:
        r = requests.get(WD_SPARQL, params={"query": query}, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def _clean_label(uri_or_label: str) -> str:
    """Mi basta l'ultima parte se arriva un URI, altrimenti torno la stringa com'è."""
    if uri_or_label.startswith("http"):
        return uri_or_label.rsplit("/", 1)[-1]
    return uri_or_label


def from_isbn(isbn: str) -> Optional[WDData]:
    """Provo ad agganciare un'opera tramite ISBN (match forte)."""
    if not isbn:
        return None

    # 1) Trovo l'item libro collegato a questo ISBN (P212/P957) → prendo l'opera
    query_item = f"""
    SELECT ?book ?bookLabel ?work ?workLabel WHERE {{
      VALUES ?isbn "{{isbn}}"
      {{
        SELECT ?book WHERE {{
          ?book wdt:P212|wdt:P957 ?isbn .
        }} LIMIT 1
      }}
      OPTIONAL {{ ?book wdt:P629 ?work . }}  # se l'item è un'edizione, cerco la "work"
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
    }}
    """.replace("{isbn}", isbn)

    js = _run_sparql(query_item)
    if not js or not js.get("results", {}).get("bindings"):
        return None

    b = js["results"]["bindings"][0]
    work_uri = b.get("work", {}).get("value") or b.get("book", {}).get("value")
    if not work_uri:
        return None

    qid = _clean_label(work_uri)  # tipo "Q12345"
    return _fetch_work_data(qid)


def from_wikipedia(lang: str, title: str) -> Optional[WDData]:
    """Se ho una pagina Wikipedia, provo a risalire all'item Wikidata collegato."""
    if not lang or not title:
        return None

    # 1) Chiedo a Wikidata quale QID è collegato a questa pagina
    query_qid = f"""
    SELECT ?item WHERE {{
      ?item rdfs:label "{title}"@{lang} .
    }} LIMIT 1
    """
    js = _run_sparql(query_qid)
    if not js or not js.get("results", {}).get("bindings"):
        return None

    item_uri = js["results"]["bindings"][0]["item"]["value"]
    qid = _clean_label(item_uri)
    return _fetch_work_data(qid)


def _fetch_work_data(qid: str) -> Optional[WDData]:
    """Dato un QID di 'work' (opera), tiro fuori anno, premi, genere, setting."""
    if not qid:
        return None

    query = f"""
    SELECT ?pubYear ?awardLabel ?awardYear ?genreLabel ?timeLabel ?placeLabel WHERE {{
      OPTIONAL {{ wd:{qid} wdt:P577 ?pubDate . BIND(YEAR(?pubDate) AS ?pubYear) . }}
      OPTIONAL {{
        wd:{qid} wdt:P166 ?award .
        OPTIONAL {{ ?award wdt:P585 ?awardTime . BIND(YEAR(?awardTime) AS ?awardYear) . }}
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
      }}
      OPTIONAL {{ wd:{qid} wdt:P136 ?genre . SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }} }}
      OPTIONAL {{ wd:{qid} wdt:P2408 ?time .  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }} }}
      OPTIONAL {{ wd:{qid} wdt:P840 ?place . SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }} }}
    }}
    """
    js = _run_sparql(query)
    if not js:
        return None

    year = None
    awards: list[WDAward] = []
    genres: set[str] = set()
    time_lbl = None
    place_lbl = None

    for row in js.get("results", {}).get("bindings", []):
        # primo anno di pubblicazione
        if not year and "pubYear" in row:
            try:
                year = int(row["pubYear"]["value"])
            except Exception:
                pass

        # awards
        a_name = row.get("awardLabel", {}).get("value")
        a_year = row.get("awardYear", {}).get("value")
        if a_name:
            awards.append(WDAward(name=a_name, year=int(a_year) if a_year else None))

        # genre
        g = row.get("genreLabel", {}).get("value")
        if g:
            genres.add(g)

        # setting
        if not time_lbl:
            time_lbl = row.get("timeLabel", {}).get("value")
        if not place_lbl:
            place_lbl = row.get("placeLabel", {}).get("value")

    return WDData(
        first_publication_year=year,
        awards=awards,
        genre=list(genres),
        setting_time=time_lbl,
        setting_place=place_lbl,
        qid=qid,
    )
