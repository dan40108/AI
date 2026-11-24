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

WMO_METEO_IT = {
    0: "cielo sereno",
    1: "prevalentemente sereno",
    2: "parzialmente nuvoloso",
    3: "coperto",
    45: "nebbia",
    48: "nebbia con brina",
    51: "pioviggine leggera",
    53: "pioviggine moderata",
    55: "pioviggine intensa",
    61: "pioggia debole",
    63: "pioggia moderata",
    65: "pioggia forte",
    71: "neve debole",
    73: "neve moderata",
    75: "neve intensa",
    80: "rovesci leggeri",
    81: "rovesci moderati",
    82: "rovesci violenti",
    95: "temporale",
    96: "temporale con grandine",
    99: "forte temporale con grandine",
}


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


def _valida_coerenza_file(target_file: str, contenuto: str) -> tuple[bool, str]:
    testo_check = contenuto.strip()
    lower = testo_check.lower()

    if target_file == "index.html":
        ha_html = ("<!doctype html" in lower) or ("<html" in lower) or ("<body" in lower) or ("<div" in lower)
        sembra_python = bool(
            re.search(r"^\s*(from\s+\w+|import\s+\w+|def\s+\w+|async\s+def\s+\w+|@app\.)", testo_check, re.MULTILINE)
        )
        if not ha_html or sembra_python:
            return False, "Il contenuto generato non è HTML valido per index.html (sembra codice Python o testo non HTML)."
        return True, ""

    if target_file == "main.py":
        sembra_html = ("<!doctype html" in lower) or ("<html" in lower)
        ha_python = ("def " in testo_check) or ("import " in testo_check)
        if sembra_html or not ha_python:
            return False, "Il contenuto generato non sembra codice Python valido per main.py."
        return True, ""

    return False, "File non supportato."


def _è_richiesta_meteo(testo: str) -> bool:
    testo_lower = testo.lower().strip()
    if len(testo_lower) > 95:
        return False
    parole_tecniche = [
        "codice", "script", "html", "css", "js", "python", "fastapi", "litellm",
        "modifica", "aggiorna", "auto-aggiorna", "bug", "prompt", "main.py", "index.html", "github", "render"
    ]
    if any(p in testo_lower for p in parole_tecniche):
        return False
    return any(k in testo_lower for k in ["meteo", "che tempo", "previsioni"])


def _estrai_citta_e_giorno(testo: str) -> tuple[str, int, str]:
    lower = testo.lower()
    if "dopodomani" in lower:
        giorno_idx, etichetta = 2, "dopodomani"
    elif "domani" in lower:
        giorno_idx, etichetta = 1, "domani"
    else:
        giorno_idx, etichetta = 0, "oggi"

    match_prep = re.search(
        r"\b(?:a|ad|per|su|in|di)\s+([a-zA-ZÀ-ÿ'’\-]+(?:\s+[a-zA-ZÀ-ÿ'’\-]+){0,2})",
        testo,
        re.IGNORECASE,
    )
    if match_prep:
        candidato = match_prep.group(1)
        candidato = re.sub(
            r"\b(oggi|domani|dopodomani|adesso|ora|subito|per favore|grazie)\b",
            "",
            candidato,
            flags=re.IGNORECASE,
        ).strip(" ?.,!\"'")
        if candidato and candidato.lower() not in {"il", "la", "lo", "le", "gli", "un", "una", "uno", "citta", "città"}:
            return candidato.title(), giorno_idx, etichetta

    ripulito = re.sub(
        r"\b(zoe|che|tempo|fa|farà|meteo|previsioni|del|per|oggi|domani|dopodomani|a|ad|in|su|di|dimmi|dici|mi)\b",
        "",
        testo,
        flags=re.IGNORECASE,
    ).strip(" ?.,!\"'")
    citta = ripulito.title() if ripulito else "Torino"
    return citta, giorno_idx, etichetta


