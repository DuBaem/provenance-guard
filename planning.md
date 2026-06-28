# Provenance Guard Planning Document

## Project Overview

Provenance Guard is a backend system for creative sharing platforms. It analyzes submitted content, estimates whether the content is likely AI-generated, likely human-written, or uncertain, and returns a transparency label that can be shown to readers.

The system is designed to avoid overclaiming authorship decisions. A false positive, where real human work is labeled as AI-generated, can harm creator trust. Because of that, the system will use confidence scoring, uncertainty labels, appeals, and provenance evidence instead of making unsupported binary judgments.

## Milestone 1 Architecture Notes

### Submission Flow

To be filled from Milestone 1 Step 1.1.

### Detection Signals

To be filled from Milestone 1 Step 1.2.

### False Positive Policy

To be filled from Milestone 1 Step 1.3.

### API Surface

To be filled from Milestone 1 Step 1.4.

## Architecture

### Architecture Narrative

When a creator submits content to Provenance Guard, the request first passes through the rate limiter to prevent abuse. The API then validates the required fields, creates a unique `content_id`, and routes the submission based on `content_type`. Text content goes through the text analysis pipeline, while metadata content goes through the metadata analysis path.

The detection pipeline runs four signals: Groq LLM classification, stylometric heuristics, repetition/template pattern detection, and provenance metadata checking. Each signal is normalized to a `0.0` to `1.0` AI-likelihood score. The ensemble scorer combines those normalized scores into one `combined_ai_score`, maps the score to an attribution result, and sends the result to the transparency label generator.

The system saves the current content state in the content store and writes a historical event to the audit log. Appeals use the original `content_id` to locate the classification decision, attach creator reasoning and structured evidence, update the content status to `under_review`, and preserve the appeal event in the audit log. Reviewer decisions are also logged so the system keeps a complete history of the original classification, appeal, review decision, and final status.

### Submission Flow

```text
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
    | raw llm assessment and llm_score
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
Content Store
    |
    | save current content record
    | status: classified
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
```

### Appeal Flow

```text
Creator / Platform
    |
    | POST /appeal
    | content_id, creator_id, creator_reasoning, evidence
    v
Provenance Guard API
    |
    | validate content_id exists
    | validate creator_id matches or is allowed to appeal
    | validate creator_reasoning is present
    | validate structured evidence format if provided
    v
Appeal Handler
    |
    | update content status to under_review
    | attach creator reasoning
    | attach structured evidence
    v
Content Store
    |
    | save current content status: under_review
    | save appeal_status: submitted
    v
Audit Logger
    |
    | event_type: appeal_submitted
    | timestamp
    | content_id
    | creator_id
    | creator_reasoning
    | evidence
    | status: under_review
    v
JSON Response
    |
    | appeal received
    | status: under_review
    v
Creator / Platform
```

### Appeal Review Flow

```text
Reviewer
    |
    | PATCH /appeal/<content_id>
    | reviewer_id, decision, reviewer_notes
    v
Provenance Guard API
    |
    | validate content_id exists
    | validate decision is approved, rejected, or needs_more_info
    | validate reviewer_notes are present
    v
Appeal Review Handler
    |
    | approved -> appeal_status: approved, content_status: human_review_overturned
    | rejected -> appeal_status: rejected, content_status: classified
    | needs_more_info -> appeal_status: needs_more_info, content_status: under_review
    v
Content Store
    |
    | save updated appeal status
    | save updated content status
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
```

### Certificate Flow

```text
Creator
    |
    | POST /verify-human
    | creator_id, verification_method, evidence_summary
    v
Provenance Guard API
    |
    | validate creator_id
    | validate verification_method
    | validate evidence_summary
    v
Certificate Handler
    |
    | issue certificate_id
    | set verified_human: true
    v
Content Store
    |
    | save creator certificate status
    v
Audit Logger
    |
    | event_type: certificate_issued
    | creator_id
    | certificate_id
    | verification_method
    | verification status
    v
JSON Response
```

### Certificate Lookup Flow

```text
Creator / Platform
    |
    | GET /certificate/<creator_id>
    v
Certificate Handler
    |
    | retrieve certificate status
    v
JSON Response
```

### Analytics Flow

```text
Dashboard / Reviewer
    |
    | GET /analytics
    v
Analytics Handler
    |
    | read current content records
    | read historical audit log events
    | calculate total submissions
    | calculate likely_ai, uncertain, and likely_human counts
    | calculate appeal count and appeal rate
    | calculate average confidence
    v
Analytics JSON Response
```

## Required Feature Planning

