"""
Provenance Guard - Milestone 5
==============================

A Flask backend that:
  1. Accepts creative content via POST /submit
  2. Runs a FOUR-signal detection ensemble:
        Signal 1 - Groq LLM classification        (weight 0.40)
        Signal 2 - Stylometric heuristics          (weight 0.30)
        Signal 3 - Repetition / template patterns  (weight 0.20)
        Signal 4 - Provenance metadata             (weight 0.10)
  3. Combines the signals into a real confidence score
  4. Returns a structured, transparency-focused response with a real label
  5. Writes a structured audit entry to a local JSON file
  6. Exposes the audit log via GET /log

Milestone 5 adds the trust + accountability layer (all NEW this milestone):
  - Real transparency-label generation (replaces the placeholder label)
  - Appeal submission   : POST  /appeal
  - Appeal review        : PATCH /appeal/<content_id>
  - Human verification   : POST  /verify-human
  - Certificate lookup   : GET   /certificate/<creator_id>
  - Basic analytics      : GET   /analytics
  - In-memory rate limiting on every route (Flask-Limiter)
  The four-signal ensemble, weights, thresholds, and calibration logic from
  Milestone 4 are UNCHANGED. Storage remains the local JSON audit log.

Scoring convention:
  0.0 = strongly human-written
  0.5 = uncertain
  1.0 = strongly AI-generated
"""

import os
import re
import json
import uuid
import statistics
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from groq import Groq


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
AUDIT_LOG_PATH = "audit_log.json"

VALID_CLASSIFICATIONS = {"likely_ai", "uncertain", "likely_human"}

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
if client is None:
    print("[WARN] GROQ_API_KEY not found. Classification will default to 'uncertain'.")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Rate limiting  (NEW in Milestone 5)
# ---------------------------------------------------------------------------
# Simple in-memory limiter, keyed by client IP. "memory://" storage is fine
# for a single-process class project; a production deployment would point this
# at Redis so limits are shared across workers. No global default limit is set
# so each route opts in explicitly with its own @limiter.limit(...) decorator.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="memory://",
)
@app.errorhandler(429)
def rate_limit_handler(error):
    """Return JSON when a client exceeds a rate limit."""
    return (
        jsonify(
            {
                "error": "Rate limit exceeded.",
                "status": "error",
                "details": str(error.description),
            }
        ),
        429,
    )


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------
def _clamp(value, low=0.0, high=1.0):
    """Keep a number inside [low, high]."""
    return max(low, min(high, value))


