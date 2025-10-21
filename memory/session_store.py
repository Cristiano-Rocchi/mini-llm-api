# memory/session_store.py
# Qui gestisco la memoria "a breve termine" della chat (RAM).
# Mi serve per ricordare cosa ha chiesto l'utente durante la sessione.

from typing import Dict, List


class SessionStore:
    """Gestisce le conversazioni in RAM (volatile)."""

    def __init__(self):
        self.sessions: Dict[str, List[Dict[str, str]]] = {}

    def get(self, session_id: str) -> List[Dict[str, str]]:
        """Ritorna la cronologia di una sessione, o lista vuota se nuova."""
        return self.sessions.get(session_id, [])

    def append_message(self, session_id: str, role: str, text: str):
        """Aggiunge un messaggio alla cronologia (role = 'user' o 'assistant')."""
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        self.sessions[session_id].append({"role": role, "text": text})