### Detection Signals

Provenance Guard will use a four-signal ensemble detection pipeline. Each signal captures a different property of the submitted content, and the final result will be based on the combined evidence instead of a single detector.

Each signal will produce or be converted into an AI-likelihood score from `0.0` to `1.0`.

- `0.0` means the signal strongly suggests human-written content.
- `0.5` means the signal is uncertain.
- `1.0` means the signal strongly suggests AI-generated content.

The system will not treat any single signal as final proof. This is important because AI detection is uncertain, and polished human writing can sometimes look AI-generated.

#### Signal 1: Groq LLM Classification

**What it measures:**  
This signal asks the Groq `llama-3.3-70b-versatile` model to classify whether the submitted content reads as AI-generated, human-written, or uncertain.

**Why this signal was chosen:**  
An LLM can evaluate broad writing patterns that are difficult to capture with simple rules. It can consider tone, coherence, generic phrasing, smoothness, and whether the content sounds overly polished or formulaic.

**Expected output:**

```json
{
  "classification": "likely_ai | uncertain | likely_human",
  "score": 0.0,
  "reasoning": "Short explanation of what the model noticed."
}
```

The `score` will represent AI likelihood on a `0.0` to `1.0` scale.

**Blind spot:**  
The LLM can be wrong. It may classify polished human writing as AI-generated, especially if the writing is formal, edited, academic, or corporate. It may also miss AI-generated content that has been heavily revised by a human.

#### Signal 2: Stylometric Heuristics

**What it measures:**  
This signal measures structural properties of the writing using pure Python. These may include sentence length variance, vocabulary diversity, punctuation density, and average sentence complexity.

**Why this signal was chosen:**  
AI-generated writing often has smoother and more uniform structure. Human writing is often more irregular, with more variation in sentence rhythm, punctuation, sentence length, and word choice.

**Expected output:**

```json
{
  "score": 0.0,
  "metrics": {
    "sentence_length_variance": 0.0,
    "type_token_ratio": 0.0,
    "punctuation_density": 0.0
  },
  "reasoning": "Short explanation of the structural patterns."
}
```

The final `score` will represent AI likelihood on a `0.0` to `1.0` scale.

**Blind spot:**  
Formal human writing can appear uniform and polished, which may make it look AI-like to stylometric rules. Short text can also be difficult to score because there may not be enough sentence or vocabulary variation to measure reliably.

#### Signal 3: Repetition and Template Pattern Signal

**What it measures:**  
This signal looks for repeated phrases, predictable transitions, generic wording, and template-like structure. It checks for common formulaic phrases such as "It is important to note that," "Furthermore," "In conclusion," and other repeated or overly safe patterns.

**Why this signal was chosen:**  
Generated writing often relies on predictable transitions and generic phrasing. This signal gives the system another independent way to detect formulaic writing without depending on the LLM.

**Expected output:**

```json
{
  "score": 0.0,
  "matched_patterns": [],
  "repetition_count": 0,
  "reasoning": "Short explanation of repeated or template-like patterns."
}
```

The `score` will represent AI likelihood on a `0.0` to `1.0` scale.

**Blind spot:**  
Some human writers naturally use formal transitions, especially in school essays, professional reports, grant writing, or policy writing. This signal should not be treated as proof of AI generation by itself.

#### Signal 4: Provenance Metadata Signal

**What it measures:**  
This signal checks creator-level and submission-level provenance evidence. It may use verified human certificate status, available draft history, revision notes, structured metadata, and appeal evidence.

**Why this signal was chosen:**  
The goal of Provenance Guard is not only to detect AI-like text, but also to protect human creators from false positives. Provenance evidence gives the system a way to recognize when a creator has supporting evidence that the work is human-made.

**Expected output:**

```json
{
  "score": 0.0,
  "verified_human": false,
  "certificate_id": null,
  "evidence_summary": "Short summary of available provenance evidence."
}
```

For this signal, a lower score means stronger human provenance. A verified human certificate or strong draft evidence should reduce the final AI-risk score.

**Blind spot:**  
Lack of provenance evidence does not mean the work is AI-generated. Many honest creators may not have a certificate, draft history, or structured metadata available. Because of this, missing provenance evidence should not heavily penalize a creator.

#### Ensemble Combination Plan

The final system will combine the four normalized signal scores using a weighted ensemble:

| Signal | Weight |
|---|---:|
| Groq LLM Classification | 40% |
| Stylometric Heuristics | 30% |
| Repetition / Template Pattern Signal | 20% |
| Provenance Metadata Signal | 10% |

