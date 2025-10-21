"""
STRUTTURA DEL PROGETTO
=========================

──────────────────────────────
-- api/
│ ├─ routes.py → contiene le route FastAPI (endpoint HTTP)
│ └─ schemas.py → definisce i modelli Pydantic per request/response
│
-- core/
│ ├─ models.py → classi principali: Book, EnrichmentRecord, UserProfile
│ └─ config.py → configurazioni base (modello LLM, percorsi, costanti)
│
-- memory/
│ ├─ session_store.py → memoria conversazionale a breve termine (RAM)
│ └─ profile_store.py → profili utente e preferenze salvati in JSON
│
-- tools/
│ ├─ openlibrary_client.py → prende copertina, pagine, subjects da OpenLibrary
│ ├─ wikipedia_client.py → riassunto e link pagina da Wikipedia
│ └─ wikidata_client.py → anno, premi, generi e ambientazione da Wikidata
│
-- rag/
│ ├─ scoring.py → ranking e mapping dei generi (tassonomia MVP)
│ └─ embeddings.py → (opzionale) ricerche semantiche locali
│
-- llm/
│ ├─ ollama_client.py → parla con il modello LLM locale e restituisce JSON
│ └─ prompts.py → contiene eventuali prompt e schemi per i task
│
-- services/
│ ├─ enrichment_service.py → unisce i dati delle fonti esterne (OL/WP/WD)
│ └─ recommendation_service.py → flusso completo: ranking → enrichment → LLM → scheda libro
│
-- memory/
│ ├─ session_store.py → conserva la cronologia chat (solo runtime)
│ └─ profile_store.py → salva i gusti dell’utente su file
│
-- utils/
│ ├─ text.py → piccole funzioni per normalizzare testi/titoli
│ └─ http.py → (opzionale) retry/backoff per richieste API
│
-- data/
│ ├─ libri.py → la mia libreria personale (lista di dict)
│ └─ cache.json → cache locale dei dati arricchiti (OpenLibrary/Wiki)
│
──────────────────────────────
app.py → avvia FastAPI, crea i service e monta le route.
In pratica è il "main" dell’app.
──────────────────────────────
"""