def _safe_int(value):
    """Coerce a value to int, returning 0 for anything non-numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_bool(value):
    """Return True only for a real JSON boolean true."""
    return value is True


def _tokenize_words(text):
    """Lowercased word tokens."""
    return re.findall(r"[A-Za-z']+", text.lower())


def _split_sentences(text):
    """Split into non-empty sentences on . ! ? boundaries."""
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


# ---------------------------------------------------------------------------
# Audit log helpers
# ---------------------------------------------------------------------------
def ensure_audit_log_exists():
    """Create audit_log.json with an empty entries list if it does not exist."""
    if not os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump({"entries": []}, f, indent=2)


def read_audit_log():
    """Return the list of audit entries."""
    ensure_audit_log_exists()
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def append_audit_entry(entry):
    """Append a single audit entry and persist the log back to disk."""
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


# ===========================================================================
# Signal 1: Groq LLM Classification
# ===========================================================================
SYSTEM_PROMPT = (
    "You are a content provenance classifier for a creative-sharing platform. "
    "Given a piece of text, estimate whether it reads as AI-generated, "
    "human-written, or uncertain.\n\n"
    "Respond with ONLY a JSON object, no surrounding text and no markdown, using "
    "exactly these keys:\n"
    '  - "classification": one of "likely_ai", "uncertain", "likely_human"\n'
    '  - "score": a number from 0.0 to 1.0 representing AI likelihood, where '
    "0.0 = strongly human-written, 0.5 = uncertain, 1.0 = strongly AI-generated\n"
    '  - "reasoning": one or two short sentences explaining what you noticed.\n\n'
    "Calibration guidance:\n"
    "- Judge by substance and specificity, not surface tone. A casual, "
    "first-person, or conversational voice is NOT by itself evidence of human "
    "authorship because AI text is often lightly edited to sound casual.\n"
    "- Lean toward 'uncertain' around 0.5 when the content is generic, "
    "evenly balanced, hedge-laden, or based on vague appeals to unnamed studies, "
    "even if the tone sounds conversational.\n"
    "- When content is highly repetitive, generic, template-like, and lacks "
    "concrete details or a distinct authorial perspective, scores from 0.85 "
    "to 0.95 are appropriate. Do not assign high AI scores from one phrase "
    "alone; look for repeated structure and lack of specificity together.\n"
    "- Genuine human writing often shows concrete specific detail, a distinct "
    "voice, lived experience, or real domain expertise. Formal or technical "
    "writing with real specificity is NOT by itself a sign of AI.\n"
    "- Reserve low strongly-human scores for content with clear specific detail "
    "or expertise, not merely casual tone.\n\n"
    "Be cautious: when signals are weak or mixed, prefer 'uncertain'. "
    "Mislabeling genuine human work as AI is a serious harm."
)


def normalize_signal(data):
    """Coerce a raw model dict into the exact signal shape we trust."""
    classification = data.get("classification")
    if classification not in VALID_CLASSIFICATIONS:
        classification = "uncertain"

    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        score = 0.5
    score = _clamp(score)

    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning = "No reasoning provided."

    return {
        "classification": classification,
        "score": score,
        "reasoning": reasoning.strip(),
    }


def classify_with_groq(text):
    """Ask the Groq model to classify the text."""
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
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)
        return normalize_signal(parsed)
    except Exception as exc:
        print(f"[WARN] Groq classification failed: {exc}")
        return safe_default


# ===========================================================================
# Signal 2: Stylometric Heuristics
# ===========================================================================
def classify_with_stylometrics(text):
    words = _tokenize_words(text)
    sentences = _split_sentences(text)
    total_tokens = len(words)

    sentence_word_counts = [len(_tokenize_words(s)) for s in sentences]
    sentence_length_variance = (
        float(statistics.pvariance(sentence_word_counts))
        if sentence_word_counts
        else 0.0
    )

    type_token_ratio = (len(set(words)) / total_tokens) if total_tokens else 0.0

    punctuation_marks = len(re.findall(r"""[,.;:!?"'()\-]""", text))
    punctuation_density = (punctuation_marks / total_tokens) if total_tokens else 0.0

    metrics = {
        "sentence_length_variance": round(sentence_length_variance, 3),
        "type_token_ratio": round(type_token_ratio, 3),
        "punctuation_density": round(punctuation_density, 3),
    }

    if total_tokens < 20 or len(sentences) < 2:
        return {
            "score": 0.5,
            "metrics": metrics,
            "reasoning": "Text too short for reliable stylometric analysis; neutral score applied.",
        }

    if sentence_length_variance < 2:
        variance_subscore = 0.70
    elif sentence_length_variance < 8:
        variance_subscore = 0.56
    elif sentence_length_variance < 18:
        variance_subscore = 0.46
    else:
        variance_subscore = 0.34

    if type_token_ratio < 0.45:
        ttr_subscore = 0.68
    elif type_token_ratio < 0.65:
        ttr_subscore = 0.56
    elif type_token_ratio < 0.85:
        ttr_subscore = 0.48
    else:
        ttr_subscore = 0.42

    if punctuation_density < 0.05:
        punct_subscore = 0.58
    elif punctuation_density < 0.12:
        punct_subscore = 0.52
    elif punctuation_density < 0.25:
        punct_subscore = 0.46
    else:
        punct_subscore = 0.40

    stylometric_score = _clamp(
        (variance_subscore * 0.50)
        + (ttr_subscore * 0.30)
        + (punct_subscore * 0.20),
        0.25,
        0.75,
    )

    reasoning = (
        f"Sentence-length variance {metrics['sentence_length_variance']} "
        f"(very uniform sentence lengths lean more AI-like), lexical diversity "
        f"{metrics['type_token_ratio']} (low diversity can suggest repetition), "
        f"punctuation density {metrics['punctuation_density']} "
        f"(used as a weak stylistic signal)."
    )

    return {
        "score": round(stylometric_score, 3),
        "metrics": metrics,
        "reasoning": reasoning,
    }


# ===========================================================================
# Signal 3: Repetition and Template Pattern Signal
# ===========================================================================
STOPWORDS = {
    "about", "after", "again", "also", "because", "before", "being", "between",
    "could", "every", "from", "have", "into", "more", "most", "other", "same",
    "should", "some", "such", "than", "that", "their", "there", "these",
    "this", "those", "through", "under", "very", "when", "where", "which",
    "while", "with", "would",
}