The planned scoring formula is:

```text
combined_ai_score =
  (llm_score * 0.40) +
  (stylometric_score * 0.30) +
  (template_score * 0.20) +
  (provenance_score * 0.10)
```

This weighting gives the LLM the largest influence while preventing it from becoming the only decision-maker. The stylometric and template signals provide independent structural evidence. The provenance signal is intentionally weighted lower because it should protect verified creators, but it should not automatically override all other signals.

The combined score will later be mapped to one of three attribution results:

- `likely_ai`
- `uncertain`
- `likely_human`

The exact thresholds for these categories will be defined in the uncertainty representation section.

### Uncertainty Representation

Provenance Guard will treat the final score as an AI-likelihood score, not as absolute proof of authorship. The score will range from `0.0` to `1.0`.

- `0.0` means the combined evidence strongly points toward human-written content.
- `0.5` means the combined evidence is ambiguous.
- `1.0` means the combined evidence strongly points toward AI-generated content.

The system will use the name `combined_ai_score` internally. In API responses, this value may be returned as `confidence` so the response remains simple, but the README and label text will explain that the score represents AI likelihood.

#### Thresholds

The system will use asymmetric thresholds because false positives are more harmful than false negatives in a creative platform. A human creator should not be strongly labeled as AI-generated unless the evidence is high.

| Combined AI Score Range | Attribution Result | Meaning |
|---:|---|---|
| `0.00` to `0.35` | `likely_human` | The system found stronger evidence of human authorship than AI generation. |
| `0.36` to `0.77` | `uncertain` | The system does not have enough confidence to make a strong attribution claim. |
| `0.78` to `1.00` | `likely_ai` | The system found strong evidence that the content may be AI-generated. |

The uncertain range is intentionally wide. This protects creators whose work may look polished, formal, repetitive, or highly edited even when it is human-written.

#### Meaning of a 0.6 Score

A score of `0.6` means the content has some AI-like signals, but not enough to justify a strong AI-generated label. In this system, `0.6` falls inside the uncertain range. The reader-facing label should communicate that the system cannot confidently determine authorship.

This is different from a score like `0.95`. A score of `0.95` means the signals strongly agree that the content appears AI-generated, so the system can return the likely AI label.

#### Raw Signal Normalization

Each signal may produce a different kind of raw output. Before scoring, every signal will be normalized into a `0.0` to `1.0` AI-likelihood score.

Examples:

| Signal | Raw Output | Normalized Score |
|---|---|---:|
| Groq LLM Classification | Model says likely AI with high confidence | `0.85` |
| Stylometric Heuristics | Low sentence variation and low vocabulary diversity | `0.72` |
| Template Pattern Signal | Several formulaic phrases detected | `0.68` |
| Provenance Metadata Signal | Verified human certificate exists | `0.10` |

After normalization, the weighted ensemble formula will produce one `combined_ai_score`.

#### Calibration Plan

The scoring system will be tested with at least four input types:

1. Clearly AI-generated content
2. Clearly human-written content
3. Formal human writing that may look AI-like
4. Lightly edited AI output that may look more human

The goal is not perfect detection. The goal is meaningful score separation. Clearly AI-generated writing should score much higher than casual human writing. Borderline cases should usually fall into the uncertain range instead of being forced into a binary label.

#### False Positive Safety Rule

When the signals disagree, the system should prefer `uncertain` over `likely_ai`.

This rule protects human creators from being unfairly labeled as AI-generated when the evidence is mixed.

### Transparency Label Design

Provenance Guard will return a reader-facing transparency label with every classification response. The label must be plain enough for a non-technical reader to understand, but careful enough not to overstate what the system knows.

The label will be based on the final `combined_ai_score`, the attribution result, and the creator's provenance certificate status if one exists.

#### Label Design Principles

The label language will follow four rules:

1. It will describe signals and likelihood, not make absolute claims.
2. It will avoid accusing the creator of dishonesty.
3. It will make uncertainty visible instead of hiding it.
4. It will give creators a path to appeal when they disagree with the result.

#### Label Variants

| Attribution Result | Score Range | Label Variant | Exact Reader-Facing Text |
|---|---:|---|---|
| `likely_human` | `0.00` to `0.35` | High-confidence human | "This content shows strong signs of human authorship. Provenance Guard found low evidence of AI generation based on the available signals." |
| `uncertain` | `0.36` to `0.77` | Uncertain | "Provenance Guard could not confidently determine whether this content was human-written or AI-generated. The available signals are mixed, so this result should be treated as uncertain." |
| `likely_ai` | `0.78` to `1.00` | High-confidence AI | "This content shows strong signs of AI generation. Provenance Guard found high AI-likelihood signals, but this result is not a final judgment of authorship." |

