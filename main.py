from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from litellm import completion
import asyncio
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
    return {"stato": "Zoe Multi-Agent Evolution System Online"}

@app.post("/chiedi")
async def chiedi(req: Richiesta):
    testo_lower = req.testo.lower()
    
    # Riconosce se vuoi che Zoe si auto-migliori o scriva codice
    is_meta_coder = any(k in testo_lower for k in [
        "migliorati", "auto-migliora", "codice", "script", "funzione", 
        "programma", "patch", "aggiorna", "analizza il tuo codice", "ottimizza"
    ])
    
    if is_meta_coder:
        system_prompt = (
            "Sei l'Agente Meta-Programmatore di Zoe. Il tuo obiettivo è analizzare il codice, "
            "progettare miglioramenti strutturali, scrivere codice pulito, commentato e privo di errori "
            "in Python, FastAPI o JavaScript. Non usare mai emoji o asterischi. Rispondi in modo tecnico."
        )
        # Modelli avanzati per la logica e il coding
        modelli = [
            "openrouter/deepseek/deepseek-r1:free",
            "groq/llama-3.3-70b-versatile",
            "gemini/gemini-2.0-flash"
        ]
    else:
        system_prompt = (
            "Ti chiami Zoe e sei un'assistente di co-working intelligente e informale. "
            "Non usare emoji o asterischi nella voce. Rispondi in modo naturale e amichevole in italiano."
        )
        modelli = [
            "groq/llama-3.3-70b-versatile",
            "openrouter/openrouter/free",
            "gemini/gemini-2.0-flash"
        ]

    messaggi = [{"role": "system", "content": system_prompt}]
    
    for m in req.storico[-6:]:
        messaggi.append({"role": m["role"], "content": m["content"]})
        
    messaggi.append({"role": "user", "content": req.testo})

    async def esegui_chiamata():
        errori = []
        for modello in modelli:
            try:
                risposta = completion(model=modello, messages=messaggi)
                testo_risposta = risposta.choices[0].message.content
                return {"risposta": testo_risposta, "modello": f"{modello} (Agent)"}
            except Exception as e:
                errori.append(f"{modello}: {str(e)[:60]}")
                continue
        raise Exception("Tutti i modelli hanno fallito: " + " | ".join(errori))

    try:
        risultato = await asyncio.wait_for(esegui_chiamata(), timeout=60.0)
        return risultato
    except asyncio.TimeoutError:
        return {
            "risposta": "Errore critico: Nessun agente ha risposto entro 60 secondi. È colpa di Gemini e dei server cloud che stanno impiegando troppo tempo.",
            "modello": "timeout-error"
        }
    except Exception as err:
        return {
            "risposta": f"Errore del sistema multi-agente: {str(err)}",
            "modello": "errore"
        }
