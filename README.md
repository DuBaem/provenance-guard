# Provenance Guard

Provenance Guard is a Flask backend system for creative sharing platforms. It classifies submitted content as `likely_human`, `uncertain`, or `likely_ai`, returns a confidence score, surfaces a reader-facing transparency label, records an audit trail, and supports creator appeals when a creator believes their work has been misclassified.

The project is designed around a key safety principle: AI detection should not be treated as absolute proof of authorship. False positives can harm real creators, so Provenance Guard uses uncertainty labels, multiple detection signals, provenance evidence, audit logs, and appeals instead of making unsupported binary claims.

## Project Purpose

Creative platforms increasingly need ways to communicate whether content may have been generated or assisted by AI. At the same time, AI detection is imperfect. Human-written work can look polished, repetitive, formal, or generic, and AI-assisted work can be edited to sound more human.

Provenance Guard addresses this by acting as a backend trust layer. A platform can send submitted content to the API, receive a classification result, display a careful transparency label to readers, and preserve a review trail for creators who want to appeal.

The system focuses on:

- Classification
- Confidence scoring
- Reader-facing transparency labels
- Creator appeals
- Rate limiting
- Audit logging
- Provenance certificates
- Analytics
- Multi-modal structured metadata support

## Features

- `POST /submit` endpoint for text and metadata submissions
- Four-signal ensemble detection
- Groq LLM classification using `llama-3.3-70b-versatile`
- Stylometric heuristic scoring
- Repetition and template pattern scoring
- Provenance metadata scoring
- Confidence score from `0.0` to `1.0`
- Three attribution results: `likely_human`, `uncertain`, and `likely_ai`
- Three reader-facing transparency labels
- Verified human provenance certificates
- Creator appeal submission
- Human review endpoint for appeals
- Structured JSON audit log
- Rate limiting with Flask-Limiter
- JSON analytics endpoint
- Visual HTML dashboard
- Multi-modal support through structured metadata submissions

## Tech Stack

- Python
- Flask
- Flask-Limiter
- Groq API
- `llama-3.3-70b-versatile`
- python-dotenv
- Local structured JSON audit log

## Walkthrough Video

Walkthrough video link:

    https://drive.google.com/file/d/16OuR3E87rVczreB4EiLC6sacQAk3ht7L/view?usp=sharing

The walkthrough video is a short portfolio tour of Provenance Guard. It shows the project working end-to-end, includes live tests, and explains the main design decisions behind the backend.

The video includes:

- Starting the Flask backend locally with `python app.py`
- Opening the visual analytics dashboard at `GET /dashboard`
- Reviewing dashboard metrics such as total submissions, attribution counts, appeal counts, verified creators, and average signal scores
- Clicking a dashboard submission row to open `GET /dashboard/submission/<content_id>`
- Reviewing the detailed classification evidence for one submission
- Explaining the four-signal ensemble detection system:
  - Groq LLM classification
  - Stylometric heuristics
  - Repetition and template pattern detection
  - Provenance metadata scoring
- Running a live `POST /submit` test with `content_type: "metadata"`
- Showing the metadata response, including:
  - `content_id`
  - `attribution`
  - `confidence`
  - `label`
  - `metadata_summary`
  - `signals`
  - `safety`
- Calling `GET /analytics` to confirm that audit-log metrics are returned as JSON
- Refreshing the dashboard to show that new submissions are reflected in the visual dashboard
- Testing an invalid detail page and confirming that it returns a readable `404 NOT FOUND`
- Briefly explaining the appeals workflow with `POST /appeal` and `PATCH /appeal/<content_id>`
- Briefly explaining verified human provenance certificates with `POST /verify-human` and `GET /certificate/<creator_id>`
- Mentioning rate limiting with Flask-Limiter and structured audit logging through `audit_log.json`

The walkthrough also points out the completed stretch features:

1. Ensemble detection with four weighted signals
2. Verified human provenance certificates
3. Visual analytics dashboard with clickable submission detail pages
4. Multi-modal structured metadata support


## Setup Instructions

