"""
Provenance Guard - Dashboard module
===================================

The visual analytics dashboard, extracted from app.py.

This module is self-contained: it imports nothing from app.py. Instead,
app.py calls register_dashboard_routes(...) and passes in the two helpers the
dashboard needs (read_audit_log and calculate_analytics_summary). That keeps
the dependency one-directional (app -> dashboard) and avoids a circular import.

It renders plain HTML via Flask's render_template_string with inline CSS only:
no templates folder, no static files, no frontend framework, no new
dependencies. Jinja autoescaping keeps any user-supplied audit values safe to
display.

Routes registered:
  GET /dashboard                          - summary + recent events
  GET /dashboard/submission/<content_id>  - full evidence for one submission
"""

import json

from flask import render_template_string


# ===========================================================================
# Helpers
# ===========================================================================
def find_submission_event(entries, content_id):
    """Return the 'submission_classified' event for a content_id, or None.

    Scans newest-first so that if a content_id ever appeared more than once,
    the most recent classification wins.
    """
    for entry in reversed(entries):
        if (
            entry.get("event_type") == "submission_classified"
            and entry.get("content_id") == content_id
        ):
            return entry
    return None


def find_related_appeals(entries, content_id):
    """Return (submitted, reviewed) lists of appeal events for a content_id.

    Each list preserves chronological order as stored in the audit log.
    """
    submitted = [
        e
        for e in entries
        if e.get("event_type") == "appeal_submitted"
        and e.get("content_id") == content_id
    ]
    reviewed = [
        e
        for e in entries
        if e.get("event_type") == "appeal_reviewed"
        and e.get("content_id") == content_id
    ]
    return submitted, reviewed


def safe_format(value):
    """Format any audit value for display.

    Dicts and lists become pretty-printed JSON; None/empty becomes a dash;
    everything else becomes its string form. Never raises.
    """
    if value is None or value == "" or value == [] or value == {}:
        return "-"
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


# ===========================================================================
# Templates  (inline CSS only)
# ===========================================================================
# Shared styling kept inline in each template so the module stays standalone.
_BASE_CSS = """
    body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
           margin: 0; background: #0f172a; color: #e2e8f0; }
    .wrap { max-width: 960px; margin: 0 auto; padding: 32px 20px 60px; }
    a { color: #7dd3fc; text-decoration: none; }
    a:hover { text-decoration: underline; }
    h1 { font-size: 22px; margin: 0 0 4px; }
    .sub { color: #94a3b8; font-size: 13px; margin-bottom: 28px; }
    h2 { font-size: 14px; text-transform: uppercase; letter-spacing: .06em;
         color: #94a3b8; margin: 32px 0 12px; }
    .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px;
            padding: 16px; }
    .card .v { font-size: 26px; font-weight: 700; }
    .card .k { font-size: 12px; color: #94a3b8; margin-top: 4px; }
    .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .pill { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
            padding: 12px 14px; display: flex; justify-content: space-between; }
    .pill .v { font-weight: 700; }
    table { width: 100%; border-collapse: collapse; font-size: 13px;
            background: #1e293b; border-radius: 12px; overflow: hidden; }
    th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid #334155; }
    th { color: #94a3b8; font-weight: 600; background: #172033; }
    tr:last-child td { border-bottom: none; }
    .muted { color: #64748b; }
    code { background: #0b1220; padding: 1px 6px; border-radius: 5px; }
    .panel { background: #1e293b; border: 1px solid #334155; border-radius: 12px;
             padding: 16px 18px; margin-bottom: 14px; }
    .row { display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px solid #2a3850; }
    .row:last-child { border-bottom: none; }
    .row .label { color: #94a3b8; width: 200px; flex: none; font-size: 13px; }
    .row .val { font-size: 14px; word-break: break-word; }
    pre { background: #0b1220; border: 1px solid #243044; border-radius: 8px;
          padding: 10px 12px; font-size: 12px; overflow-x: auto; margin: 4px 0 0; }
    .back { margin-bottom: 18px; display: inline-block; font-size: 13px; }
"""

