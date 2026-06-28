"""
Provenance Guard — Milestone 3
==============================

A minimal Flask backend that:
  1. Accepts creative content via POST /submit
  2. Runs ONE detection signal (Groq LLM classification)
  3. Returns a structured, transparency-focused response
  4. Writes a structured audit entry to a local JSON file
  5. Exposes the audit log via GET /log

Scope note (intentional):
  Only Signal 1 (Groq LLM classification) is implemented here.
  Stylometric heuristics, ensemble scoring, appeals, rate limiting,
  certificates, and analytics are deliberately NOT implemented yet.
  `confidence` and `label` are placeholders until Milestone 4, because
  real confidence should come from combining multiple signals — not
  from a single model's opinion.
"""

import os
import json
import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Load variables from a local .env file (e.g. GROQ_API_KEY=...).
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
AUDIT_LOG_PATH = "audit_log.json"

# The three attribution states the whole system is allowed to use.
# Keeping this as a single source of truth makes validation easy and
# prevents typos from leaking into responses or the audit log.
VALID_CLASSIFICATIONS = {"likely_ai", "uncertain", "likely_human"}

# Only initialize the Groq client if a key is actually present.
# If the key is missing, classify_with_groq() falls back to a safe
# "uncertain" result instead of crashing the server on startup.
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
if client is None:
    print("[WARN] GROQ_API_KEY not found. Classification will default to 'uncertain'.")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Audit log helpers (simple JSON file storage)
# ---------------------------------------------------------------------------
def ensure_audit_log_exists():
    """Create audit_log.json with an empty entries list if it doesn't exist."""
    if not os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump({"entries": []}, f, indent=2)


def read_audit_log():
    """Return the list of audit entries. Returns [] if the file is missing
    or corrupted, so a bad log file never takes down GET /log."""
    ensure_audit_log_exists()
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Defensive: make sure we got the shape we expect.
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def append_audit_entry(entry):
    """Append a single audit entry and persist the whole log back to disk.

    This is a read-modify-write on a JSON file, which is fine for a
    single-process starter project. It will be replaced by a real
    datastore in a later milestone.
    """
    entries = read_audit_log()
    entries.append(entry)
    with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, indent=2)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------
def error_response(message, status_code):
    """Return a consistent, structured JSON error."""
    return jsonify({"error": message, "status": "error"}), status_code


# ---------------------------------------------------------------------------
# Signal 1: Groq LLM Classification
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a content provenance classifier for a creative-sharing platform. "
    "Given a piece of text, estimate whether it reads as AI-generated, "
    "human-written, or uncertain.\n\n"
    "Respond with ONLY a JSON object (no surrounding text, no markdown) using "
    "exactly these keys:\n"
    '  - "classification": one of "likely_ai", "uncertain", "likely_human"\n'
    '  - "score": a number from 0.0 to 1.0 representing AI likelihood, where '
    "0.0 = strongly human-written, 0.5 = uncertain, 1.0 = strongly AI-generated\n"
    '  - "reasoning": one or two short sentences explaining what you noticed.\n\n'
    "Be cautious: when signals are weak or mixed, prefer 'uncertain'. "
    "Mislabeling genuine human work as AI is a serious harm."
)


def normalize_signal(data):
    """Coerce a raw model dict into the exact signal shape we trust.

    Anything unexpected (missing keys, out-of-range score, unknown
    classification) is safely defaulted rather than passed through.
    """
    classification = data.get("classification")
    if classification not in VALID_CLASSIFICATIONS:
        classification = "uncertain"

    # Clamp score into [0.0, 1.0]; default to 0.5 if it isn't a number.
    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        score = 0.5
    score = max(0.0, min(1.0, score))

    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning = "No reasoning provided."

    return {
        "classification": classification,
        "score": score,
        "reasoning": reasoning.strip(),
    }


def classify_with_groq(text):
    """Ask the Groq model to classify the text.

    Always returns a predictable dict:
        {"classification": ..., "score": float, "reasoning": str}

    If the API key is missing or the call fails for any reason, it returns
    a safe "uncertain" result instead of raising — the server must never
    crash because of an upstream model issue.
    """
    safe_default = {
        "classification": "uncertain",
        "score": 0.5,
        "reasoning": "Classification unavailable; defaulting to uncertain.",
    }

    if client is None:
        return safe_default

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            # Ask Groq to guarantee a JSON object back.
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)
        return normalize_signal(parsed)
    except Exception as exc:  # network error, JSON error, API error, etc.
        print(f"[WARN] Groq classification failed: {exc}")
        return safe_default


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/submit", methods=["POST"])
def submit():
    """Validate a submission, run Signal 1, log it, and return the result."""
    # --- Parse the JSON body defensively ---
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("Request body must be a valid JSON object.", 400)

    creator_id = body.get("creator_id")
    content_type = body.get("content_type")
    text = body.get("text")

    # --- Validation ---
    if not isinstance(creator_id, str) or not creator_id.strip():
        return error_response(
            "creator_id is required and must be a non-empty string.", 400
        )

    if not isinstance(content_type, str) or not content_type.strip():
        return error_response("content_type is required.", 400)

    # Milestone 3 only supports text. Anything else is a structured 400.
    if content_type != "text":
        return error_response(
            f"Unsupported content_type '{content_type}'. "
            "Milestone 3 supports 'text' only.",
            400,
        )

    if not isinstance(text, str) or not text.strip():
        return error_response(
            "text is required and must be a non-empty string "
            "for content_type 'text'.",
            400,
        )

    # --- Run the detection pipeline (Signal 1 only for now) ---
    signal = classify_with_groq(text)

    # --- Build identifiers and metadata ---
    content_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # --- Assemble the response ---
    # NOTE: `confidence` and `label` are placeholders. Real confidence will
    # come from ensemble scoring across multiple signals in a later milestone.
    response_body = {
        "content_id": content_id,
        "creator_id": creator_id,
        "content_type": content_type,
        "attribution": signal["classification"],
        "confidence": 0.0,  # placeholder until Milestone 5
        "label": "Placeholder label until Milestone 5.",
        "signals": {
            "llm_score": signal["score"],
            "llm_reasoning": signal["reasoning"],
        },
        "status": "classified",
    }

    # --- Write the audit entry ---
    append_audit_entry(
        {
            "event_type": "submission_classified",
            "timestamp": timestamp,
            "content_id": content_id,
            "creator_id": creator_id,
            "content_type": content_type,
            "attribution": signal["classification"],
            "confidence": 0.0,
            "llm_score": signal["score"],
            "llm_reasoning": signal["reasoning"],
            "status": "classified",
        }
    )

    return jsonify(response_body), 200


@app.route("/log", methods=["GET"])
def get_log():
    """Return all audit entries recorded so far."""
    return jsonify({"entries": read_audit_log()}), 200


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ensure_audit_log_exists()
    app.run(host="0.0.0.0", port=5000, debug=True)