Clone the repository, create a virtual environment, install dependencies, and add a `.env` file with a Groq API key.

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

The project dependencies are:

    flask>=3.0.0
    flask-limiter>=3.5.0
    groq==0.15.0
    python-dotenv==1.0.1

## Environment Variables

Create a `.env` file in the root of the project:

    GROQ_API_KEY=your_groq_api_key_here

The `.env` file should not be committed to GitHub.

## How to Run the App

Start the Flask app:

    python app.py

The app runs at:

    http://localhost:5000

The dashboard can be opened at:

    http://localhost:5000/dashboard

## API Endpoints

### POST /submit

Classifies submitted content.

Supported content types:

    text
    metadata

Example text request:

    curl -X POST http://localhost:5000/submit -H "Content-Type: application/json" -d "{\"creator_id\":\"creator-1\",\"content_type\":\"text\",\"text\":\"I wrote this short reflection after revising my draft several times.\",\"metadata\":{\"has_version_history\":true,\"draft_count\":3,\"revision_count\":2,\"time_spent_minutes\":45}}"

Example metadata request:

    curl -X POST http://localhost:5000/submit -H "Content-Type: application/json" -d "{\"creator_id\":\"metadata-test-user\",\"content_type\":\"metadata\",\"metadata\":{\"title\":\"Short Film Poster Caption\",\"description\":\"A caption describing the poster and how it was made.\",\"declared_ai_assistance\":true,\"ai_generated_draft\":true,\"ai_tool_used\":\"AI writing assistant\",\"verified_human\":false,\"has_version_history\":true,\"draft_count\":2,\"revision_count\":3,\"time_spent_minutes\":40}}"

Example metadata response excerpt:

    {
      "attribution": "uncertain",
      "confidence": 0.702,
      "content_type": "metadata",
      "creator_id": "metadata-test-user",
      "metadata_summary": "Title: Short Film Poster Caption. Description: A caption describing the poster and how it was made. The creator declared AI assistance. An AI-generated draft was disclosed. AI tool used: AI writing assistant. The creator is not marked as verified human. Version history is available. Draft count: 2. Revision count: 3. Time spent: 40 minutes.",
      "status": "classified"
    }

### POST /appeal

Allows a creator to appeal a classification.

    curl -X POST http://localhost:5000/appeal -H "Content-Type: application/json" -d "{\"content_id\":\"content-123\",\"creator_id\":\"creator-123\",\"creator_reasoning\":\"I wrote this myself and can explain the revision process.\",\"evidence\":{\"draft_notes\":\"The first draft was written before the final version.\",\"revision_summary\":\"I revised the second paragraph and changed the title.\"}}"

Expected response behavior:

    {
      "content_id": "content-123",
      "status": "under_review",
      "message": "Appeal received with creator reasoning and evidence. The content has been marked for human review."
    }

### PATCH /appeal/<content_id>

Allows a reviewer to resolve an appeal.

Supported decisions:

    approved
    rejected
    needs_more_info

Example request:

    curl -X PATCH http://localhost:5000/appeal/content-123 -H "Content-Type: application/json" -d "{\"reviewer_id\":\"reviewer-1\",\"decision\":\"approved\",\"reviewer_notes\":\"The creator provided enough evidence to overturn the original classification.\"}"

### GET /log

Returns the structured audit log.

    curl http://localhost:5000/log

### POST /verify-human

Issues a verified human provenance certificate for a creator.

Supported verification methods:

    manual_review
    institutional_email
    portfolio_review

Example request:

    curl -X POST http://localhost:5000/verify-human -H "Content-Type: application/json" -d "{\"creator_id\":\"label-test-user\",\"verification_method\":\"manual_review\",\"reviewer_id\":\"reviewer-1\"}"

Example certificate created during testing:

    certificate_id: 87cb0a01-c261-48c2-83cc-995c1488cf16
    verified_human: true

### GET /certificate/<creator_id>

Looks up the most recent verified human certificate for a creator.

    curl http://localhost:5000/certificate/label-test-user