#### Certificate-Aware Label Add-On

If the creator has a verified human certificate, the system may add this sentence after the main label:

```text
This creator has a verified human provenance certificate on record.
```

This certificate add-on does not erase the classification result. It gives readers additional context and helps reduce false-positive harm for verified creators.

#### API Label Output

The `/submit` endpoint will return the selected label as a string in the JSON response.

Example response field:

```json
{
  "label": "Provenance Guard could not confidently determine whether this content was human-written or AI-generated. The available signals are mixed, so this result should be treated as uncertain."
}
```

#### Label Behavior

The label must change when the attribution result changes. The system should never return the same label text for every score.

Expected behavior:

- A low score such as `0.22` should return the high-confidence human label.
- A middle score such as `0.60` should return the uncertain label.
- A high score such as `0.91` should return the high-confidence AI label.

#### Appeal Language

For uncertain and likely AI results, the frontend or README can explain that creators may appeal the result. The backend will support this through the `/appeal` endpoint. The appeal process will let a creator submit reasoning and structured evidence, then mark the content as `under_review`.

### Appeals Workflow

Provenance Guard will include an appeals workflow so creators can contest a classification they believe is wrong. This is especially important because false positives can harm creator trust.

An appeal does not automatically change the original classification. Instead, it changes the content status to `under_review`, records the creator's reasoning and evidence, and creates a review trail for a human reviewer.

#### Who Can Submit an Appeal

A creator can submit an appeal for content connected to their `creator_id`.

The appeal request must include:

- `content_id`
- `creator_id`
- `creator_reasoning`

The appeal request may also include structured evidence.

#### Appeal Submission Endpoint

Appeals will be submitted through:

```text
POST /appeal
```

Expected request body:

```json
{
  "content_id": "content-123",
  "creator_id": "creator-456",
  "creator_reasoning": "I wrote this myself based on personal experience and can explain the revision process.",
  "evidence": {
    "draft_notes": "The first draft was written before the final version and later revised for tone.",
    "revision_summary": "I changed the title, rewrote the second paragraph, and removed repeated phrases.",
    "external_links": [
      "https://example.com/version-history"
    ],
    "supporting_files_note": "Screenshots or source files can be reviewed manually outside this demo."
  }
}
```

Expected response:

```json
{
  "content_id": "content-123",
  "status": "under_review",
  "message": "Appeal received with creator reasoning and evidence. The content has been marked for human review."
}
```

#### Appeal Submission Behavior

When an appeal is received, the system will:

1. Validate that the `content_id` exists.
2. Validate that the `creator_id` is allowed to appeal the content.
3. Validate that `creator_reasoning` is present.
4. Validate the evidence format if evidence is provided.
5. Update the content status to `under_review`.
6. Save the appeal reasoning and evidence.
7. Write an `appeal_submitted` event to the audit log.
8. Return a confirmation response.

#### Structured Evidence

For this version, appeal evidence will be accepted as structured JSON instead of file upload. This keeps the system focused and avoids unnecessary file storage complexity.

Supported evidence fields may include:

- `draft_notes`
- `revision_summary`
- `external_links`
- `supporting_files_note`

This is enough for the backend to preserve the creator's explanation and provide context to a human reviewer.

#### Human Review Endpoint

A reviewer will resolve an appeal through:

```text
PATCH /appeal/<content_id>
```

Expected request body:

```json
{
  "reviewer_id": "reviewer-001",
  "decision": "rejected",
  "reviewer_notes": "The submitted evidence did not provide enough provenance context to overturn the original classification."
}
```

Supported reviewer decisions:

| Decision | Appeal Status | Content Status | Meaning |
|---|---|---|---|
| `approved` | `approved` | `human_review_overturned` | The reviewer accepts the appeal and overturns the original classification. |
| `rejected` | `rejected` | `classified` | The reviewer rejects the appeal and keeps the original classification. |
| `needs_more_info` | `needs_more_info` | `under_review` | The reviewer needs more evidence before making a final decision. |

Expected response for a rejected appeal:

```json
{
  "content_id": "content-123",
  "appeal_status": "rejected",
  "content_status": "classified",
  "message": "Appeal reviewed and rejected. Original classification remains in place."
}
```

Expected response for an approved appeal:

```json
{
  "content_id": "content-123",
  "appeal_status": "approved",
  "content_status": "human_review_overturned",
  "message": "Appeal approved. The original classification has been overturned after human review."
}
```

