from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from litellm import completion
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Richiesta(BaseModel):
    testo: str
    storico: list = []

@app.post("/chiedi")
async def chiedi(req: Richiesta):
    messaggi = [
        {
            "role": "system",
            "content": "Ti chiami Zoe e sei un'assistente personale intelligente, simpatica e informale. Rispondi sempre in italiano in modo naturale, diretto e pertinente alla domanda dell'utente."
        }
    ]
    
    # Aggiunge lo storico recente (ultimi 6 messaggi per non appesantire)
    for m in req.storico[-6:]:
        messaggi.append({"role": m["role"], "content": m["content"]})
        
    messaggi.append({"role": "user", "content": req.testo})

    # Modelli gratuiti in cascata (se uno fallisce o è occupato, passa al successivo)
    modelli = [
        "groq/llama-3.3-70b-versatile",
        "gemini/gemini-2.0-flash",
        "openrouter/google/gemma-2-9b-it:free"
    ]

    for modello in modelli:
        try:
            risposta = completion(model=modello, messages=messaggi)
            testo_risposta = risposta.choices[0].message.content
            return {"risposta": testo_risposta, "modello": modello}
        except Exception as e:
            print(f"Errore con {modello}: {e}")
            continue

    return {"risposta": "Ops, al momento i server AI sono un po' intasati. Riprova tra un attimo!", "modello": "nessuno"}