FORMULAIC_PHRASES = [
    "it is important to note",
    "furthermore",
    "in conclusion",
    "this highlights",
    "there are several factors",
    "it is essential",
    "plays a crucial role",
    "transformative",
    "paradigm shift",
]


def detect_template_patterns(text):
    lowered = text.lower()
    words = _tokenize_words(lowered)
    sentences = _split_sentences(text)
    word_count = len(words) or 1

    matched_patterns = []
    repetition_count = 0

    for phrase in FORMULAIC_PHRASES:
        count = lowered.count(phrase)
        if count > 0:
            matched_patterns.append(phrase)
            repetition_count += count

    sentence_openings = []
    for sentence in sentences:
        sentence_words = _tokenize_words(sentence)
        if len(sentence_words) >= 4:
            opening = " ".join(sentence_words[:4])
            sentence_openings.append(opening)

    opening_counts = {}
    for opening in sentence_openings:
        opening_counts[opening] = opening_counts.get(opening, 0) + 1

    repeated_openings = {
        opening: count
        for opening, count in opening_counts.items()
        if count >= 2
    }

    repeated_opening_count = sum(count - 1 for count in repeated_openings.values())

    meaningful_word_counts = {}
    for word in words:
        if len(word) >= 6 and word not in STOPWORDS:
            meaningful_word_counts[word] = meaningful_word_counts.get(word, 0) + 1

    repeated_terms = {
        word: count
        for word, count in meaningful_word_counts.items()
        if count >= 4
    }

    repeated_term_count = sum(count - 3 for count in repeated_terms.values())

    hits_per_100w = repetition_count / (word_count / 100.0)
    openings_per_100w = repeated_opening_count / (word_count / 100.0)
    repeated_terms_per_100w = repeated_term_count / (word_count / 100.0)

    template_score = _clamp(
        0.5
        + (0.05 * hits_per_100w)
        + (0.08 * openings_per_100w)
        + (0.03 * repeated_terms_per_100w),
        0.0,
        1.0,
    )

    for opening, count in repeated_openings.items():
        matched_patterns.append(f"repeated opening: {opening} ({count}x)")

    for word, count in repeated_terms.items():
        matched_patterns.append(f"repeated term: {word} ({count}x)")

    if matched_patterns:
        reasoning = (
            f"Detected template-like repetition: {repetition_count} formulaic "
            f"phrase occurrence(s), {repeated_opening_count} repeated sentence "
            f"opening(s), and {repeated_term_count} repeated key-term signal(s)."
        )
    else:
        reasoning = "No strong formulaic, repeated-opening, or repeated key-term patterns detected; neutral template score applied."

    return {
        "score": round(template_score, 3),
        "matched_patterns": matched_patterns,
        "repetition_count": repetition_count + repeated_opening_count + repeated_term_count,
        "reasoning": reasoning,
    }


# ===========================================================================
# Signal 4: Provenance Metadata Signal
# ===========================================================================
def score_provenance_metadata(metadata):
    if not isinstance(metadata, dict) or not metadata:
        return {
            "score": 0.5,
            "verified_human": False,
            "certificate_id": None,
            "evidence_summary": "No provenance metadata provided; neutral score applied.",
        }

    score = 0.5
    evidence = []

    verified_human = _safe_bool(metadata.get("verified_human"))
    if verified_human:
        score -= 0.35
        evidence.append("verified human authorship")

    if _safe_bool(metadata.get("has_version_history")):
        score -= 0.10
        evidence.append("version history present")

    draft_count = _safe_int(metadata.get("draft_count"))
    if draft_count >= 2:
        score -= 0.08
        evidence.append(f"{draft_count} drafts")

    revision_count = _safe_int(metadata.get("revision_count"))
    if revision_count >= 2:
        score -= 0.08
        evidence.append(f"{revision_count} revisions")

    time_spent = _safe_int(metadata.get("time_spent_minutes"))
    if time_spent >= 30:
        score -= 0.08
        evidence.append(f"{time_spent} minutes spent authoring")

    # AI-use disclosure is provenance evidence too. This does not accuse the
    # creator based on style; it uses metadata the submitter provided.
    if _safe_bool(metadata.get("declared_ai_assistance")):
        score += 0.35
        evidence.append("declared AI assistance")

    if _safe_bool(metadata.get("ai_generated_draft")):
        score += 0.30
        evidence.append("AI-generated draft disclosed")

    ai_tool = metadata.get("ai_tool_used")
    if isinstance(ai_tool, str) and ai_tool.strip():
        score += 0.10
        evidence.append(f"AI tool disclosed: {ai_tool.strip()}")

    score = _clamp(score)

    if evidence:
        summary = "Provenance evidence: " + ", ".join(evidence) + "."
    else:
        summary = "Metadata provided but no strong authorship-process evidence found."

    return {
        "score": round(score, 3),
        "verified_human": verified_human,
        "certificate_id": None,
        "evidence_summary": summary,
    }