async def ottieni_meteo_dinamico(testo: str) -> dict:
    citta, giorno_idx, etichetta = _estrai_citta_e_giorno(testo)
    url_fallback = f"https://www.google.com/search?q=meteo+{httpx.QueryParams({'q': citta})['q']}" + ("+domani" if giorno_idx == 1 else "")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": citta, "count": 1, "language": "it", "format": "json"},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()

            risultati = geo_data.get("results") or []
            if not risultati:
                return {
                    "risposta": f"Non ho trovato la località {citta}. Ti apro la ricerca meteo su Google.",
                    "url": url_fallback,
                }

            loc = risultati[0]
            nome_citta = loc.get("name", citta)
            lat = loc["latitude"]
            lon = loc["longitude"]

            meteo_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 3,
                },
            )
            meteo_resp.raise_for_status()
            dati = meteo_resp.json()

        daily = dati.get("daily", {})
        codici = daily.get("weather_code", [])
        t_min_list = daily.get("temperature_2m_min", [])
        t_max_list = daily.get("temperature_2m_max", [])
        prob_list = daily.get("precipitation_probability_max", [])

        if giorno_idx >= len(codici) or giorno_idx >= len(t_min_list) or giorno_idx >= len(t_max_list):
            return {
                "risposta": f"Non ho trovato i dati meteo per {nome_citta} per {etichetta}.",
                "url": url_fallback,
            }

        desc_giorno = WMO_METEO_IT.get(codici[giorno_idx], "condizioni variabili")
        t_min = round(t_min_list[giorno_idx])
        t_max = round(t_max_list[giorno_idx])
        prob_pioggia = prob_list[giorno_idx] if giorno_idx < len(prob_list) and prob_list[giorno_idx] is not None else 0

        if giorno_idx == 0 and dati.get("current"):
            t_attuale = round(dati["current"]["temperature_2m"])
            desc_attuale = WMO_METEO_IT.get(dati["current"]["weather_code"], desc_giorno)
            risposta = (
                f"A {nome_citta} oggi ci sono {t_attuale} gradi con {desc_attuale}. "
                f"Minima {t_min} gradi, massima {t_max} gradi, probabilità di pioggia {prob_pioggia} percento."
            )
        else:
            risposta = (
                f"A {nome_citta} per {etichetta} è previsto {desc_giorno}, "
                f"con minima di {t_min} gradi, massima di {t_max} gradi e probabilità di pioggia del {prob_pioggia} percento."
            )

        url_citta = f"https://www.google.com/search?q=meteo+{httpx.QueryParams({'q': nome_citta})['q']}" + ("+domani" if giorno_idx == 1 else "")
        return {"risposta": risposta, "url": url_citta}

    except Exception:
        return {
            "risposta": f"Ecco le previsioni meteo per {citta} ({etichetta}).",
            "url": url_fallback,
        }


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

    if target_file == "index.html":
        regola_formato = (
            "Il file di destinazione è index.html: devi restituire ESCLUSIVAMENTE codice HTML completo "
            "che inizi con <!DOCTYPE html> o <html e termini con </html>. "
            "Non scrivere MAI codice Python, MAI commenti introduttivi, MAI spiegazioni prima o dopo, MAI emoji e MAI asterischi."
        )
    else:
        regola_formato = (
            "Il file di destinazione è main.py: devi restituire ESCLUSIVAMENTE codice Python valido e completo "
            "senza markup HTML, senza commenti introduttivi, senza spiegazioni, senza emoji e senza asterischi."
        )

    system_prompt = (
        "Sei l'Agente Meta-Programmatore di Zoe. Ricevi il file sorgente attuale e un'istruzione di modifica. "
        f"{regola_formato}"
    )
    user_prompt = (
        f"File: {target_file}\n"
        f"Istruzione: {req.istruzione}\n\n"
        f"Codice attuale:\n{codice_attuale}"
    )

    modelli_coder = [
        "gemini/gemini-2.0-flash",
        "groq/llama-3.3-70b-versatile",
        "openrouter/openrouter/free",
    ]

    try:
        res = await esegui_modello(
            modelli_coder,
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            timeout_sec=300.0,
        )
        nuovo_codice = _pulisci_blocco_codice(res["risposta"])
        if not nuovo_codice or len(nuovo_codice) < 40:
            return {"risposta": "Il modello ha restituito un codice vuoto o troppo corto; commit annullato.", "modello": res["modello"]}

        if target_file == "main.py":
            compile(nuovo_codice, "main.py", "exec")

        ok_file, motivo_blocco = _valida_coerenza_file(target_file, nuovo_codice)
        if not ok_file:
            return {
                "risposta": f"Commit bloccato per sicurezza: {motivo_blocco}",
                "modello": "content-guard",
            }

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

    if _è_richiesta_meteo(req.testo):
        dati_meteo = await ottieni_meteo_dinamico(req.testo)
        return {
            "risposta": dati_meteo["risposta"],
            "url": dati_meteo["url"],
            "azione": "apri_link",
            "modello": "open-meteo",
        }

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
        timeout_richiesta = 180.0
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
        timeout_richiesta = 60.0

    try:
        return await esegui_modello(modelli, messaggi, timeout_sec=timeout_richiesta)
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
