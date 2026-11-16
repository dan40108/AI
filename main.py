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

@app.get("/")
async def home():
    return {"stato": "Zoe Backend Online"}

@app.post("/chiedi")
async def chiedi(req: Richiesta):
    messaggi = [
        {
            "role": "system",
            "content": "Ti chiami Zoe e sei un'assistente personale intelligente, simpatica e informale. Rispondi sempre in italiano in modo naturale, diretto e pertinente alla domanda dell'utente."
        }
    ]
    
    for m in req.storico[-6:]:
        messaggi.append({"role": m["role"], "content": m["content"]})
        
    messaggi.append({"role": "user", "content": req.testo})

    modelli = [
        "openrouter/openrouter/free",
        "groq/llama-3.3-70b-versatile",
        "groq/llama-3.1-8b-instant",
        "gemini/gemini-2.0-flash-lite",
        "openrouter/meta-llama/llama-3.3-70b-instruct:free"
    ]

    errori = []
    for modello in modelli:
        try:
            risposta = completion(model=modello, messages=messaggi)
            testo_risposta = risposta.choices[0].message.content
            return {"risposta": testo_risposta, "modello": modello}
        except Exception as e:
            errori.append(f"{modello}: {str(e)[:80]}")
            continue

    return {"risposta": "Dettaglio errori:\n" + "\n".join(errori), "modello": "nessuno"}