# ===========================================================================
# Ensemble scoring
# ===========================================================================
def calculate_combined_score(
    llm_score, stylometric_score, template_score, provenance_score
):
    """Weighted ensemble of the four signals."""
    combined = (
        (llm_score * 0.40)
        + (stylometric_score * 0.30)
        + (template_score * 0.20)
        + (provenance_score * 0.10)
    )
    return _clamp(combined)


def determine_attribution(combined_ai_score):
    """Map combined AI-likelihood score to attribution."""
    if combined_ai_score < 0.36:
        return "likely_human"
    elif combined_ai_score < 0.78:
        return "uncertain"
    else:
        return "likely_ai"


# ===========================================================================
# Transparency labels + certificate lookup  (NEW in Milestone 5)
# ===========================================================================
# Exact, human-readable label text shown to readers. Keyed by attribution.
TRANSPARENCY_LABELS = {
    "likely_human": (
        "This content shows strong signs of human authorship. Provenance "
        "Guard found low evidence of AI generation based on the available "
        "signals."
    ),
    "uncertain": (
        "Provenance Guard could not confidently determine whether this content "
        "was human-written or AI-generated. The available signals are mixed, "
        "so this result should be treated as uncertain."
    ),
    "likely_ai": (
        "This content shows strong signs of AI generation. Provenance Guard "
        "found high AI-likelihood signals, but this result is not a final "
        "judgment of authorship."
    ),
}

CERTIFICATE_ADDON = (
    "This creator has a verified human provenance certificate on record."
)


def generate_transparency_label(attribution, confidence, verified_human=False):
    """Build the reader-facing transparency label for a result.

    `confidence` is accepted for API completeness (and future wording that may
    reference it); the base text is chosen by attribution. When the creator has
    a verified human certificate, the certificate sentence is appended.
    """
    base = TRANSPARENCY_LABELS.get(attribution, TRANSPARENCY_LABELS["uncertain"])
    if verified_human:
        return base + " " + CERTIFICATE_ADDON
    return base


