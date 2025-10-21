from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests
import json
import re
from typing import List, Dict, Tuple

from libri import LIBRI

# -------------------- MODELLI DATI --------------------
class ConsigliaIn(BaseModel):
    testo_utente: str

class Scelta(BaseModel):
    titolo: str
    motivo: str

class Fonte(BaseModel):
    titolo: str
    url: str

class ConsigliaOut(BaseModel):
    scelte: List[Scelta] = Field(default_factory=list)
    note: str | None = None
    fonti: List[Fonte] = Field(default_factory=list)

# Per la chat generale
class ChatIn(BaseModel):
    sessione_id: str | None = None
    messaggio: str

class ChatOut(BaseModel):
    risposta: str

# -------------------- FASTAPI APP --------------------
app = FastAPI(title="Mini LLM API")

# CORS (aperto per sviluppo; in produzione limita ai tuoi domini)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- CONFIG --------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

# Memoria conversazioni minimale in RAM (per demo)
SESSIONS: Dict[str, List[Dict[str, str]]] = {}

# -------------------- UTILS --------------------
def ask_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "top_p": 0.9},
            },
            timeout=180,
        )
        r.raise_for_status()
        return r.json().get("response", "")
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Errore chiamando Ollama: {e}")

def wiki_summary(title: str, lang: str = "it") -> Tuple[str, str, str]:
    """
    Restituisce (titolo_pagina, url, testo_summary) usando l'API REST di Wikipedia.
    Fallback: tuple vuote se non trova.
    """
    base = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
    try:
        resp = requests.get(base + requests.utils.quote(title), timeout=10)
        if resp.status_code != 200:
            return "", "", ""
        data = resp.json()
        page_title = data.get("titles", {}).get("display") or data.get("title") or title
        url = data.get("content_urls", {}).get("desktop", {}).get("page") or data.get("source") or ""
        extract = data.get("extract") or ""
        return page_title, url, extract
    except requests.RequestException:
        return "", "", ""

def best_wiki_for_book(lb: dict) -> Tuple[str, str, str]:
    """
    Tenta: wiki_it -> wiki_en. Se non definiti, prova con Titolo + Autore su it poi en.
    """
    for lang, key in [("it", "wiki_it"), ("en", "wiki_en")]:
        t = lb.get(key)
        if t:
            pt, url, extr = wiki_summary(t, lang=lang)
            if extr:
                return pt, url, extr

    # fallback semplice: prova col titolo + autore
    for lang in ("it", "en"):
        guess = f"{lb.get('titolo','')} ({lb.get('autore','')})"
        pt, url, extr = wiki_summary(guess, lang=lang)
        if extr:
            return pt, url, extr

    return "", "", ""

def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def overlap_score(query: str, lb: dict) -> int:
    """
    Punteggio grezzo per selezionare candidati (match su parole_chiave/mood/temi).
    """
    q = normalize_text(query).lower()
    tokens = set(re.findall(r"[a-zà-ù0-9]+", q, flags=re.IGNORECASE))
    bag = []
    for k in ("parole_chiave", "mood", "temi"):
        bag.extend([str(x).lower() for x in (lb.get(k) or [])])
    score = 0
    for t in bag:
        for w in tokens:
            if w and w in t:
                score += 1
    return score

# -------------------- INTENT & CONSTRAINTS --------------------
INTENT_BOOK_RE = re.compile(
    r"\b(libro|libri|leggere|lettura|consiglia|consiglio|romanzo|saggio|giallo|fantasy|distopico|avventura|classico)\b",
    re.IGNORECASE,
)
GREETING_RE = re.compile(r"\b(ciao|hey|hello|salve|buongiorno|buonasera)\b", re.IGNORECASE)

def classify_intent(txt: str) -> str:
    t = (txt or "").lower()
    if GREETING_RE.search(t) and not INTENT_BOOK_RE.search(t):
        return "greeting"
    if INTENT_BOOK_RE.search(t):
        return "book_reco"
    return "chitchat"