### GET /analytics

Returns aggregate analytics from the audit log.

    curl http://localhost:5000/analytics

Example output after testing:

    {
      "appeal_count": 3,
      "appeal_status_counts": {
        "approved": 1,
        "needs_more_info": 0,
        "rejected": 1,
        "under_review": 1
      },
      "attribution_counts": {
        "likely_ai": 1,
        "likely_human": 8,
        "uncertain": 23
      },
      "average_confidence": 0.492,
      "average_signal_scores": {
        "llm": 0.497,
        "provenance": 0.513,
        "stylometric": 0.45,
        "template": 0.549
      },
      "total_submissions": 32,
      "verified_creator_count": 1
    }

### GET /dashboard

Displays a visual analytics dashboard in the browser.

    start http://localhost:5000/dashboard

The dashboard shows:

- Total submissions
- Average confidence
- Appeals submitted
- Verified creators
- Attribution counts
- Appeal status counts
- Average signal scores
- Recent audit events

Dashboard route test:

    HTTP/1.1 200 OK
    Content-Type: text/html; charset=utf-8
    Content-Length: 7017

### GET /dashboard/submission/<content_id>

Displays a detailed browser view for one classified submission.

Example URL:

    http://localhost:5000/dashboard/submission/b1b27806-b1ef-4f85-849f-fd7cc31afa80

The detail page shows:

- content ID
- creator ID
- content type
- timestamp
- attribution result
- confidence score
- transparency label
- metadata summary, if present
- certificate information, if present
- safety adjustment information
- individual signal scores
- LLM reasoning
- stylometric reasoning and metrics
- template pattern evidence
- provenance summary
- related appeal submissions
- related appeal review decisions
- link back to the dashboard

Invalid content IDs return a readable browser page with a `404 NOT FOUND` status instead of crashing.

Test evidence:

    /dashboard/submission/not-a-real-id -> 404 NOT FOUND

The dashboard now links submission rows to this detail page when a row has a `content_id`.

## Architecture

The system is organized around a request pipeline, a detection pipeline, an audit trail, and review workflows. The same audit log powers `/log`, `/analytics`, and `/dashboard`.

### Architecture Narrative

When a creator submits content to Provenance Guard, the request first passes through the rate limiter to prevent abuse. The API validates the required fields, creates a unique `content_id`, and routes the request based on `content_type`.

Text submissions go through the normal text analysis pipeline. Metadata submissions are converted into a readable metadata summary and then analyzed through the same ensemble pipeline. The original metadata object is also passed into the provenance metadata signal.

The detection pipeline runs four signals: Groq LLM classification, stylometric heuristics, repetition/template pattern detection, and provenance metadata scoring. Each signal returns an AI-likelihood score from `0.0` to `1.0`. The ensemble scorer combines those normalized scores into one `combined_ai_score`, maps the score to an attribution result, and sends that result to the transparency label generator.

The system writes a structured event to `audit_log.json` after submissions, appeals, review decisions, and certificate events. This gives the project a historical record of what happened, not just the latest response.

### Submission Flow

    Creator / Platform
        |
        | POST /submit
        | creator_id, content_type, text or metadata
        v
    Rate Limiter
        |
        | allow request or return 429
        v
    Provenance Guard API
        |
        | validate required fields
        | reject missing creator_id
        | reject empty content
        | reject unsupported content_type
        v
    Content ID Generator
        |
        | create unique content_id
        v
    Content Router
        |
        | content_type = text -> text analysis pipeline
        | content_type = metadata -> metadata analysis pipeline
        | unsupported content_type -> structured 400 error
        v
    Certificate Check
        |
        | check creator verified_human status
        | retrieve certificate_id if available
        v
    Detection Pipeline
        |
        | run ensemble signals
        v
    Signal 1: Groq LLM Classification
        |
        | raw LLM assessment and llm_score
        v
    Signal 2: Stylometric Heuristics
        |
        | sentence variance, vocabulary diversity, punctuation metrics
        v
    Signal 3: Repetition / Template Pattern Signal
        |
        | repeated phrase and template pattern score
        v
    Signal 4: Provenance Metadata Signal
        |
        | certificate and evidence-aware provenance score
        v
    Signal Normalizer
        |
        | convert all signal outputs to 0.0 to 1.0 AI-likelihood scores
        v
    Ensemble Confidence Scorer
        |
        | apply documented weights
        | produce combined confidence score
        | produce attribution: likely_ai, uncertain, or likely_human
        v
    Transparency Label Generator
        |
        | map attribution and confidence to reader-facing label text
        | include verified human certificate display if available
        v
    Audit Logger
        |
        | event_type: submission_classified
        | timestamp
        | content_id
        | creator_id
        | content_type
        | individual signal scores
        | combined confidence score
        | attribution result
        | label text
        | certificate status
        | review status
        v
    JSON Response
        |
        | content_id
        | attribution
        | confidence
        | label
        | signal summary
        | certificate information
        | status
        v
    Creator / Platform