def find_certificate_for_creator(creator_id):
    """Return the most recent verified-human certificate for a creator, or None.

    Scans the audit log newest-first and returns the first matching
    'human_verified' event as a small certificate dict.
    """
    for entry in reversed(read_audit_log()):
        if (
            entry.get("event_type") == "human_verified"
            and entry.get("creator_id") == creator_id
            and entry.get("verified_human") is True
        ):
            return {
                "creator_id": creator_id,
                "certificate_id": entry.get("certificate_id"),
                "verified_human": True,
                "verification_method": entry.get("verification_method"),
                # The audit event stores the issue time under "timestamp".
                "issued_at": entry.get("timestamp"),
            }
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute")
def submit():
    """Validate a submission, run all four signals, score, log, and respond."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("Request body must be a valid JSON object.", 400)

    creator_id = body.get("creator_id")
    content_type = body.get("content_type")
    text = body.get("text")
    metadata = body.get("metadata")

    if not isinstance(creator_id, str) or not creator_id.strip():
        return error_response(
            "creator_id is required and must be a non-empty string.", 400
        )

    if not isinstance(content_type, str) or not content_type.strip():
        return error_response("content_type is required.", 400)

    if content_type != "text":
        return error_response(
            f"Unsupported content_type '{content_type}'. Only 'text' is supported.",
            400,
        )

    if not isinstance(text, str) or not text.strip():
        return error_response(
            "text is required and must be a non-empty string for content_type 'text'.",
            400,
        )

    signal1 = classify_with_groq(text)
    signal2 = classify_with_stylometrics(text)
    signal3 = detect_template_patterns(text)
    signal4 = score_provenance_metadata(metadata)

    combined_ai_score = calculate_combined_score(
        signal1["score"], signal2["score"], signal3["score"], signal4["score"]
    )
    confidence = round(combined_ai_score, 3)
    attribution = determine_attribution(confidence)

    safety_adjusted = False
    safety_reason = None

    signal_values = [
        signal1["score"],
        signal2["score"],
        signal3["score"],
        signal4["score"],
    ]
    signal_spread = max(signal_values) - min(signal_values)

    if attribution == "likely_ai" and signal4["verified_human"]:
        attribution = "uncertain"
        safety_adjusted = True
        safety_reason = (
            "Verified human provenance was present, so the system reduced "
            "the result from likely_ai to uncertain."
        )
    elif attribution == "likely_ai" and signal_spread > 0.5:
        attribution = "uncertain"
        safety_adjusted = True
        safety_reason = (
            "The detection signals disagreed strongly, so the system reduced "
            "the result from likely_ai to uncertain."
        )

    content_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # --- Certificate-aware transparency label (Milestone 5) ---
    # A verified human certificate is about the CREATOR, separate from the
    # per-request provenance metadata signal. It only affects the label add-on
    # here; it does not alter the ensemble score or attribution.
    certificate = find_certificate_for_creator(creator_id)
    label = generate_transparency_label(
        attribution, confidence, verified_human=bool(certificate)
    )

    response_body = {
        "content_id": content_id,
        "creator_id": creator_id,
        "content_type": content_type,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "certificate": certificate,  # full cert dict if on record, else None
        "signals": {
            "llm_score": signal1["score"],
            "llm_reasoning": signal1["reasoning"],
            "stylometric_score": signal2["score"],
            "stylometric_metrics": signal2["metrics"],
            "stylometric_reasoning": signal2["reasoning"],
            "template_score": signal3["score"],
            "matched_patterns": signal3["matched_patterns"],
            "repetition_count": signal3["repetition_count"],
            "template_reasoning": signal3["reasoning"],
            "provenance_score": signal4["score"],
            "provenance_summary": signal4["evidence_summary"],
        },
        "safety": {
            "signal_spread": round(signal_spread, 3),
            "safety_adjusted": safety_adjusted,
            "safety_reason": safety_reason,
        },
        "status": "classified",
    }

    append_audit_entry(
        {
            "event_type": "submission_classified",
            "timestamp": timestamp,
            "content_id": content_id,
            "creator_id": creator_id,
            "content_type": content_type,
            "attribution": attribution,
            "confidence": confidence,
            "label": label,
            "creator_certificate_verified": bool(certificate),
            "certificate_id": certificate.get("certificate_id") if certificate else None,
            "llm_score": signal1["score"],
            "llm_reasoning": signal1["reasoning"],
            "stylometric_score": signal2["score"],
            "stylometric_metrics": signal2["metrics"],
            "stylometric_reasoning": signal2["reasoning"],
            "template_score": signal3["score"],
            "matched_patterns": signal3["matched_patterns"],
            "repetition_count": signal3["repetition_count"],
            "template_reasoning": signal3["reasoning"],
            "provenance_score": signal4["score"],
            "provenance_summary": signal4["evidence_summary"],
            "verified_human": signal4["verified_human"],
            "signal_spread": round(signal_spread, 3),
            "safety_adjusted": safety_adjusted,
            "safety_reason": safety_reason,
            "status": "classified",
        }
    )

    return jsonify(response_body), 200


@app.route("/log", methods=["GET"])
@limiter.limit("30 per minute")
def get_log():
    """Return all audit entries recorded so far."""
    return jsonify({"entries": read_audit_log()}), 200


# ===========================================================================
# Appeals  (NEW in Milestone 5)
# ===========================================================================
VALID_DECISIONS = {"approved", "rejected", "needs_more_info"}

# Maps a reviewer decision to (appeal_status, content_status).
DECISION_MAP = {
    "approved": ("approved", "human_review_overturned"),
    "rejected": ("rejected", "classified"),
    "needs_more_info": ("needs_more_info", "under_review"),
}


@app.route("/appeal", methods=["POST"])
@limiter.limit("5 per minute")
def submit_appeal():
    """Let a creator contest a classification. Records it for human review."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("Request body must be a valid JSON object.", 400)

    content_id = body.get("content_id")
    creator_id = body.get("creator_id")
    creator_reasoning = body.get("creator_reasoning")
    evidence = body.get("evidence")

    # --- Validation ---
    if not isinstance(content_id, str) or not content_id.strip():
        return error_response(
            "content_id is required and must be a non-empty string.", 400
        )
    if not isinstance(creator_id, str) or not creator_id.strip():
        return error_response(
            "creator_id is required and must be a non-empty string.", 400
        )
    if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return error_response(
            "creator_reasoning is required and must be a non-empty string.", 400
        )

    # evidence is optional, but if present it must be an object, and any
    # external_links inside it must be a list of strings.
    if evidence is not None:
        if not isinstance(evidence, dict):
            return error_response("evidence must be a JSON object if provided.", 400)
        external_links = evidence.get("external_links")
        if external_links is not None:
            if not isinstance(external_links, list) or not all(
                isinstance(link, str) for link in external_links
            ):
                return error_response(
                    "evidence.external_links must be a list of strings if provided.",
                    400,
                )

    timestamp = datetime.now(timezone.utc).isoformat()
    appeal_status = "under_review"

    append_audit_entry(
    {
            "event_type": "appeal_submitted",
            "timestamp": timestamp,
            "content_id": content_id,
            "creator_id": creator_id,
            "status": "under_review",
            "appeal_status": appeal_status,
            "content_status": "under_review",
            "creator_reasoning": creator_reasoning,
            "appeal_reasoning": creator_reasoning,
            "evidence": evidence if isinstance(evidence, dict) else {},
        }
    )

    return (
        jsonify(
            {
                "content_id": content_id,
                "status": appeal_status,
                "message": (
                    "Appeal received with creator reasoning and evidence. "
                    "The content has been marked for human review."
                ),
            }
        ),
        200,
    )