def parse_constraints(txt: str) -> dict:
    t = (txt or "").lower()

    # Pagine richieste
    pages = None
    m = re.search(r"(\d{2,4})\s*pagin", t)
    if m:
        pages = int(m.group(1))
    elif re.search(r"(molto )?breve|sotto\s*200|meno di\s*200", t):
        pages = ("max", 200)
    elif re.search(r"lung(o|a)|corpos[oa]|oltre\s*500|pi[uù]\s*di\s*500", t):
        pages = ("min", 500)

    # Parole chiave desiderate
    wants = set()
    for kw in ["giallo","fantasy","distopico","classico","avventura","filosofico","saggio","umoristico","cupo","leggero","psicologico"]:
        if kw in t:
            wants.add(kw)

    return {"pages": pages, "wants": wants}

def pages_ok(lb: dict, pages_constraint):
    if not pages_constraint:
        return True
    approx = int(lb.get("pagine_approx") or 0)
    if approx <= 0:
        return False
    if isinstance(pages_constraint, tuple):  # ("max", 200) o ("min", 500)
        kind, v = pages_constraint
        return (kind == "max" and approx <= v) or (kind == "min" and approx >= v)
    # numero esatto: accetta ±15% (min 50 pagine)
    return abs(approx - int(pages_constraint)) <= max(50, int(0.15 * approx))

# -------------------- PROMPTING --------------------
SYSTEM_RULES = """
Ruolo: sei un bibliotecario che consiglia libri.

Regole RIGIDE:
1) Puoi scegliere SOLO tra i titoli in LISTA_TITOLI.
2) Usa ESCLUSIVAMENTE i PASSAGGI_FORNITI per i fatti (trama/temi/contesto). Se non bastano, ammetti incertezza.
3) Rispondi SOLO in JSON valido con lo schema:
{
  "scelte": [ { "titolo": "...", "motivo": "..." }, ... ],
  "note": "",
  "fonti": [ { "titolo": "...", "url": "..." }, ... ]
}
4) In "motivo" cita i TAG usati (es: giallo, breve, leggero) e riferisci ai passaggi forniti.
5) Non aggiungere NIENTE fuori dal JSON.
6) Se non ci sono titoli che rispettano i vincoli, lascia "scelte": [] e usa "note" per CHIEDERE UNA SOLA DOMANDA di chiarimento utile.
"""

def build_grounded_prompt(testo_utente: str, candidati: List[dict], fonti: List[Tuple[str,str,str]]) -> str:
    """
    Crea un prompt 'grounded' con: titoli ammessi + estratti Wikipedia (per i soli candidati).
    """
    titoli_ammessi = [c["titolo"] for c in candidati]
    blocco_fonti = []
    for (lb, (pt, url, extr)) in zip(candidati, fonti):
        if extr:
            blocco_fonti.append(
                f"[FONTE per {lb['titolo']}] TitoloPagina: {pt}\nURL: {url}\nEstratto: {extr}\n"
            )

    lista_tag = []
    for c in candidati:
        tags = []
        for k in ("parole_chiave", "mood", "temi"):
            tags.extend(c.get(k) or [])
        lista_tag.append(f"- {c['titolo']} | TAG: {', '.join(tags)}")

    return f"""{SYSTEM_RULES}

Utente: {testo_utente}

LISTA_TITOLI (vincolo assoluto):
{json.dumps(titoli_ammessi, ensure_ascii=False)}

TAG DEI CANDIDATI:
{chr(10).join(lista_tag)}

PASSAGGI_FORNITI (estratti da Wikipedia):
{chr(10).join(blocco_fonti)}

Restituisci SOLO il JSON richiesto.
"""

