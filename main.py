from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from litellm import completion

app = FastAPI()

# Permette alla tua pagina web di comunicare col server cloud
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Richiesta(BaseModel):
    testo: str

# Catena di modelli 100% gratuiti in ordine di priorità
MODELLI_GRATIS = [
    "gemini/gemini-2.5-flash",
    "groq/openai/gpt-oss-120b",
    "groq/qwen/qwen3.8-27b",
    "openrouter/google/gemma-4-31b-it:free"
]

@app.get("/")
def home():
    return {"stato": "Assistente Cloud Attivo"}

@app.post("/chiedi")
def chiedi_ai(dati: Richiesta):
    try:
        risposta = completion(
            model=MODELLI_GRATIS[0],
            messages=[
                
            {
                "role": "system",
                "content": "Ti chiami Zoe e sei un assistente personale intelligente, informale e molto elastico. Comprendi qualsiasi formulazione colloquiale. Se l'utente ti chiede l'ora o la data attuale, rispondi usando i riferimenti temporali corretti. Rispondi sempre in italiano in modo naturale, diretto e amichevole."
            }
        ],
            fallbacks=MODELLI_GRATIS[1:]
        )
        return {
            "risposta": risposta.choices[0].message.content,
            "modello": risposta.model
        }
    except Exception as e:
        return {
            "risposta": "Al momento tutti i modelli gratuiti hanno raggiunto il limite. Riprova tra poco.",
            "errore": str(e)
        }
