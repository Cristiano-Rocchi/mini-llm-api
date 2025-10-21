# api/routes.py
# Qui definisco le route FastAPI. Tengo gli endpoint sottili: validano input,
# chiamano i service e ritornano i DTO (schemas). Niente logiche "pesanti" qui.

from fastapi import APIRouter, HTTPException
from typing import Protocol, Optional, Any, Dict

from .schemas import AskRequest, AskResponse, BookCard


class RecommendationServiceProtocol(Protocol):
    """Interfaccia minima del service che uso qui (così non ho import circolari).
    L'implementazione vera vivrà in services/recommendation_service.py
    """
    def recommend(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Any: ...
    # Ritorna un dict con {"mode": "message", "message": "..."} oppure
    # {"mode": "book", "result": BookCard}


def get_router(recommendation_service: RecommendationServiceProtocol) -> APIRouter:
    """Factory del router: mi passo da app.py il service già costruito.
    In questo modo separo bene i livelli e in test posso fare mocking.
    """
    router = APIRouter()

    @router.get("/health")
    def health():
        """Endpoint di salute: mi serve per capire al volo se il server è su."""
        return {"status": "ok"}

    @router.post("/ask", response_model=AskResponse)
    def ask(payload: AskRequest):
        """Endpoint principale: riceve la domanda dell'utente e risponde.
        Se è small talk restituisco un messaggio guida; altrimenti una scheda libro.
        """
        try:
            out: Dict[str, Any] = recommendation_service.recommend(
                query=payload.query,
                user_id=payload.user_id,
                session_id=payload.session_id,
            )

            # Caso messaggio (small talk / saluto)
            if out.get("mode") == "message":
                return AskResponse(mode="message", message=out.get("message"))

            # Caso scheda libro
            result = out.get("result")
            if isinstance(result, BookCard):
                return AskResponse(mode="book", result=result)

            # Se arrivo qui, qualcosa non torna nel service
            raise HTTPException(status_code=500, detail="Formato risposta non valido dal servizio")

        except HTTPException:
            # Se il service ha già lanciato un HTTPException, la rilancio uguale.
            raise
        except Exception as exc:
            # Non sputtano stack trace all'utente: messaggio pulito e stop.
            # I dettagli me li guardo nei log del server.
            raise HTTPException(status_code=500, detail="Errore interno durante la generazione del consiglio") from exc

    return router