@app.route("/appeal/<content_id>", methods=["PATCH"])
@limiter.limit("10 per minute")
def review_appeal(content_id):
    """Record a reviewer's decision on an appeal."""
    if not isinstance(content_id, str) or not content_id.strip():
        return error_response("content_id in the URL must be non-empty.", 400)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("Request body must be a valid JSON object.", 400)

    reviewer_id = body.get("reviewer_id")
    decision = body.get("decision")
    reviewer_notes = body.get("reviewer_notes")

    # --- Validation ---
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        return error_response(
            "reviewer_id is required and must be a non-empty string.", 400
        )
    if decision not in VALID_DECISIONS:
        return error_response(
            "decision is required and must be one of: "
            "approved, rejected, needs_more_info.",
            400,
        )
    if reviewer_notes is not None and not isinstance(reviewer_notes, str):
        return error_response("reviewer_notes must be a string if provided.", 400)

    appeal_status, content_status = DECISION_MAP[decision]
    timestamp = datetime.now(timezone.utc).isoformat()

    append_audit_entry(
        {
            "event_type": "appeal_reviewed",
            "timestamp": timestamp,
            "content_id": content_id,
            "reviewer_id": reviewer_id,
            "decision": decision,
            "appeal_status": appeal_status,
            "content_status": content_status,
            "reviewer_notes": reviewer_notes,
        }
    )

    return (
        jsonify(
            {
                "content_id": content_id,
                "appeal_status": appeal_status,
                "content_status": content_status,
                "reviewer_notes": reviewer_notes,
            }
        ),
        200,
    )


# ===========================================================================
# Verified human provenance certificates  (NEW in Milestone 5)
# ===========================================================================
VALID_VERIFICATION_METHODS = {
    "manual_review",
    "institutional_email",
    "portfolio_review",
}


