import asyncio
import base64
import os
import re
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from litellm import completion
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dan40108.github.io"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GITHUB_REPO = "dan40108/AI"
GITHUB_BRANCH = "main"
FILE_CONSENTITI = {"main.py", "index.html"}


class Richiesta(BaseModel):
    testo: str
    storico: list = []


class RichiestaAutoAggiorna(BaseModel):
    file: str
    istruzione: str


def _headers_github() -> dict:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Variabile GITHUB_TOKEN non impostata su Render.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def leggi_file_github(percorso_file: str) -> tuple[str, str]:
    if percorso_file not in FILE_CONSENTITI:
        raise ValueError(f"File non consentito: {percorso_file}")

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{percorso_file}"
    params = {"ref": GITHUB_BRANCH}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_headers_github(), params=params)
        resp.raise_for_status()
        dati = resp.json()

    contenuto_b64 = dati.get("content", "").replace("\n", "")
    contenuto_testo = base64.b64decode(contenuto_b64).decode("utf-8")
    sha = dati.get("sha", "")
    return contenuto_testo, sha


async def scrivi_file_github(percorso_file: str, nuovo_contenuto: str, sha: str, messaggio_commit: str) -> str:
    if percorso_file not in FILE_CONSENTITI:
        raise ValueError(f"File non consentito: {percorso_file}")

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{percorso_file}"
    contenuto_b64 = base64.b64encode(nuovo_contenuto.encode("utf-8")).decode("utf-8")

    payload = {
        "message": messaggio_commit,
        "content": contenuto_b64,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.put(url, headers=_headers_github(), json=payload)
        resp.raise_for_status()
        dati = resp.json()

    commit = dati.get("commit", {})
    return commit.get("sha", "ok")[:7]


def _estrai_file_richiesto(testo_lower: str) -> str:
    if "index.html" in testo_lower or "frontend" in testo_lower or "interfaccia" in testo_lower:
        return "index.html"
    return "main.py"


def _pulisci_blocco_codice(testo_llm: str) -> str:
    testo_llm = testo_llm.strip()
    match = re.search(r"```(?:python|html|javascript|js)?\s*\n([\s\S]*?)\n```", testo_llm, re.IGNORECASE)
    if match:
        return match.group(1)
    return testo_llm


def _chiama_modelli_sync(modelli: list[str], messaggi: list[dict]) -> tuple[str, str]:
    errori = []
    for modello in modelli:
        try:
            risposta = completion(model=modello, messages=messaggi)
            testo_risposta = risposta.choices[0].message.content
            if testo_risposta and testo_risposta.strip():
                return testo_risposta, f"{modello} (Agent)"
        except Exception as e:
            errori.append(f"{modello}: {str(e)[:60]}")
            continue
    raise Exception("Tutti i modelli hanno fallito: " + " | ".join(errori))


async def esegui_modello(modelli: list[str], messaggi: list[dict], timeout_sec: float = 60.0) -> dict:
    testo_risposta, modello_agent = await asyncio.wait_for(
        asyncio.to_thread(_chiama_modelli_sync, modelli, messaggi),
        timeout=timeout_sec,
    )
    return {"risposta": testo_risposta, "modello": modello_agent}


@app.get("/")
async def home():
    return {"stato": "Zoe Multi-Agent Evolution System Online"}


@app.post("/auto-aggiorna")
async def auto_aggiorna(req: RichiestaAutoAggiorna):
    target_file = req.file.strip()
    if target_file not in FILE_CONSENTITI:
        return {"risposta": "Puoi modificare solo main.py o index.html.", "modello": "validation-error"}

    try:
        codice_attuale, sha_attuale = await leggi_file_github(target_file)
    except Exception as e:
        return {"risposta": f"Errore lettura {target_file} da GitHub: {str(e)}", "modello": "github-read-error"}

    system_prompt = (
        "Sei l'Agente Meta-Programmatore di Zoe. Ricevi il file sorgente attuale e un'istruzione di modifica. "
        "Restituisci ESCLUSIVAMENTE il nuovo file completo e funzionante, senza commenti introduttivi, "
        "senza spiegazioni, senza emoji e senza asterischi."
    )
    user_prompt = (
        f"File: {target_file}\n"
        f"Istruzione: {req.istruzione}\n\n"
        f"Codice attuale:\n{codice_attuale}"
    )

    modelli_coder = [
        "groq/llama-3.3-70b-versatile",
        "gemini/gemini-2.0-flash",
        "openrouter/openrouter/free",
    ]

    try:
        res = await esegui_modello(
            modelli_coder,
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            timeout_sec=60.0,
        )
        nuovo_codice = _pulisci_blocco_codice(res["risposta"])
        if not nuovo_codice or len(nuovo_codice) < 40:
            return {"risposta": "Il modello ha restituito un codice vuoto o troppo corto; commit annullato.", "modello": res["modello"]}

        if target_file == "main.py":
            compile(nuovo_codice, "main.py", "exec")

        commit_short = await scrivi_file_github(
            target_file,
            nuovo_codice,
            sha_attuale,
            f"Zoe auto-update {target_file}: {req.istruzione[:60]}",
        )
        return {
            "risposta": f"Ho aggiornato {target_file} su GitHub (commit {commit_short}). Render/GitHub Pages avvieranno l'aggiornamento automatico.",
            "modello": res["modello"],
        }
    except SyntaxError as se:
        return {"risposta": f"Modifica bloccata: errore di sintassi Python alla riga {se.lineno}: {se.msg}.", "modello": "syntax-guard"}
    except asyncio.TimeoutError:
        return {
            "risposta": "Errore critico: Nessun agente ha risposto entro 60 secondi. È colpa di Gemini e dei server cloud che stanno impiegando troppo tempo.",
            "modello": "timeout-error",
        }
    except Exception as err:
        return {"risposta": f"Errore durante l'auto-aggiornamento: {str(err)}", "modello": "auto-update-error"}


@app.post("/chiedi")
async def chiedi(req: Richiesta):
    testo_lower = req.testo.lower()

    is_auto_apply = any(k in testo_lower for k in [
        "aggiorna il tuo codice", "modifica il tuo codice", "applica la modifica",
        "scrivi nel file", "salva su github", "auto-aggiorna", "fai il commit"
    ])

    is_meta_coder = is_auto_apply or any(k in testo_lower for k in [
        "migliorati", "auto-migliora", "codice", "script", "funzione",
        "programma", "patch", "aggiorna", "analizza il tuo codice", "ottimizza",
        "leggi il tuo codice", "che codice hai"
    ])

    if is_auto_apply:
        target_file = _estrai_file_richiesto(testo_lower)
        return await auto_aggiorna(RichiestaAutoAggiorna(file=target_file, istruzione=req.testo))

    if is_meta_coder:
        target_file = _estrai_file_richiesto(testo_lower)
        try:
            codice_letto, _ = await leggi_file_github(target_file)
            contesto_file = f"\n\nContenuto attuale di {target_file} su GitHub:\n```\n{codice_letto[:12000]}\n```"
        except Exception as e:
            contesto_file = f"\n\n[Nota: impossibile leggere {target_file} da GitHub: {str(e)}]"

        system_prompt = (
            "Sei l'Agente Meta-Programmatore di Zoe. Il tuo obiettivo è analizzare il codice, "
            "progettare miglioramenti strutturali, scrivere codice pulito, commentato e privo di errori "
            "in Python, FastAPI o JavaScript. Non usare mai emoji o asterischi. Rispondi in modo tecnico."
        )
        modelli = [
            "groq/llama-3.3-70b-versatile",
            "gemini/gemini-2.0-flash",
            "openrouter/openrouter/free",
        ]
        messaggi = [{"role": "system", "content": system_prompt}]
        for m in req.storico[-6:]:
            messaggi.append({"role": m["role"], "content": m["content"]})
        messaggi.append({"role": "user", "content": f"{req.testo}{contesto_file}"})
    else:
        system_prompt = (
            "Ti chiami Zoe e sei un'assistente di co-working intelligente e informale. "
            "Non usare emoji o asterischi nella voce. Rispondi in modo naturale e amichevole in italiano."
        )
        modelli = [
            "groq/llama-3.3-70b-versatile",
            "openrouter/openrouter/free",
            "gemini/gemini-2.0-flash",
        ]
        messaggi = [{"role": "system", "content": system_prompt}]
        for m in req.storico[-6:]:
            messaggi.append({"role": m["role"], "content": m["content"]})
        messaggi.append({"role": "user", "content": req.testo})

    try:
        return await esegui_modello(modelli, messaggi, timeout_sec=60.0)
    except asyncio.TimeoutError:
        return {
            "risposta": "Errore critico: Nessun agente ha risposto entro 60 secondi. È colpa di Gemini e dei server cloud che stanno impiegando troppo tempo.",
            "modello": "timeout-error",
        }
    except Exception as err:
        return {
            "risposta": f"Errore del sistema multi-agente: {str(err)}",
            "modello": "errore",
        }