# -------------------- CORE: CONSIGLIA --------------------
def consiglia_core(testo_utente: str) -> ConsigliaOut:
    cons = parse_constraints(testo_utente)

    # 1) FILTRO PAGINE: elimina subito ciò che non rispetta il vincolo
    candidati0 = [lb for lb in LIBRI if pages_ok(lb, cons["pages"])]
    if not candidati0:
        return ConsigliaOut(
            scelte=[],
            note="Nessun titolo rispetta il vincolo di pagine. Va bene se cerco qualcosa con ~300 pagine?"
        )

    # 2) PUNTEGGIO SEMANTICO: overlap su parole_chiave/mood/temi (+1 se contiene wants espliciti)
    def score(lb):
        base = overlap_score(testo_utente, lb)
        bonus = 0
        bag = []
        for k in ("parole_chiave", "mood", "temi"):
            bag.extend([str(x).lower() for x in (lb.get(k) or [])])
        for w in cons["wants"]:
            if any(w in t for t in bag):
                bonus += 1
        return base + bonus

    scored = sorted(candidati0, key=score, reverse=True)
    if not scored:
        return ConsigliaOut(scelte=[], note="Non ho trovato corrispondenze chiare. Specifica genere/mood/lunghezza.")

    max_score = score(scored[0])
    if max_score <= 0:
        return ConsigliaOut(
            scelte=[],
            note="Non ho una corrispondenza chiara tra i miei titoli. Vuoi indicarmi genere o mood?"
        )

    # tieni i migliori (entro 1 punto dal top) per non saturare il prompt
    candidati = [lb for lb in scored[:5] if score(lb) >= max(1, max_score - 1)]

    # 3) ESTRATTI WIKIPEDIA
    fonti = [best_wiki_for_book(lb) for lb in candidati]

    # 4) PROMPT GROUNDED → LLM
    prompt = build_grounded_prompt(testo_utente, candidati, fonti)
    raw = ask_ollama(prompt).strip()

    # 5) ESTRATTO JSON
    start = raw.find("{"); end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ConsigliaOut(scelte=[], note="risposta non in JSON")

    try:
        data = json.loads(raw[start:end+1])
    except json.JSONDecodeError:
        return ConsigliaOut(scelte=[], note="JSON non valido dal modello")

    # 6) ANTI-ALLUCINAZIONI: tieni solo titoli ammessi
    titoli_validi = {lb["titolo"] for lb in LIBRI}
    scelte_raw = data.get("scelte", []) or []
    scelte_filtrate: List[Scelta] = []
    for s in scelte_raw:
        titolo = s.get("titolo")
        motivo = s.get("motivo", "")
        if isinstance(titolo, str) and titolo in titoli_validi and isinstance(motivo, str):
            scelte_filtrate.append(Scelta(titolo=titolo, motivo=motivo))

    # 7) FONTI: usa le nostre (evita quelle inventate)
    fonti_out: List[Fonte] = []
    for (pt, url, extr) in fonti:
        if pt and url and extr:
            fonti_out.append(Fonte(titolo=pt, url=url))

    note = data.get("note") or ""
    return ConsigliaOut(scelte=scelte_filtrate, note=note, fonti=fonti_out)

# -------------------- ENDPOINTS --------------------
@app.post("/consiglia", response_model=ConsigliaOut)
def consiglia(body: ConsigliaIn):
    return consiglia_core(body.testo_utente)

@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    msg = (body.messaggio or "").strip()
    if not msg:
        return ChatOut(risposta="Dimmi pure: preferenze di lettura, genere, mood? Posso consigliarti tra i miei titoli.")

    intent = classify_intent(msg)

    if intent == "greeting":
        return ChatOut(
            risposta="Ciao! 👋 Come posso aiutarti? Se mi dici genere, mood o lunghezza, ti consiglio un titolo tra i miei."
        )

    if intent == "book_reco":
        out = consiglia_core(msg)
        if not out.scelte:
            return ChatOut(
                risposta=out.note or "Non ho trovato una corrispondenza chiara. Specifica genere/mood/lunghezza."
            )
        first = out.scelte[0]
        fonte = f" Fonte: {out.fonti[0].titolo}." if out.fonti else ""
        return ChatOut(risposta=f"Ti propongo: **{first.titolo}** — {first.motivo}.{fonte}")

    # chitchat generico
    sys = (
        "Sei un assistente cordiale. Rispondi in italiano, in modo breve e chiaro. "
        "Se l'utente chiede consigli di lettura, invitalo a specificare genere/mood/lunghezza."
    )
    prompt = f"SYSTEM:\n{sys}\n\nUTENTE:\n{msg}\n\nASSISTENTE:"
    raw = ask_ollama(prompt)
    risposta = raw.strip() or "Dimmi pure su che genere o mood ti va: posso aiutarti a scegliere."
    return ChatOut(risposta=risposta)

# endpoint di test
@app.get("/")
def read_root():
    return {"message": "Mini LLM API pronta 🚀 Usa POST /consiglia o POST /chat"}