DASHBOARD_TEMPLATE = (
    """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Provenance Guard - Dashboard</title>
  <style>"""
    + _BASE_CSS
    + """</style>
</head>
<body>
  <div class="wrap">
    <h1>Provenance Guard</h1>
    <div class="sub">Audit dashboard &middot; read-only view of <code>audit_log.json</code></div>

    <div class="cards">
      <div class="card"><div class="v">{{ s.total_submissions }}</div><div class="k">Total submissions</div></div>
      <div class="card"><div class="v">{{ s.average_confidence }}</div><div class="k">Avg confidence (AI-likelihood)</div></div>
      <div class="card"><div class="v">{{ s.appeal_count }}</div><div class="k">Appeals submitted</div></div>
      <div class="card"><div class="v">{{ s.verified_creator_count }}</div><div class="k">Verified creators</div></div>
    </div>

    <h2>Attribution counts</h2>
    <div class="grid3">
      <div class="pill"><span>likely_human</span><span class="v">{{ s.attribution_counts.likely_human }}</span></div>
      <div class="pill"><span>uncertain</span><span class="v">{{ s.attribution_counts.uncertain }}</span></div>
      <div class="pill"><span>likely_ai</span><span class="v">{{ s.attribution_counts.likely_ai }}</span></div>
    </div>

    <h2>Appeal status counts</h2>
    <div class="grid3">
      <div class="pill"><span>under_review</span><span class="v">{{ s.appeal_status_counts.under_review }}</span></div>
      <div class="pill"><span>approved</span><span class="v">{{ s.appeal_status_counts.approved }}</span></div>
      <div class="pill"><span>rejected</span><span class="v">{{ s.appeal_status_counts.rejected }}</span></div>
      <div class="pill"><span>needs_more_info</span><span class="v">{{ s.appeal_status_counts.needs_more_info }}</span></div>
    </div>

    <h2>Average signal scores</h2>
    <div class="grid3">
      <div class="pill"><span>llm</span><span class="v">{{ s.average_signal_scores.llm }}</span></div>
      <div class="pill"><span>stylometric</span><span class="v">{{ s.average_signal_scores.stylometric }}</span></div>
      <div class="pill"><span>template</span><span class="v">{{ s.average_signal_scores.template }}</span></div>
      <div class="pill"><span>provenance</span><span class="v">{{ s.average_signal_scores.provenance }}</span></div>
    </div>

    <h2>Recent audit events</h2>
    <table>
      <tr><th>Timestamp</th><th>Event</th><th>Content / Creator</th><th>Detail</th><th>Confidence</th></tr>
      {% for r in recent %}
      <tr>
        <td class="muted">{{ r.timestamp }}</td>
        <td>{{ r.event_type }}</td>
        <td>
          {% if r.content_id %}
            <a href="/dashboard/submission/{{ r.content_id }}">{{ r.ident }}</a>
          {% else %}
            {{ r.ident }}
          {% endif %}
        </td>
        <td>{{ r.detail }}</td>
        <td>{{ r.confidence }}</td>
      </tr>
      {% endfor %}
      {% if not recent %}
      <tr><td colspan="5" class="muted">No audit events yet.</td></tr>
      {% endif %}
    </table>
  </div>
</body>
</html>
"""
)