### Appeal Flow

    Creator / Platform
        |
        | POST /appeal
        | content_id, creator_id, creator_reasoning, evidence
        v
    Provenance Guard API
        |
        | validate content_id
        | validate creator_id
        | validate creator_reasoning
        | validate structured evidence format if provided
        v
    Appeal Handler
        |
        | update content status to under_review
        | attach creator reasoning
        | attach structured evidence
        v
    Audit Logger
        |
        | event_type: appeal_submitted
        | timestamp
        | content_id
        | creator_id
        | creator_reasoning
        | appeal_reasoning
        | evidence
        | status: under_review
        | appeal_status: under_review
        | content_status: under_review
        v
    JSON Response
        |
        | appeal received
        | status: under_review
        v
    Creator / Platform

### Appeal Review Flow

    Reviewer
        |
        | PATCH /appeal/<content_id>
        | reviewer_id, decision, reviewer_notes
        v
    Provenance Guard API
        |
        | validate content_id
        | validate decision is approved, rejected, or needs_more_info
        | validate reviewer_notes if provided
        v
    Appeal Review Handler
        |
        | approved -> appeal_status: approved, content_status: human_review_overturned
        | rejected -> appeal_status: rejected, content_status: classified
        | needs_more_info -> appeal_status: needs_more_info, content_status: under_review
        v
    Audit Logger
        |
        | event_type: appeal_reviewed
        | timestamp
        | content_id
        | reviewer_id
        | reviewer decision
        | reviewer notes
        | final appeal_status
        | final content_status
        v
    JSON Response
        |
        | appeal review result
        v
    Reviewer

### Certificate Flow

    Creator / Reviewer
        |
        | POST /verify-human
        | creator_id, verification_method, reviewer_id, notes
        v
    Provenance Guard API
        |
        | validate creator_id
        | validate verification_method
        | validate reviewer_id
        v
    Certificate Handler
        |
        | issue certificate_id
        | set verified_human: true
        v
    Audit Logger
        |
        | event_type: human_verified
        | timestamp
        | creator_id
        | certificate_id
        | verification_method
        | reviewer_id
        | verified_human: true
        v
    JSON Response
        |
        | creator_id
        | certificate_id
        | verified_human
        | verification_method
        | issued_at
        v
    Creator / Reviewer

### Certificate Lookup Flow

    Creator / Platform
        |
        | GET /certificate/<creator_id>
        v
    Certificate Handler
        |
        | scan audit log for most recent human_verified event
        | retrieve certificate status if available
        v
    JSON Response
        |
        | certificate found -> certificate details
        | no certificate -> verified_human: false message
        v
    Creator / Platform

### Analytics Flow

    Dashboard / Reviewer
        |
        | GET /analytics
        v
    Analytics Handler
        |
        | read historical audit log events
        | calculate total submissions
        | calculate likely_ai, uncertain, and likely_human counts
        | calculate appeal count
        | calculate appeal status counts
        | calculate average confidence
        | calculate average signal scores
        | calculate verified creator count
        v
    Analytics JSON Response