#### Audit Log Requirements

The audit log will preserve both the original classification and the appeal activity.

An appeal submission event should include:

```json
{
  "event_type": "appeal_submitted",
  "timestamp": "2026-06-26T00:00:00Z",
  "content_id": "content-123",
  "creator_id": "creator-456",
  "creator_reasoning": "I wrote this myself based on personal experience.",
  "evidence": {
    "draft_notes": "The first draft was written before the final version.",
    "revision_summary": "The piece was revised several times."
  },
  "status": "under_review"
}
```

An appeal review event should include:

```json
{
  "event_type": "appeal_reviewed",
  "timestamp": "2026-06-26T00:05:00Z",
  "content_id": "content-123",
  "reviewer_id": "reviewer-001",
  "decision": "rejected",
  "reviewer_notes": "The submitted evidence did not provide enough provenance context.",
  "appeal_status": "rejected",
  "content_status": "classified"
}
```

#### Reviewer View

A human reviewer should be able to inspect:

- The original submitted content
- The original attribution result
- The original confidence score
- The individual signal scores
- The transparency label shown to the reader
- The creator's appeal reasoning
- Any structured evidence submitted by the creator
- The creator's verified human certificate status, if available
- The audit history for the content

This gives the reviewer enough context to decide whether the original classification should stand, be overturned, or require more information.

### Anticipated Edge Cases

Provenance Guard will not be reliable for every type of creative content. The system is designed to communicate uncertainty honestly, especially when the signals are likely to disagree or when a text has unusual stylistic features.

#### Edge Case 1: Poetry With Repetition and Simple Language

A poem may intentionally repeat words, phrases, or sentence structures for rhythm and emotional effect. The repetition and template pattern signal may treat that repetition as formulaic, even when it is an intentional human writing choice.

**Why this is difficult:**  
The template signal looks for repeated patterns, but poetry often uses repetition as a valid creative technique.

**Expected handling:**  
The system should avoid labeling this kind of work as `likely_ai` unless other signals strongly agree. If the score falls in the middle range, the system should return `uncertain`.

#### Edge Case 2: Formal Human Writing

A human-written academic essay, policy memo, grant proposal, or professional article may be polished, structured, and predictable. This can make the stylometric signal and Groq LLM signal score the text as more AI-like.

**Why this is difficult:**  
Formal writing often has low sentence variation, careful transitions, and abstract phrasing. These are also features that can appear in generated writing.

**Expected handling:**  
The system should treat formal tone as weak evidence by itself. If the signals are not strongly aligned, the result should remain `uncertain`.

#### Edge Case 3: Heavily Edited AI Output

A creator may start with AI-generated text and then heavily revise it. The final version may include human edits, irregular phrasing, and personal details that reduce the AI-likelihood score.

**Why this is difficult:**  
The system analyzes the submitted final text, not the full creation process. Heavy editing can blur the difference between generated and human-written work.

**Expected handling:**  
The system may return `uncertain` if the signals are mixed. Provenance evidence, draft notes, and revision history should help reviewers understand the creation process during appeals.

#### Edge Case 4: Very Short Text

A short caption, poem fragment, quote, or one-paragraph submission may not provide enough material for reliable signal analysis.

**Why this is difficult:**  
Stylometric features such as sentence length variance and vocabulary diversity become less meaningful when there are only a few words or sentences.

**Expected handling:**  
Very short content should be handled carefully. The system should return lower confidence or `uncertain` when there is not enough text to support a strong classification.

#### Edge Case 5: Non-Native or Multilingual Writing

A human writer using English as an additional language may write with unusual sentence structure, repeated phrasing, or simplified vocabulary. The system may incorrectly treat this as AI-like.

**Why this is difficult:**  
Stylometric and template-based signals may confuse language-learning patterns with generated patterns.

**Expected handling:**  
The system should avoid overconfidence. If the text shows unusual structure but the evidence is not strong, the result should be `uncertain`.

#### Edge Case 6: Metadata Without Enough Context

For the multi-modal metadata path, a creator may submit structured metadata that is incomplete or too vague. For example, a metadata submission may include a title and draft count but no meaningful revision history.

**Why this is difficult:**  
Metadata can support provenance, but weak metadata does not prove human authorship or AI generation.

**Expected handling:**  
Missing or weak metadata should not automatically increase AI risk. It should simply limit how much the provenance metadata signal can help.

#### Edge Case 7: Verified Creator With AI-Assisted Content

A creator may have a verified human certificate but still submit content that was partly generated or heavily assisted by AI.