SUBMISSION_DETAIL_TEMPLATE = (
    """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Submission {{ d.content_id }} - Provenance Guard</title>
  <style>"""
    + _BASE_CSS
    + """</style>
</head>
<body>
  <div class="wrap">
    <a class="back" href="/dashboard">&larr; Back to dashboard</a>
    <h1>Submission detail</h1>
    <div class="sub"><code>{{ d.content_id }}</code></div>

    <h2>Overview</h2>
    <div class="panel">
      <div class="row"><div class="label">creator_id</div><div class="val">{{ d.creator_id }}</div></div>
      <div class="row"><div class="label">content_type</div><div class="val">{{ d.content_type }}</div></div>
      <div class="row"><div class="label">timestamp</div><div class="val">{{ d.timestamp }}</div></div>
      <div class="row"><div class="label">attribution</div><div class="val">{{ d.attribution }}</div></div>
      <div class="row"><div class="label">confidence</div><div class="val">{{ d.confidence }}</div></div>
      <div class="row"><div class="label">label</div><div class="val">{{ d.label }}</div></div>
      {% if d.metadata_summary %}
      <div class="row"><div class="label">metadata_summary</div><div class="val">{{ d.metadata_summary }}</div></div>
      {% endif %}
    </div>

    {% if d.show_certificate %}
    <h2>Certificate</h2>
    <div class="panel">
      <div class="row"><div class="label">creator_certificate_verified</div><div class="val">{{ d.certificate_verified }}</div></div>
      <div class="row"><div class="label">certificate_id</div><div class="val">{{ d.certificate_id }}</div></div>
    </div>
    {% endif %}

    <h2>Safety</h2>
    <div class="panel">
      <div class="row"><div class="label">safety_adjusted</div><div class="val">{{ d.safety_adjusted }}</div></div>
      <div class="row"><div class="label">safety_reason</div><div class="val">{{ d.safety_reason }}</div></div>
      <div class="row"><div class="label">signal_spread</div><div class="val">{{ d.signal_spread }}</div></div>
    </div>

    <h2>Signals</h2>
    <div class="panel">
      <div class="row"><div class="label">llm_score</div><div class="val">{{ d.llm_score }}</div></div>
      <div class="row"><div class="label">llm_reasoning</div><div class="val">{{ d.llm_reasoning }}</div></div>
      <div class="row"><div class="label">stylometric_score</div><div class="val">{{ d.stylometric_score }}</div></div>
      <div class="row"><div class="label">stylometric_reasoning</div><div class="val">{{ d.stylometric_reasoning }}</div></div>
      <div class="row"><div class="label">stylometric_metrics</div><div class="val"><pre>{{ d.stylometric_metrics }}</pre></div></div>
      <div class="row"><div class="label">template_score</div><div class="val">{{ d.template_score }}</div></div>
      <div class="row"><div class="label">template_reasoning</div><div class="val">{{ d.template_reasoning }}</div></div>
      <div class="row"><div class="label">matched_patterns</div><div class="val"><pre>{{ d.matched_patterns }}</pre></div></div>
      <div class="row"><div class="label">repetition_count</div><div class="val">{{ d.repetition_count }}</div></div>
      <div class="row"><div class="label">provenance_score</div><div class="val">{{ d.provenance_score }}</div></div>
      <div class="row"><div class="label">provenance_summary</div><div class="val">{{ d.provenance_summary }}</div></div>
    </div>

    <h2>Related appeals</h2>
    <div class="panel">
      <div class="row"><div class="label">appeal_submitted</div><div class="val">
        {% if submitted %}
          {% for a in submitted %}<pre>{{ a }}</pre>{% endfor %}
        {% else %}<span class="muted">None</span>{% endif %}
      </div></div>
      <div class="row"><div class="label">appeal_reviewed</div><div class="val">
        {% if reviewed %}
          {% for a in reviewed %}<pre>{{ a }}</pre>{% endfor %}
        {% else %}<span class="muted">None</span>{% endif %}
      </div></div>
    </div>
  </div>
</body>
</html>
"""
)

NOT_FOUND_TEMPLATE = (
    """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Not found - Provenance Guard</title>
  <style>"""
    + _BASE_CSS
    + """</style>
</head>
<body>
  <div class="wrap">
    <a class="back" href="/dashboard">&larr; Back to dashboard</a>
    <h1>Submission not found</h1>
    <div class="sub">No <code>submission_classified</code> event exists for content_id
      <code>{{ content_id }}</code>.</div>
  </div>
</body>
</html>
"""
)


