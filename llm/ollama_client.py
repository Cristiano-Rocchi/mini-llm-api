# llm/ollama_client.py
# Client minimale per Ollama. Qui centralizzo le chiamate al modello,
# imposto uno "stile" coerente (temperatura bassa) e chiedo sempre JSON pulito.
# Le risposte vengono validate/parse e, se il modello sporca un po',
# provo a recuperare comunque il JSON.

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import requests


class LLMClient:
    """Piccolo wrapper per Ollama. Lo tengo semplice e chiaro."""

    def __init__(
        self,
        model: str = "llama3",
        host: str = "http://localhost:11434",
        timeout: int = 30,
        temperature: float = 0.2,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature

    # ---------- API pubblica ----------

    def write_json_summary(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Dato il contesto (titolo, autore, temi, ecc.), chiedo 2 campi:
        - trama_breve (max 2 frasi)
        - perche_consigliato (1–2 frasi, personalizzato)
        Ritorno sempre un dict o None se non riesco a parse-are il JSON.
        """
        system = (
            "Sei un assistente editoriale. Usi solo i dati forniti, "
            "non inventi nulla. Scrivi italiano naturale, tono semplice e concreto."
        )

        # Prompt molto diretto per ridurre libertà e allucinazioni
        user = (
            "GENERA SOLO JSON (niente testo prima o dopo). Campi obbligatori:\n"
            '  - "trama_breve": stringa (max 2 frasi)\n'
            '  - "perche_consigliato": stringa (1–2 frasi, personalizzato per l’utente)\n'
            "Se un dato non è disponibile, evita di citarlo. Non inserire altre chiavi.\n\n"
            "=== DATI ===\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

        txt = self._chat_single(system=system, user=user)
        if not txt:
            return None

        return self._parse_json_safe(txt)

    # (opzionale) esempio di classificatore d'intento, lo lascio pronto
    def classify_intent(self, text: str) -> Optional[str]:
        """Restituisce una etichetta semplice (es. 'saluto', 'consiglio_libro', 'altro')."""
        system = (
            "Sei un classificatore. Leggi il testo e scegli UNA sola label tra: "
            "saluto, consiglio_libro, info_libro, altro. Rispondi SOLO con la label."
        )
        user = f"Testo: {text.strip()}"
        txt = self._chat_single(system=system, user=user)
        if not txt:
            return None
        label = txt.strip().lower()
        # pulizia minima
        label = re.sub(r"[^a-z_]", "", label)
        return label or None

    # ---------- Ollama low-level ----------

    def _chat_single(self, system: str, user: str) -> Optional[str]:
        """Uso /api/generate per una singola turn (prompt unico).
        Tengo stream=False per ricevere la risposta tutta insieme.
        """
        url = f"{self.host}/api/generate"
        # creo un prompt "compatto": prima le istruzioni di sistema, poi l'utente
        prompt = f"<<SYS>>\n{system}\n<</SYS>>\n\n{user}"

        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }

        try:
            r = requests.post(url, json=body, timeout=self.timeout)
            if r.status_code != 200:
                return None
            js = r.json()
            # campo standard di Ollama per /generate
            return js.get("response")
        except Exception:
            return None

    # ---------- Utils ----------

    def _parse_json_safe(self, text: str) -> Optional[Dict[str, Any]]:
        """Provo a parse-are il JSON. Se la risposta ha testo extra,
        cerco la prima/dopo ultima graffa per estrarre il blocco JSON.
        """
        # tentativo diretto
        try:
            return json.loads(text)
        except Exception:
            pass

        # estrazione euristica tra { ... }
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            snippet = match.group(0)
            try:
                return json.loads(snippet)
            except Exception:
                return None

        return None