@app.route("/verify-human", methods=["POST"])
@limiter.limit("20 per minute")
def verify_human():
    """Issue a verified-human provenance certificate for a creator."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("Request body must be a valid JSON object.", 400)

    creator_id = body.get("creator_id")
    verification_method = body.get("verification_method")
    reviewer_id = body.get("reviewer_id")
    notes = body.get("notes")

    # --- Validation ---
    if not isinstance(creator_id, str) or not creator_id.strip():
        return error_response(
            "creator_id is required and must be a non-empty string.", 400
        )
    if verification_method not in VALID_VERIFICATION_METHODS:
        return error_response(
            "verification_method is required and must be one of: "
            "manual_review, institutional_email, portfolio_review.",
            400,
        )
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        return error_response(
            "reviewer_id is required and must be a non-empty string.", 400
        )
    if notes is not None and not isinstance(notes, str):
        return error_response("notes must be a string if provided.", 400)

    certificate_id = str(uuid.uuid4())
    issued_at = datetime.now(timezone.utc).isoformat()

    append_audit_entry(
        {
            "event_type": "human_verified",
            "timestamp": issued_at,
            "creator_id": creator_id,
            "certificate_id": certificate_id,
            "verified_human": True,
            "verification_method": verification_method,
            "reviewer_id": reviewer_id,
            "notes": notes,
        }
    )

    return (
        jsonify(
            {
                "creator_id": creator_id,
                "certificate_id": certificate_id,
                "verified_human": True,
                "verification_method": verification_method,
                "issued_at": issued_at,
            }
        ),
        200,
    )


@app.route("/certificate/<creator_id>", methods=["GET"])
@limiter.limit("20 per minute")
def get_certificate(creator_id):
    """Look up the most recent verified-human certificate for a creator."""
    certificate = find_certificate_for_creator(creator_id)
    if certificate is not None:
        return jsonify(certificate), 200

    return (
        jsonify(
            {
                "creator_id": creator_id,
                "verified_human": False,
                "message": (
                    "No verified human provenance certificate found for "
                    "this creator."
                ),
            }
        ),
        200,
    )


# ===========================================================================
# Analytics  (NEW in Milestone 5)
# ===========================================================================
@app.route("/analytics", methods=["GET"])
@limiter.limit("30 per minute")
def analytics():
    """Aggregate simple, read-only statistics from the audit log."""
    entries = read_audit_log()

    attribution_counts = {"likely_human": 0, "uncertain": 0, "likely_ai": 0}
    appeal_status_counts = {
        "under_review": 0,
        "approved": 0,
        "rejected": 0,
        "needs_more_info": 0,
    }
    confidence_total = 0.0
    total_submissions = 0
    appeal_count = 0
    verified_creators = set()

    # Track the LATEST appeal status per content_id so a reviewed appeal moves
    # out of "under_review" into its decision bucket instead of being counted
    # in both. appeal_count still counts how many appeals were submitted.
    latest_appeal_status = {}

    # Running sums for the four signal scores, so we can average them.
    signal_totals = {"llm": 0.0, "stylometric": 0.0, "template": 0.0, "provenance": 0.0}

    for entry in entries:
        event_type = entry.get("event_type")

        if event_type == "submission_classified":
            total_submissions += 1

            attribution = entry.get("attribution")
            if attribution in attribution_counts:
                attribution_counts[attribution] += 1

            confidence_total += float(entry.get("confidence", 0.0) or 0.0)

            signal_totals["llm"] += float(entry.get("llm_score", 0.0) or 0.0)
            signal_totals["stylometric"] += float(
                entry.get("stylometric_score", 0.0) or 0.0
            )
            signal_totals["template"] += float(entry.get("template_score", 0.0) or 0.0)
            signal_totals["provenance"] += float(
                entry.get("provenance_score", 0.0) or 0.0
            )

        elif event_type == "appeal_submitted":
            appeal_count += 1
            cid = entry.get("content_id")
            if cid is not None:
                latest_appeal_status[cid] = entry.get("appeal_status", "under_review")

        elif event_type == "appeal_reviewed":
            cid = entry.get("content_id")
            if cid is not None:
                latest_appeal_status[cid] = entry.get("appeal_status")

        elif event_type == "human_verified":
            if entry.get("verified_human") is True:
                verified_creators.add(entry.get("creator_id"))

    # Tally the latest status of each appealed item into the four buckets.
    for status in latest_appeal_status.values():
        if status in appeal_status_counts:
            appeal_status_counts[status] += 1

    # Averages (guard against division by zero on an empty log).
    if total_submissions > 0:
        average_confidence = round(confidence_total / total_submissions, 3)
        average_signal_scores = {
            key: round(value / total_submissions, 3)
            for key, value in signal_totals.items()
        }
    else:
        average_confidence = 0.0
        average_signal_scores = {"llm": 0.0, "stylometric": 0.0, "template": 0.0, "provenance": 0.0}

    return (
        jsonify(
            {
                "total_submissions": total_submissions,
                "attribution_counts": attribution_counts,
                "average_confidence": average_confidence,
                "appeal_count": appeal_count,
                "appeal_status_counts": appeal_status_counts,
                "verified_creator_count": len(verified_creators),
                "average_signal_scores": average_signal_scores,
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ensure_audit_log_exists()
    app.run(host="0.0.0.0", port=5000, debug=True)