### Visual Dashboard Flow

    Dashboard / Reviewer
        |
        | GET /dashboard
        v
    Dashboard Route
        |
        | reuse calculate_analytics_summary()
        | read recent audit events
        | render HTML with inline CSS
        v
    Browser Dashboard
        |
        | summary cards
        | attribution counts
        | appeal status counts
        | average signal scores
        | recent audit events table

## Detection Signals

Provenance Guard uses four signals. Each signal returns an AI-likelihood score from `0.0` to `1.0`.

- `0.0` means strongly human-written.
- `0.5` means uncertain.
- `1.0` means strongly AI-generated.

### Signal 1: Groq LLM Classification

This signal sends the submitted text or metadata summary to Groq's `llama-3.3-70b-versatile` model. The model returns:

- classification
- AI-likelihood score
- reasoning

This signal can evaluate broad writing patterns, but it is not treated as final proof.

### Signal 2: Stylometric Heuristics

This signal uses pure Python heuristics to measure writing structure.

It checks:

- sentence length variance
- type-token ratio
- punctuation density

This helps identify overly uniform or repetitive writing, but it can be unreliable for short content or formal human writing.

### Signal 3: Repetition and Template Pattern Detection

This signal checks for:

- formulaic phrases
- repeated sentence openings
- repeated meaningful terms

It is useful for detecting generic or template-like writing, but repeated language can also be intentional in poetry, speeches, and creative writing.

### Signal 4: Provenance Metadata Scoring

This signal checks structured metadata such as:

- verified human status
- version history
- draft count
- revision count
- time spent authoring
- declared AI assistance
- disclosed AI-generated draft
- AI tool used

This signal is important because Provenance Guard is not only trying to detect AI-like text. It is also trying to preserve creator context and reduce false-positive harm.

## Confidence Scoring

### Ensemble Formula

The system combines the four signals using this weighted formula:

    combined_ai_score =
      (llm_score * 0.40) +
      (stylometric_score * 0.30) +
      (template_score * 0.20) +
      (provenance_score * 0.10)

The LLM has the largest weight, but it cannot decide the result alone. The other signals provide structural and provenance context.

### Thresholds

| Combined AI Score | Attribution |
|---:|---|
| `0.00` to `0.35` | `likely_human` |
| `0.36` to `0.77` | `uncertain` |
| `0.78` to `1.00` | `likely_ai` |

The uncertain range is intentionally wide because false positives can harm real creators.

### Example 1: Lower-Confidence Case

A human-like submission with version history and revision metadata returned:

    attribution: likely_human
    confidence: 0.333

This shows that the system can return a lower AI-likelihood score when content and metadata provide stronger human authorship evidence.

### Example 2: Higher-Confidence Case

A metadata-supported AI-assisted submission returned:

    attribution: uncertain
    confidence: 0.702
    llm_score: 0.9
    provenance_score: 0.91
    template_score: 0.5
    stylometric_score: 0.504

A separate strong AI-disclosed test returned:

    attribution: likely_ai
    confidence: 0.815
    llm_score: 0.9
    template_score: 1.0
    provenance_score: 1.0

These tests show that the system can separate lower-risk, uncertain, and high AI-likelihood cases.

## Transparency Labels

Every `/submit` response includes a `label` field.

### High-Confidence Human Label

    This content shows strong signs of human authorship. Provenance Guard found low evidence of AI generation based on the available signals.

### Uncertain Label

    Provenance Guard could not confidently determine whether this content was human-written or AI-generated. The available signals are mixed, so this result should be treated as uncertain.

### High-Confidence AI Label

    This content shows strong signs of AI generation. Provenance Guard found high AI-likelihood signals, but this result is not a final judgment of authorship.

### Verified Human Certificate Add-On

If a creator has a verified human provenance certificate, this sentence is appended to the label:

    This creator has a verified human provenance certificate on record.

The certificate add-on gives additional context, but it does not automatically erase the classification result.

## Appeals Workflow

The appeals workflow gives creators a path to contest results.

