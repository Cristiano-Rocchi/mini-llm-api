# memory/profile_store.py
# Qui salvo e carico le preferenze utente su file JSON.
# Così posso ricordare cosa gli piace anche dopo che riavvio il server.

import json
from pathlib import Path
from typing import Optional
from core.models import UserProfile

PROFILE_PATH = Path("data/profiles.json")


class ProfileStore:
    """Gestisce i profili utente in un semplice file JSON."""

    def __init__(self):
        self.path = PROFILE_PATH
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, user_id: str) -> UserProfile:
        """Ritorna il profilo di un utente o ne crea uno nuovo."""
        if user_id not in self.data:
            self.data[user_id] = UserProfile(user_id=user_id).model_dump()
            self._save()
        return UserProfile(**self.data[user_id])

    def update(self, profile: UserProfile):
        """Aggiorna e salva il profilo."""
        self.data[profile.user_id] = profile.model_dump()
        self._save()
