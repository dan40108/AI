import json
import os
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore

_db = None


def get_db():
    global _db
    if _db is not None:
        return _db

    raw_creds = os.getenv("FIREBASE_CREDENTIALS", "").strip()
    if not raw_creds:
        raise RuntimeError("Variabile d'ambiente FIREBASE_CREDENTIALS mancante.")

    # Supporta sia il JSON incollato direttamente (es. su Render) sia un percorso a file in locale
    if raw_creds.startswith("{"):
        cred_dict = json.loads(raw_creds)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate(raw_creds)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    _db = firestore.client()
    return _db


def get_user_profile() -> dict:
    doc = get_db().collection("user_profile").document("main").get()
    return doc.to_dict() if doc.exists else {}


def update_user_profile(data: dict, merge: bool = True):
    get_db().collection("user_profile").document("main").set(data, merge=merge)


def get_current_context() -> dict:
    doc = get_db().collection("current_context").document("active").get()
    return doc.to_dict() if doc.exists else {}


def overwrite_current_context(summary: str, topic: str = ""):
    """Sovrascrive completamente il riassunto precedente (nessun merge)."""
    payload = {
        "summary": summary,
        "topic": topic,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    get_db().collection("current_context").document("active").set(payload, merge=False)