Flow:

    Creator submits content
        |
    System classifies content
        |
    Creator submits appeal through POST /appeal
        |
    Content is marked under_review
        |
    Reviewer resolves appeal through PATCH /appeal/<content_id>
        |
    Audit log preserves both the appeal and review decision

Tested appeal outcomes:

    approved -> appeal_status: approved, content_status: human_review_overturned
    rejected -> appeal_status: rejected, content_status: classified
    needs_more_info -> appeal_status: needs_more_info, content_status: under_review

Example appeal log fields:

    {
      "event_type": "appeal_submitted",
      "status": "under_review",
      "appeal_status": "under_review",
      "content_status": "under_review",
      "creator_reasoning": "I wrote this myself based on personal experience.",
      "appeal_reasoning": "I wrote this myself based on personal experience.",
      "evidence": {
        "draft_notes": "The first draft was written before the final version.",
        "revision_summary": "The piece was revised several times."
      }
    }

## Audit Log Evidence

The audit log is stored in:

    audit_log.json

It is ignored by Git because it is runtime data.

The audit log records:

- classified submissions
- appeal submissions
- appeal review decisions
- verified human certificate events
- metadata summaries
- signal scores
- confidence scores
- transparency labels
- safety adjustments

Metadata audit evidence:

    "metadata_summary": "Title: Short Film Poster Caption. Description: A caption describing the poster and how it was made. The creator declared AI assistance. An AI-generated draft was disclosed. AI tool used: AI writing assistant. The creator is not marked as verified human. Version history is available. Draft count: 2. Revision count: 3. Time spent: 40 minutes."

## Rate Limiting Evidence

The app uses Flask-Limiter.

The `/submit` endpoint is limited with:

    @limiter.limit("10 per minute; 100 per day")

During testing, repeated `/submit` requests produced:

    10 requests returned 200 OK
    2 later requests returned 429 TOO MANY REQUESTS

The app also includes a JSON error handler for rate-limit failures:

    {
      "error": "Rate limit exceeded.",
      "status": "error",
      "details": "..."
    }

## Analytics Dashboard Evidence

The visual dashboard was tested at:

    http://localhost:5000/dashboard

The route returned:

    HTTP/1.1 200 OK
    Content-Type: text/html; charset=utf-8
    Content-Length: 7017

The dashboard displayed:

    Total submissions: 31
    Average confidence: 0.485
    Appeals submitted: 3
    Verified creators: 1

After testing metadata support, `/analytics` updated to:

    Total submissions: 32
    Average confidence: 0.492
    Appeals submitted: 3
    Verified creators: 1

This confirms that the dashboard and analytics endpoint read from the same audit log.

The dashboard was later improved so that recent submission rows are clickable. Clicking a submission opens:

    GET /dashboard/submission/<content_id>

The detail page was tested successfully in the browser. A fake content ID was also tested and returned:

    HTTP/1.1 404 NOT FOUND

After the dashboard refactor, `/submit` was tested again with a metadata submission. The submission succeeded and analytics updated from `32` total submissions to `33`, confirming that the refactor did not break the backend API.

## Multi-Modal Metadata Support

Provenance Guard supports a second content type:

    content_type: "metadata"

Instead of raw text, the creator can submit structured authorship and provenance metadata.

Example metadata fields:

- `title`
- `description`
- `declared_ai_assistance`
- `ai_generated_draft`
- `ai_tool_used`
- `verified_human`
- `has_version_history`
- `draft_count`
- `revision_count`
- `time_spent_minutes`

The system converts the metadata object into a readable summary and runs the same detection pipeline on that summary. It also passes the original metadata object into the provenance metadata signal.

Metadata test result:

    content_type: metadata
    attribution: uncertain
    confidence: 0.702
    metadata_summary: present
    audit log: metadata_summary present

Unsupported content type test:

    curl -i -X POST http://localhost:5000/submit -H "Content-Type: application/json" -d "{\"creator_id\":\"unsupported-test-user\",\"content_type\":\"image\",\"metadata\":{\"title\":\"x\"}}"

Result:

    HTTP/1.1 400 BAD REQUEST