# ===========================================================================
# Route registration
# ===========================================================================
def register_dashboard_routes(
    app, read_audit_log, calculate_analytics_summary, limiter=None
):
    """Attach the dashboard routes to an existing Flask app.

    Parameters:
      app                        - the Flask application instance
      read_audit_log             - callable returning the list of audit entries
      calculate_analytics_summary- callable returning the analytics summary dict
      limiter                    - optional Flask-Limiter instance. When passed,
                                   the original "30 per minute" limit is applied
                                   so /dashboard behaves exactly as before.
    """

    def _maybe_limit(limit_str):
        """Return limiter.limit(...) if a limiter was provided, else a no-op."""
        if limiter is not None:
            return limiter.limit(limit_str)

        def _identity(fn):
            return fn

        return _identity

    @app.route("/dashboard", methods=["GET"])
    @_maybe_limit("30 per minute")
    def dashboard():
        """Render the dashboard from the shared analytics summary."""
        summary = calculate_analytics_summary()

        # Most recent audit rows (newest first), pulling the most useful
        # identifier and detail field available for each event type.
        entries = read_audit_log()
        recent = []
        for entry in reversed(entries[-15:]):
            content_id = entry.get("content_id")
            ident = content_id or entry.get("creator_id") or "-"
            detail = (
                entry.get("attribution")
                or entry.get("appeal_status")
                or entry.get("verification_method")
                or "-"
            )
            confidence = entry.get("confidence")
            recent.append(
                {
                    "timestamp": entry.get("timestamp", "-"),
                    "event_type": entry.get("event_type", "-"),
                    "ident": ident,
                    # Only rows with a content_id become clickable links.
                    "content_id": content_id,
                    "detail": detail,
                    "confidence": confidence if confidence is not None else "-",
                }
            )

        return render_template_string(DASHBOARD_TEMPLATE, s=summary, recent=recent)

    @app.route("/dashboard/submission/<content_id>", methods=["GET"])
    @_maybe_limit("30 per minute")
    def dashboard_submission_detail(content_id):
        """Render the full evidence for one submission, or a 404 page."""
        entries = read_audit_log()
        submission = find_submission_event(entries, content_id)

        if submission is None:
            # Readable browser page + 404 status.
            return (
                render_template_string(NOT_FOUND_TEMPLATE, content_id=content_id),
                404,
            )

        submitted, reviewed = find_related_appeals(entries, content_id)

        certificate_verified = submission.get("creator_certificate_verified", False)
        certificate_id = submission.get("certificate_id")

        detail = {
            "content_id": submission.get("content_id", "-"),
            "creator_id": submission.get("creator_id", "-"),
            "content_type": submission.get("content_type", "-"),
            "timestamp": submission.get("timestamp", "-"),
            "attribution": submission.get("attribution", "-"),
            "confidence": submission.get("confidence", "-"),
            "label": submission.get("label", "-"),
            "metadata_summary": submission.get("metadata_summary"),
            # Certificate
            "show_certificate": bool(certificate_verified) or bool(certificate_id),
            "certificate_verified": certificate_verified,
            "certificate_id": certificate_id if certificate_id else "-",
            # Safety
            "safety_adjusted": submission.get("safety_adjusted", False),
            "safety_reason": submission.get("safety_reason") or "-",
            "signal_spread": submission.get("signal_spread", "-"),
            # Signals
            "llm_score": submission.get("llm_score", "-"),
            "llm_reasoning": submission.get("llm_reasoning", "-"),
            "stylometric_score": submission.get("stylometric_score", "-"),
            "stylometric_reasoning": submission.get("stylometric_reasoning", "-"),
            "stylometric_metrics": safe_format(submission.get("stylometric_metrics")),
            "template_score": submission.get("template_score", "-"),
            "template_reasoning": submission.get("template_reasoning", "-"),
            "matched_patterns": safe_format(submission.get("matched_patterns")),
            "repetition_count": submission.get("repetition_count", "-"),
            "provenance_score": submission.get("provenance_score", "-"),
            "provenance_summary": submission.get("provenance_summary", "-"),
        }

        return render_template_string(
            SUBMISSION_DETAIL_TEMPLATE,
            d=detail,
            submitted=[safe_format(a) for a in submitted],
            reviewed=[safe_format(a) for a in reviewed],
        )