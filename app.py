# app.py
# Questo è il punto d’ingresso dell’app.
# Qui creo FastAPI, istanzio i vari servizi e monto le route.
# Tutto il resto (logica, AI, fonti) è nei moduli dedicati.

from fastapi import FastAPI
from api.routes import get_router
from services.enrichment_service import EnrichmentService
from services.recommendation_service import RecommendationService
from llm.ollama_client import LLMClient
from fastapi.middleware.cors import CORSMiddleware


# --- Inizializzazione componenti principali ---

# Creo il client per Ollama (LLM locale)
llm_client = LLMClient(
    model="llama3",  # modello di default
    host="http://localhost:11434",
    temperature=0.2
)

# Creo il servizio di arricchimento (OpenLibrary + Wikipedia + Wikidata)
enrichment_service = EnrichmentService()

# Creo il servizio principale che usa entrambi
recommendation_service = RecommendationService(enrichment_service, llm_client)

# --- Configurazione FastAPI ---

app = FastAPI(
    title="Mini LLM Books Agent",
    description="Un piccolo agente AI che consiglia e descrive i libri della mia libreria",
    version="1.0.0"
)

# 👇 abilito CORS per permettere richieste da file:// o da altre origini (es. index.html)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # per test va bene *, in produzione limita ai tuoi domini
    allow_credentials=False,    # deve restare False se usi "*"
    allow_methods=["*"],        # abilita anche OPTIONS
    allow_headers=["*"],
)


# Monta le route passando il service
app.include_router(get_router(recommendation_service))

# Endpoint base opzionale (solo per test)
@app.get("/")
def root():
    """Pagina base per verificare che l'app sia su."""
    return {"message": "Mini LLM Agent attivo 🚀"}