Response:

    {
      "error": "Unsupported content_type 'image'. Supported types are 'text' and 'metadata'.",
      "status": "error"
    }

## Stretch Features Completed

### Ensemble Detection

Completed.

The backend uses four detection signals and combines them through a weighted ensemble. The response and audit log include individual signal scores and the final confidence score.

### Provenance Certificate

Completed.

The backend supports:

    POST /verify-human
    GET /certificate/<creator_id>

A verified creator receives a certificate ID, and future submissions from that creator include certificate context in the response.

### Analytics Dashboard

Completed.

The backend supports:

    GET /analytics
    GET /dashboard
    GET /dashboard/submission/<content_id>

`GET /analytics` returns structured JSON. `GET /dashboard` provides a browser-based visual dashboard for demo and review.

The dashboard code was moved into a separate `dashboard.py` file so `app.py` can stay focused on backend API routes. The dashboard now includes clickable submission detail pages for reviewing classification evidence.

### Multi-Modal Structured Metadata Support

Completed.

The backend supports:

    content_type: "metadata"

The system converts structured metadata into a readable summary, analyzes it through the ensemble pipeline, and records the metadata summary in the audit log.

## Known Limitations

Provenance Guard is not a perfect AI detector.

Known limitations include:

- Short text can be difficult to classify reliably.
- Formal human writing may look AI-like.
- Poetry or repeated creative language may trigger template-pattern signals.
- Heavily edited AI output may look human.
- Non-native or multilingual writing may be misread by stylometric heuristics.
- Metadata can be incomplete or misleading.
- A verified human certificate verifies creator provenance status, not the authorship of every future submission.
- The audit log uses a local JSON file, which is fine for a class project but not ideal for production.
- In-memory rate limiting is fine for local testing but would need shared storage such as Redis in production.

## Spec Reflection

The spec helped guide the implementation by forcing the system to include more than just a classifier. The transparency label, confidence score, appeals workflow, audit log, and rate limiting requirements pushed the project toward a more responsible trust-and-safety backend.

One way my implementation diverged from the simplest version of the spec is that I used a wide `uncertain` range and added safety downgrade logic when signals strongly disagreed. I made that choice because the project is about creator trust, and a false positive could be more harmful than returning an uncertain result.

The stretch features also shaped the final design. The certificate feature gives verified creators additional context. The analytics dashboard makes the system easier to demo and monitor. The metadata content type shows how the system can evaluate structured provenance information, not only raw text.

## AI Usage

I used AI tools as coding and planning assistants during this project. I used Claude to generate focused code drafts for specific backend changes, such as route handlers, helper functions, dashboard rendering, and metadata support. I reviewed the output, tested it locally, and made corrections before committing.


Specific AI-assisted instances:

1. I asked Claude to draft the initial Flask `/submit` route and Groq classification function. Claude produced a working starting point, but I tested the Groq signal separately, verified the audit log behavior, and later replaced placeholder confidence and label logic with the real ensemble scoring and label system.

2. I asked Claude to add the appeals workflow, certificate endpoints, rate limiting, and analytics endpoint. I reviewed the generated code and added fixes, including a JSON `429` rate-limit handler and extra audit-log fields so appeal entries clearly included `status`, `appeal_status`, `content_status`, `creator_reasoning`, and `appeal_reasoning`.

Human decisions included:

- Choosing a conservative uncertainty range
- Rejecting unfair or overly biased test prompts
- Keeping the dashboard inside Flask instead of adding Gradio
- Using structured metadata instead of image upload for the multi-modal stretch
- Verifying all test outputs before committing


## Future Improvements

Future improvements could include:

- Replacing the local JSON audit log with SQLite or PostgreSQL
- Adding authentication for reviewers
- Adding pagination for the audit log
- Adding a frontend form for submissions and appeals
- Adding charts to the dashboard
- Supporting uploaded files or images
- Adding stronger multilingual testing
- Adding a better calibration dataset
- Adding separate scoring behavior for poetry, captions, essays, and policy writing