**Why this is difficult:**  
A certificate verifies creator provenance status, not the authorship of every future submission.

**Expected handling:**  
The provenance certificate should reduce false-positive risk, but it should not automatically override the other detection signals. The label may show the certificate add-on while still preserving the classification result.

#### Edge Case Policy

When edge cases create mixed or weak evidence, Provenance Guard should prefer `uncertain` over `likely_ai`. This keeps the system honest and reduces the chance of unfairly labeling human creators as AI-generated.

## AI Tool Plan

This project will use Claude as the AI coding assistant for implementation support. Claude will be used to help generate focused code drafts, but the code will not be accepted blindly. For each implementation milestone, I will provide Claude with the relevant planning sections, ask for a specific piece of code, then review, test, and revise the output before adding it to the project.

### Milestone 3 AI Plan: Submission Endpoint and First Detection Signal

#### Spec sections to provide

For Milestone 3, I will provide these planning sections to Claude:

- Project Overview
- Architecture Narrative
- Submission Flow
- API Surface
- Detection Signals
- Signal 1: Groq LLM Classification

#### What I will ask Claude to generate

I will ask Claude to generate:

1. A minimal Flask app structure.
2. A `POST /submit` route.
3. Request validation for `creator_id`, `content_type`, and submitted content.
4. A unique `content_id` generator.
5. A Groq LLM classification function.
6. A placeholder confidence score and placeholder label.
7. A simple structured audit log entry for each submission.
8. A `GET /log` endpoint that returns recent audit entries.

#### How I will verify the output

I will verify Claude's generated code by checking that:

1. The Flask app starts without errors.
2. `POST /submit` accepts valid JSON.
3. Invalid requests return structured error responses.
4. The Groq function returns a structured result with classification, score, and reasoning.
5. The `/submit` response includes `content_id`, `attribution`, `confidence`, and `label`.
6. Each submission creates an audit log entry.
7. `GET /log` returns structured log entries as JSON.

I will test the Groq signal independently before relying on it inside the endpoint.

### Milestone 4 AI Plan: Second Signal and Confidence Scoring

#### Spec sections to provide

For Milestone 4, I will provide these planning sections to Claude:

- Detection Signals
- Uncertainty Representation
- Architecture Narrative
- Submission Flow
- Anticipated Edge Cases

#### What I will ask Claude to generate

I will ask Claude to generate:

1. A stylometric heuristic function.
2. A repetition and template pattern function.
3. A provenance metadata scoring function.
4. A signal normalization helper.
5. An ensemble confidence scoring function.
6. Logic that maps `combined_ai_score` to `likely_human`, `uncertain`, or `likely_ai`.

#### How I will verify the output

I will verify Claude's generated code by checking that:

1. Each signal returns a score from `0.0` to `1.0`.
2. Each signal can be tested independently.
3. The ensemble scoring formula matches the planned weights:
   - Groq LLM Classification: 40%
   - Stylometric Heuristics: 30%
   - Repetition / Template Pattern Signal: 20%
   - Provenance Metadata Signal: 10%
4. The score thresholds match the planning document:
   - `0.00` to `0.35`: `likely_human`
   - `0.36` to `0.77`: `uncertain`
   - `0.78` to `1.00`: `likely_ai`
5. Clearly AI-generated text scores higher than clearly human-written text.
6. Borderline cases usually fall into the uncertain range.
7. The audit log records individual signal scores and the combined score.

I will test the system with at least four input types: clearly AI-generated content, clearly human-written content, formal human writing, and lightly edited AI output.

### Milestone 5 AI Plan: Production Layer

#### Spec sections to provide

For Milestone 5, I will provide these planning sections to Claude:

- Transparency Label Design
- Appeals Workflow
- Architecture Narrative
- Appeal Flow
- Appeal Review Flow
- Certificate Flow
- Analytics Flow
- Uncertainty Representation

#### What I will ask Claude to generate

I will ask Claude to generate:

1. A transparency label generation function.
2. A `POST /appeal` endpoint.
3. A `PATCH /appeal/<content_id>` endpoint.
4. Flask-Limiter configuration for the `/submit` endpoint.
5. Complete audit log updates for submissions, appeals, and review decisions.
6. A `POST /verify-human` endpoint for provenance certificates.
7. A `GET /certificate/<creator_id>` endpoint.
8. A `GET /analytics` endpoint.

#### How I will verify the output

I will verify Claude's generated code by checking that:

1. All three transparency label variants are reachable.
2. The exact label text matches the planning document.
3. `POST /appeal` updates content status to `under_review`.
4. Appeal reasoning and structured evidence are saved.
5. `PATCH /appeal/<content_id>` supports `approved`, `rejected`, and `needs_more_info`.
6. Review decisions update both `appeal_status` and `content_status`.
7. Rate limiting returns `429` after the configured limit is exceeded.
8. The audit log includes at least three structured entries.
9. The audit log includes both classification and appeal events.
10. Certificate and analytics endpoints return structured JSON.

## Stretch Feature Planning

The project includes four stretch features: ensemble detection, provenance certificates, an analytics dashboard, and multi-modal support through structured metadata. These features extend the required backend into a stronger provenance system that is easier to audit, explain, and demo.

### Stretch 1: Ensemble Detection

The system uses a four-signal ensemble instead of relying on one AI detector. This stretch feature is already implemented in the detection pipeline.

The four signals are:

1. Groq LLM classification
2. Stylometric heuristics
3. Repetition and template pattern detection
4. Provenance metadata scoring

Each signal produces an AI-likelihood score from `0.0` to `1.0`.

- `0.0` means the signal strongly suggests human authorship.
- `0.5` means the signal is uncertain.
- `1.0` means the signal strongly suggests AI generation.

The weighted scoring formula is:

```text
combined_ai_score =
  (llm_score * 0.40) +
  (stylometric_score * 0.30) +
  (template_score * 0.20) +
  (provenance_score * 0.10)
```

The weights are intentionally uneven. The LLM signal receives the highest weight because it can reason across broad writing patterns. The stylometric signal receives the second-highest weight because it provides structural evidence from the text itself. The template signal captures formulaic and repetitive patterns. The provenance signal is weighted lower because it should support the decision, especially when metadata is available, but it should not automatically override every other signal.

The ensemble approach makes the system more explainable because the API response and audit log can show which signals contributed to the final confidence score.

Implementation status: complete.

Implemented in the backend through:

```text
classify_with_groq(text)
classify_with_stylometrics(text)
detect_template_patterns(text)
score_provenance_metadata(metadata)
calculate_combined_score(...)
determine_attribution(...)
```

Verification plan:

- Confirm that `/submit` returns all four signal scores.
- Confirm that the final confidence score changes across different submissions.
- Confirm that the attribution result maps to the documented thresholds.
- Confirm that the audit log stores the individual signal scores and final confidence score.

### Stretch 2: Provenance Certificate

The system includes a verified human provenance certificate feature. A creator can receive a verified human certificate through an additional verification step.

The certificate flow uses:

```text
POST /verify-human
```

Expected request fields include:

- `creator_id`
- `verification_method`
- `reviewer_id`
- optional `notes`

Supported verification methods are:

- `manual_review`
- `institutional_email`
- `portfolio_review`

When verification succeeds, the system creates a `certificate_id`, marks the creator as `verified_human: true`, and writes a `human_verified` event to the audit log.

The system also includes:

```text
GET /certificate/<creator_id>
```

This endpoint looks up the most recent verified human certificate for a creator.

When a verified creator submits content through `/submit`, the response includes certificate information, and the transparency label receives this add-on sentence:

```text
This creator has a verified human provenance certificate on record.
```

The certificate does not automatically force the final classification to `likely_human`. This is intentional. A verified human creator may still submit AI-assisted content. The certificate gives readers extra provenance context, but the system still preserves the classification result from the ensemble.

Implementation status: complete.

Implemented in the backend through:

```text
POST /verify-human
GET /certificate/<creator_id>
find_certificate_for_creator(creator_id)
generate_transparency_label(..., verified_human=True)
```

Verification plan:

- Confirm that `POST /verify-human` creates a certificate.
- Confirm that `GET /certificate/<creator_id>` retrieves the certificate.
- Confirm that `/submit` includes certificate information for verified creators.
- Confirm that the label includes the certificate add-on sentence.
- Confirm that the certificate event is written to the audit log.

### Stretch 3: Analytics Dashboard

The system includes a machine-readable analytics endpoint and will include a visual dashboard page for easier demo and review.

The existing endpoint is:

```text
GET /analytics
```

It reads from the audit log and returns structured JSON with:

- total submissions
- attribution counts
- average confidence score
- appeal count
- appeal status counts
- verified creator count
- average signal scores for the four detection signals

To make the analytics easier to understand during the project demo, I will add a visual Flask dashboard route:

```text
GET /dashboard
```

The dashboard will read from the same audit log and display:

- summary cards for total submissions, average confidence, appeal count, and verified creators
- attribution counts for `likely_human`, `uncertain`, and `likely_ai`
- appeal status counts for `under_review`, `approved`, `rejected`, and `needs_more_info`
- average signal scores for LLM, stylometric, template, and provenance signals
- a recent audit-events table showing recent submissions, appeals, reviews, and certificate events

I am choosing a Flask dashboard instead of Gradio because the project is already a Flask backend. Keeping the dashboard inside Flask avoids adding another dependency, keeps the project easier to run, and makes the walkthrough simpler because everything works from one server.

This dashboard satisfies the analytics dashboard stretch feature because it shows detection patterns, appeal rates/statuses, and additional metrics such as average confidence and verified creator count.

Implementation status: partially complete.

Already implemented:

```text
GET /analytics
```

Still to implement:

```text
GET /dashboard
```

Verification plan:

- Confirm that `GET /analytics` returns aggregate metrics as JSON.
- Confirm that `GET /dashboard` opens in the browser.
- Confirm that the dashboard displays detection patterns.
- Confirm that the dashboard displays appeal counts or appeal status counts.
- Confirm that the dashboard displays at least one additional metric, such as average confidence or verified creator count.

### Stretch 4: Multi-Modal Support Through Structured Metadata

The system will support a second content type beyond plain text:

```text
content_type: "metadata"
```

For this project, metadata means structured authorship and provenance information submitted as JSON. This is a lightweight multi-modal extension because the system is no longer limited to analyzing raw text. It can also evaluate structured information about how content was created.

A metadata submission may include fields such as:

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

The API will convert the structured metadata into a readable summary and send that summary through the same ensemble pipeline. The provenance metadata signal will also use the structured fields directly.

This second content type is intentionally based on structured metadata instead of image upload. The project is about provenance and authorship decisions, not computer vision. Structured metadata is easier to validate, easier to test, and more directly connected to the question of whether a creator has evidence about how the content was made.

The expected request shape will be:

```json
{
  "creator_id": "creator-123",
  "content_type": "metadata",
  "metadata": {
    "title": "Short Film Poster Caption",
    "description": "A caption describing the poster and how it was made.",
    "declared_ai_assistance": true,
    "ai_generated_draft": true,
    "ai_tool_used": "AI writing assistant",
    "verified_human": false,
    "has_version_history": true,
    "draft_count": 2,
    "revision_count": 3,
    "time_spent_minutes": 40
  }
}
```

The expected response should use the same response structure as text submissions:

```json
{
  "content_id": "content-123",
  "creator_id": "creator-123",
  "content_type": "metadata",
  "attribution": "uncertain",
  "confidence": 0.58,
  "label": "Provenance Guard could not confidently determine whether this content was human-written or AI-generated. The available signals are mixed, so this result should be treated as uncertain.",
  "signals": {
    "llm_score": 0.6,
    "stylometric_score": 0.5,
    "template_score": 0.5,
    "provenance_score": 0.7
  },
  "status": "classified"
}
```

The audit log should record metadata submissions the same way it records text submissions, including:

- timestamp
- content ID
- creator ID
- content type
- attribution result
- confidence score
- label
- individual signal scores
- provenance summary
- status

Implementation status: not complete yet.

Still to implement:

```text
content_type: "metadata"
metadata-to-summary helper
metadata validation in /submit
metadata submission test
metadata audit-log evidence
```

Verification plan:

- Confirm that `/submit` accepts `content_type: "metadata"`.
- Confirm that metadata requests require a valid JSON `metadata` object.
- Confirm that unsupported content types still return structured errors.
- Confirm that the metadata submission returns a normal classification response.
- Confirm that the audit log records the metadata submission with `content_type: "metadata"`.

### Stretch Feature Verification Plan

Before the final README is written, I will verify the stretch features as follows:

1. **Ensemble detection:** Confirm that `/submit` returns all four signal scores and a weighted confidence score.
2. **Provenance certificate:** Confirm that `POST /verify-human` creates a certificate and that `GET /certificate/<creator_id>` retrieves it.
3. **Certificate-aware labels:** Confirm that a verified creator's `/submit` response includes certificate information and appends the certificate sentence to the label.
4. **Analytics dashboard:** Confirm that `GET /analytics` returns aggregate metrics and that `GET /dashboard` displays those metrics visually in the browser.
5. **Multi-modal metadata support:** Confirm that `/submit` accepts `content_type: "metadata"` and returns a normal classification response.
6. **Audit log:** Confirm that text submissions, metadata submissions, appeals, review decisions, and certificate events are all written as structured JSON audit entries.