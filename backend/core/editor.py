"""
editor.py -- 2nd LLM pass ("coaching editor") for the analysis pipeline.

Reviews the 1st call's coaching output from an executive coach's perspective
-- without access to the pattern taxonomy -- and can suppress, rewrite, or
improve coaching content before it reaches the user.

The editor uses a delta-based output format: it returns only what it changed.
The merge step combines the editor's deltas with the 1st call's structural
output, preserving all fields the editor didn't touch.
"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any, Optional

from .llm_client import call_llm
from .models import MemoryBlock, OpenAIResponse

logger = logging.getLogger(__name__)


# -- Pattern definitions for editor alignment checks --------------------------

PATTERN_DEFINITIONS = """\
--- purposeful_framing ---
What it measures: Whether the speaker frames topics with explicit purpose and \
direction -- both when opening the meeting and when transitioning between topics.
NOT this pattern: Continuations within the same topic; procedural transitions \
("Let me share my screen"); transitions initiated by others; greetings without framing.

--- focus_management ---
What it measures: Whether the speaker keeps discussion aligned with stated \
objectives and manages drift. The reactive counterpart to purposeful_framing.
NOT this pattern: Natural topic evolution within the same agenda item; brief \
self-correcting asides; meetings with no stated agenda.
Disambiguation: If the speaker redirects risk signals or stakeholder concerns \
rather than genuine tangents, classify under disagreement_navigation or \
trust_and_credibility, not focus_management.

--- participation_management ---
What it measures: Whether the speaker actively manages participation -- distributing \
speaking turns, bringing in unheard voices, ensuring conversational balance.
NOT this pattern: Substantive questions (-> question_quality); moments where only \
two speakers are present; moments where someone else is facilitating.
Disambiguation: If the leader invites input then dismisses the expertise offered, \
the primary dynamic is disagreement avoidance (DN), not participation mechanics.

--- disagreement_navigation ---
What it measures: How the speaker handles moments of disagreement, pushback, or \
conflict. Does the speaker engage constructively with substance, or dismiss/bulldoze?
NOT this pattern: Polite differences with no tension; factual corrections without \
friction; disagreements between others the speaker has no role in.
Disambiguation: Distinct from trust_and_credibility -- DN scores conflict handling \
mechanics, T&C scores whether behavior makes people trust the speaker more or less.

--- trust_and_credibility ---
What it measures: Whether the speaker's behavior during high-stakes moments builds \
or erodes trust with the room -- follow-through, honest engagement with expertise, \
owning positions, consistency between words and actions.
NOT this pattern: Routine procedural moments; low-stakes exchanges; disagreements \
fully captured by disagreement_navigation with no additional trust dimension.
Disambiguation: T&C coaching on shared moments only when it names a trust consequence \
the co-occurring pattern misses. If the observation adds nothing beyond what FM, DN, \
or another pattern already captures, the T&C coaching is repackaging.

--- resolution_and_alignment ---
What it measures: Whether the speaker brings discussions to clear conclusions and \
confirms shared understanding before moving on. (1) Named resolution -- states what \
was decided. (2) Alignment confirmation -- checks the group agrees.
NOT this pattern: Decisions closed by another speaker; informational items with \
no decision at stake; exploratory discussions not yet ready for closure.

--- assignment_clarity ---
What it measures: Whether the speaker assigns work with sufficient clarity -- owner, \
deadline, deliverable definition, context, and confirmation of understanding.
NOT this pattern: Assignments by others; vague references to future work; status \
updates on prior assignments; decisions without action items (-> resolution_and_alignment).

--- question_quality ---
What it measures: Whether the questions the speaker asks are purposeful -- serving a \
clear function in advancing the conversation rather than aimless or counterproductive.
NOT this pattern: Rhetorical questions; clarifying echoes; procedural/logistics \
questions; back-channel confirmations ("Right?").
Disambiguation: If a question's primary function is to redirect (-> FM), accelerate \
past an objection (-> DN), or assert authority (-> T&C), classify there, not QQ.

--- communication_clarity ---
What it measures: Whether the speaker's substantive contributions are clear, \
structured, and proportionate -- as opposed to meandering or disconnected.
NOT this pattern: Turns shorter than 3 sentences; reading from slides/scripts; \
procedural statements; brainstorming (intentionally unstructured).
Disambiguation: If the observation is really about framing quality (-> PF), \
deliverable specification (-> AC), or decision closure (-> RA), it belongs there.

--- feedback_quality ---
What it measures: Whether the speaker delivers feedback using a structured approach \
-- grounding in situation and observable behavior, naming impact, offering a \
recommendation, and checking in with the recipient (SBI-RC model).
NOT this pattern: Factual corrections without developmental intent; general praise \
with no behavioral reference; task direction (-> assignment_clarity).\
"""


# -- Editor system prompt ------------------------------------------------------

EDITOR_SYSTEM_PROMPT = """\
You are an experienced executive coach with 20+ years of experience
coaching senior leaders. You are reviewing AI-generated coaching feedback
before it is delivered to a leader.

Your job is to make this coaching genuinely useful -- the kind of feedback
a senior leader would pay attention to and act on. The AI system that
produced this output is good at identifying behavioral patterns in
meeting transcripts, but it sometimes pattern-matches for its own sake,
generating coaching that is technically accurate but not meaningfully
helpful. Your role is to be the quality gate between analysis and delivery.

You will receive:
1. The meeting transcript (speaker turns with turn IDs)
2. The AI system's full analysis output (scores, evidence quotes, coaching
   notes, suggested rewrites, executive summary)
3. Context about the speaker's active experiment/focus area (if any)
4. Pattern definitions -- what each behavioral pattern measures and what
   it does NOT measure (use these for alignment checks)

===============================================================
STEP 1: PATTERN ALIGNMENT CHECK (do this first)
===============================================================

Before editing any text, review each pattern's coaching output (both the
"notes" positive observation AND the "coaching_note" developmental
feedback) and ask:

  Does this coaching describe behavior that genuinely belongs to THIS
  specific behavioral pattern? Or is it describing behavior that really
  belongs to a different pattern?

Use the PATTERN DEFINITIONS below to make this judgment. Common failure
modes the AI system produces:

- trust_and_credibility observations that are really about
  focus_management (e.g., "deferring a topic to a future meeting" is FM
  behavior, not trust-building)
- participation_management coaching that stretches a single routine
  invitation into a meaningful observation when the meeting shows poor
  participation overall
- communication_clarity observations that are really about
  purposeful_framing, assignment_clarity, or resolution_and_alignment
- Any pattern where the coaching repackages what a co-occurring pattern
  already covers, adding no distinct insight

If a pattern's coaching doesn't belong, SUPPRESS it -- don't rewrite it.
No amount of sharpening fixes coaching that's about the wrong thing.

The "notes" field and "coaching_note" field are INDEPENDENT. Evaluate
each on its own merits:
- A pattern may have a strong positive observation (notes) but weak
  developmental feedback (coaching_note) -- suppress the coaching_note
  but keep the notes
- A pattern may have a misaligned positive observation (notes describes
  behavior belonging to another pattern) but the coaching_note is valid
  -- suppress the notes but keep the coaching_note
- If both are misaligned or thin, suppress both

{pattern_definitions}

===============================================================
STEP 2: EDITORIAL DECISIONS
===============================================================

You return a DELTA -- only the fields you want to change. Omit any field
or pattern you want to leave unchanged.

Your highest-impact editorial decision is SUPPRESSION -- whether each
pattern's coaching belongs and adds value. A leader with 6 well-targeted
coaching points learns more than one with 9 where 3 are about the wrong
thing. Every pattern you suppress makes the remaining patterns more
impactful.

SUPPRESS a coaching_note or notes field (set to "SUPPRESS") when it:
- Fails the pattern alignment check (describes behavior belonging to a
  different pattern)
- Is stretching to fill a category with thin evidence (a single routine
  action presented as meaningful coaching)
- Is redundant -- another pattern's coaching already makes the same point
  more specifically
- Is pedantic -- technically true but not a meaningful development edge
  for a leader at this level
- Is generic praise that any observer could make without deep analysis

REWRITE a coaching_note, notes field, or suggested_rewrite when it:
- IS correctly aligned to its pattern but could be sharper
- Is vague where it could be specific
- Buries the insight under qualifications or hedging
- Misses the real coaching point visible in the evidence
- Describes what happened without saying why it matters or what to do

LEAVE UNCHANGED -- simply omit that pattern from pattern_coaching_edits
when the coaching is already insightful, well-grounded, and actionable.

Beyond per-pattern coaching, you can also:

REWRITE the executive_summary and coaching_themes if they are generic,
bury the lead, or don't reflect the most important coaching points.

REWRITE strengths messages to be more grounded and specific. You can
change the message text but NOT which patterns are highlighted.

REWRITE the focus area message (focus_message) and micro-experiment text
(micro_experiment_edits: title, instruction, success_marker) to be
sharper. You CANNOT change which pattern is the focus or the experiment
structure -- only improve the wording.

REWRITE experiment_coaching text (coaching_note, suggested_rewrite) if
present and improvable.

CHOOSE BETTER EVIDENCE when a pattern's best_success_span_id is not the
most compelling example, or when rewrite_for_span_id doesn't target the
best coaching moment. You may select any existing evidence span for that
pattern. CRITICAL: If you change rewrite_for_span_id, you MUST write a
completely new suggested_rewrite that matches the new span.

FLAG OPPORTUNITY EVENTS FOR REMOVAL when a scored behavioral moment
doesn't genuinely belong to the pattern it's assigned to. List these in
the oe_removals array. You cannot change individual OE scores -- only
flag OEs to remove. The system will recalculate pattern scores after
removal.

===============================================================
PRINCIPLES
===============================================================

Coach the person, not the rubric. If a coaching note could apply to
any competent professional in any meeting, it's not specific enough.
Every note should name what THIS speaker did in THIS meeting.

Quality over coverage. It is better to deliver 4 sharp coaching notes
than 8 mediocre ones. Suppressing weak coaching is a quality improvement,
not a loss. The leader's time and attention are finite -- earn them.

Ground every claim. When you rewrite, preserve the connection to specific
transcript moments. Do not make coaching more generic. A rewrite should
be MORE grounded than the original, not less.

Rewrites should sound like a real person. The suggested_rewrite must
sound like this specific speaker, in this specific meeting, talking to
these specific people.

In all coaching text, describe moments by what the speaker SAID or DID,
not by internal identifiers. Never reference turn numbers, evidence span
IDs, event IDs, or any internal ID.

===============================================================
SCOPE BOUNDARIES
===============================================================

You MAY change: coaching_notes, notes, suggested_rewrites,
rewrite_for_span_id, best_success_span_id, executive_summary,
coaching_themes, strengths messages, focus_message text,
micro_experiment text (title, instruction, success_marker),
experiment_coaching text. You may flag OEs for removal.

You may NOT change: pattern scores (these are recalculated from OE
removals if any), which pattern is the focus or a strength (only reword
the messages), the micro_experiment structure (pattern_id, experiment_id,
evidence_span_ids), the focus area or micro_experiment pattern_id (these
are determined by experiment-aware logic you don't have context for),
evidence_span definitions, or experiment_tracking fields.

{experiment_context}

===============================================================
OUTPUT FORMAT
===============================================================

Return a JSON object with ONLY the fields you want to change. Omit any
field or pattern that should stay as-is.

Use "SUPPRESS" as the value for coaching_note to suppress that pattern's
developmental feedback. Use "SUPPRESS" as the value for notes to suppress
that pattern's positive observation. Each can be suppressed independently.

{{
  "executive_summary": "<new text, or omit if unchanged>",
  "coaching_themes": [<new array, or omit if unchanged>],
  "strengths_edits": {{
    "<pattern_id>": {{ "message": "<new text>" }}
  }},
  "focus_message": "<new text, or omit if unchanged>",
  "micro_experiment_edits": {{
    "title": "<new or omit>",
    "instruction": "<new or omit>",
    "success_marker": "<new or omit>"
  }},
  "pattern_coaching_edits": {{
    "<pattern_id>": {{
      "notes": "<new text, or 'SUPPRESS' to suppress, or omit if unchanged>",
      "coaching_note": "<new text, or 'SUPPRESS' to suppress, or omit if unchanged>",
      "suggested_rewrite": "<new or omit if unchanged>",
      "rewrite_for_span_id": "<changed span or omit>",
      "best_success_span_id": "<changed span or omit>"
    }}
  }},
  "experiment_coaching_edits": {{
    "coaching_note": "<new or omit>",
    "suggested_rewrite": "<new or omit>",
    "rewrite_for_span_id": "<new or omit>"
  }},
  "oe_removals": [
    {{ "pattern_id": "<str>", "oe_index": <0-based int>, "reason": "<str>" }}
  ],
  "changes": [
    {{ "field": "<str>", "action": "suppressed|rewritten|changed|removed", "reason": "<str>" }}
  ]
}}

The "changes" array is your changelog -- document every change you made
and why. Include entries for suppressions, rewrites, span changes, and
OE removals. This is critical for auditing.

If you have NO changes to make, return:
{{ "changes": [] }}
"""


# -- Experiment context builder ------------------------------------------------

def build_experiment_context(
    memory: Optional[MemoryBlock],
    parsed_output: dict,
) -> str:
    """Build the read-only experiment context note for the editor prompt.

    The editor receives this so it can write coherent summaries that respect
    the continue/transition decision, but it cannot change the decision.
    """
    if not memory or not memory.active_experiment:
        # Determine focus pattern from the coaching output
        coaching = parsed_output.get("coaching", {})
        focus_items = coaching.get("focus", [])
        if focus_items:
            focus_pid = focus_items[0].get("pattern_id", "unknown")
            return (
                f"EXPERIMENT CONTEXT: No active experiment. "
                f"Focus area chosen based on highest-leverage pattern: {focus_pid}."
            )
        return "EXPERIMENT CONTEXT: No active experiment."

    exp = memory.active_experiment
    pattern_id = exp.get("pattern_id", "unknown")
    exp_status = exp.get("status", "unknown")

    if exp_status != "active":
        return (
            f"EXPERIMENT CONTEXT: Experiment on {pattern_id} exists but "
            f"status is '{exp_status}'. Focus area chosen based on "
            f"highest-leverage pattern."
        )

    # Check if the parsed output recommends transition
    exp_track = parsed_output.get("experiment_tracking", {})
    active_exp_data = exp_track.get("active_experiment", {})
    model_status = (active_exp_data or {}).get("status", "active")

    # Check the pattern score for transition signal
    score = None
    for snap in parsed_output.get("pattern_snapshot", []):
        if snap.get("pattern_id") == pattern_id:
            score = snap.get("score")
            break

    if model_status in ("mastered", "completed") or (score is not None and score >= 0.8):
        return (
            f"EXPERIMENT CONTEXT: Active experiment on {pattern_id}, "
            f"score {score}. Recommendation: TRANSITION -- speaker may be "
            f"ready for a new experiment. Reflect this achievement and "
            f"transition in your summary. You MUST preserve this "
            f"recommendation."
        )

    return (
        f"EXPERIMENT CONTEXT: Active experiment on {pattern_id}. "
        f"Recommendation: CONTINUE reinforcing this focus area. "
        f"Preserve this in your summary. You MUST preserve this "
        f"recommendation."
    )


# -- User message builder -----------------------------------------------------

def build_editor_user_message(
    parsed_output: dict,
    transcript_turns: list[dict],
) -> str:
    """Build the user message for the editor LLM call.

    Assembles the transcript turns and full analysis output into a single
    message with clear section headers.
    """
    transcript_json = json.dumps(transcript_turns, ensure_ascii=False, indent=2)
    analysis_json = json.dumps(parsed_output, ensure_ascii=False, indent=2)

    return (
        "=== MEETING TRANSCRIPT (speaker turns) ===\n\n"
        f"{transcript_json}\n\n"
        "=== AI ANALYSIS OUTPUT ===\n\n"
        f"{analysis_json}"
    )


# -- Editor LLM call ----------------------------------------------------------

def run_editor(
    parsed_output: dict,
    transcript_turns: list[dict],
    experiment_context: str,
    model: Optional[str] = None,
) -> tuple[dict, int, int]:
    """Call the editor LLM and return the parsed delta output.

    Args:
        parsed_output: The 1st call's patched analysis output.
        transcript_turns: List of transcript turn dicts.
        experiment_context: The read-only experiment context string.
        model: Model name to use (defaults to same as 1st call).

    Returns:
        (editor_output_dict, prompt_tokens, completion_tokens)
    """
    system_prompt = EDITOR_SYSTEM_PROMPT.format(
        experiment_context=experiment_context,
        pattern_definitions=PATTERN_DEFINITIONS,
    )
    user_message = build_editor_user_message(parsed_output, transcript_turns)

    response: OpenAIResponse = call_llm(
        system_prompt=system_prompt,
        developer_message="",  # No taxonomy for the editor
        user_message=user_message,
        model=model,
    )

    return response.parsed, response.prompt_tokens, response.completion_tokens


# -- Merge logic ---------------------------------------------------------------

def merge_editor_output(
    original: dict,
    editor_output: dict,
) -> tuple[dict, list[dict]]:
    """Merge the editor's delta output into the original analysis.

    Processing order (critical for correctness):
    1. OE removals -> score recalculation -> status updates
    2. Coaching discard for patterns demoted to insufficient_signal
    3. Apply coaching text edits (pattern_coaching_edits)
    4. Apply span reference changes with validation
    5. Apply top-level text edits

    Args:
        original: The full analysis output from the 1st call (post-patches).
        editor_output: The editor's delta output.

    Returns:
        (merged_output, changelog) where changelog is the editor's changes array.
    """
    merged = copy.deepcopy(original)
    changelog = editor_output.get("changes", [])

    # If no edits at all, return early
    if not editor_output or changelog == []:
        has_any_edit = any(
            k in editor_output
            for k in (
                "executive_summary", "coaching_themes", "strengths_edits",
                "focus_message", "micro_experiment_edits",
                "pattern_coaching_edits", "experiment_coaching_edits",
                "oe_removals",
            )
        )
        if not has_any_edit:
            return merged, changelog

    # -- Step 1: OE removals ---------------------------------------------------
    demoted_patterns: set[str] = set()
    oe_removals = editor_output.get("oe_removals", [])
    if oe_removals:
        demoted_patterns = _process_oe_removals(merged, oe_removals)

    # -- Step 2: Coaching discard for demoted patterns -------------------------
    if demoted_patterns:
        _discard_coaching_for_demoted(merged, demoted_patterns)

    # -- Step 3: Apply pattern coaching text edits -----------------------------
    pc_edits = editor_output.get("pattern_coaching_edits", {})
    if pc_edits:
        _apply_pattern_coaching_edits(merged, pc_edits, demoted_patterns)

    # -- Step 4: Apply span reference changes with validation ------------------
    if pc_edits:
        _validate_span_references(merged, pc_edits, original)

    # -- Step 5: Apply top-level text edits ------------------------------------
    _apply_toplevel_edits(merged, editor_output)

    return merged, changelog


# -- OE removal processing ----------------------------------------------------

def _process_oe_removals(
    merged: dict,
    oe_removals: list[dict],
) -> set[str]:
    """Remove flagged OEs, recalculate scores, update statuses.

    Returns the set of pattern_ids that were demoted to insufficient_signal.
    """
    # Group removals by pattern_id
    removals_by_pattern: dict[str, list[int]] = {}
    for removal in oe_removals:
        pid = removal.get("pattern_id")
        idx = removal.get("oe_index")
        if pid is not None and idx is not None:
            removals_by_pattern.setdefault(pid, []).append(idx)

    if not removals_by_pattern:
        return set()

    # Build OE list by pattern for removal
    oe_list = merged.get("opportunity_events", [])

    # Group OEs by pattern_id with their original indices
    oes_by_pattern: dict[str, list[tuple[int, dict]]] = {}
    for i, oe in enumerate(oe_list):
        pid = oe.get("pattern_id")
        if pid:
            oes_by_pattern.setdefault(pid, []).append((i, oe))

    # Collect global indices to remove
    indices_to_remove: set[int] = set()
    for pid, removal_indices in removals_by_pattern.items():
        pattern_oes = oes_by_pattern.get(pid, [])
        for local_idx in removal_indices:
            if 0 <= local_idx < len(pattern_oes):
                global_idx, _ = pattern_oes[local_idx]
                indices_to_remove.add(global_idx)
            else:
                logger.warning(
                    "Editor OE removal: invalid index %d for pattern %s (has %d OEs)",
                    local_idx, pid, len(pattern_oes),
                )

    # Remove OEs from the list (reverse order to preserve indices)
    for idx in sorted(indices_to_remove, reverse=True):
        if idx < len(oe_list):
            oe_list.pop(idx)

    # Recalculate scores for affected patterns
    demoted: set[str] = set()
    for pid in removals_by_pattern:
        _recalculate_pattern_score(merged, pid, demoted)

    return demoted


def _recalculate_pattern_score(
    merged: dict,
    pattern_id: str,
    demoted: set[str],
) -> None:
    """Recalculate a pattern's score from remaining counted OEs."""
    # Find remaining counted OEs for this pattern
    oe_list = merged.get("opportunity_events", [])
    counted_oes = [
        oe for oe in oe_list
        if oe.get("pattern_id") == pattern_id
        and oe.get("count_decision") == "counted"
    ]

    # Find the pattern snapshot entry
    snap = None
    for ps in merged.get("pattern_snapshot", []):
        if ps.get("pattern_id") == pattern_id:
            snap = ps
            break

    if snap is None:
        logger.warning("Editor: no pattern_snapshot entry for %s", pattern_id)
        return

    # Update opportunity count
    snap["opportunity_count"] = len(counted_oes)

    # Check minimum threshold
    min_threshold = snap.get("min_required_threshold")
    if min_threshold is not None and len(counted_oes) < min_threshold:
        snap["evaluable_status"] = "insufficient_signal"
        snap["score"] = None
        demoted.add(pattern_id)
        logger.info(
            "Editor: pattern %s demoted to insufficient_signal "
            "(%d counted OEs < min threshold %s)",
            pattern_id, len(counted_oes), min_threshold,
        )
        return

    if len(counted_oes) == 0:
        snap["evaluable_status"] = "insufficient_signal"
        snap["score"] = None
        demoted.add(pattern_id)
        logger.info("Editor: pattern %s demoted -- 0 counted OEs remain", pattern_id)
        return

    # Recalculate score: sum of success values / count
    total = sum(oe.get("success", 0) for oe in counted_oes)
    snap["score"] = round(total / len(counted_oes), 4)

    logger.info(
        "Editor: pattern %s recalculated -- %d counted OEs, score %.4f",
        pattern_id, len(counted_oes), snap["score"],
    )


def _discard_coaching_for_demoted(
    merged: dict,
    demoted_patterns: set[str],
) -> None:
    """Null out all coaching fields for patterns demoted to insufficient_signal."""
    coaching = merged.get("coaching", {})
    for pc in coaching.get("pattern_coaching", []):
        if pc.get("pattern_id") in demoted_patterns:
            pc["coaching_note"] = None
            pc["suggested_rewrite"] = None
            pc["rewrite_for_span_id"] = None
            pc["best_success_span_id"] = None
            pc["notes"] = None
            logger.info(
                "Editor: discarded coaching for demoted pattern %s",
                pc.get("pattern_id"),
            )


# -- Pattern coaching edits ----------------------------------------------------

def _apply_pattern_coaching_edits(
    merged: dict,
    pc_edits: dict[str, dict],
    demoted_patterns: set[str],
) -> None:
    """Apply the editor's delta edits to pattern_coaching entries."""
    coaching = merged.get("coaching", {})
    pc_list = coaching.get("pattern_coaching", [])

    # Build lookup by pattern_id
    pc_by_id = {pc.get("pattern_id"): pc for pc in pc_list}

    for pid, edits in pc_edits.items():
        if pid in demoted_patterns:
            logger.info(
                "Editor: skipping edits for demoted pattern %s", pid,
            )
            continue

        pc = pc_by_id.get(pid)
        if pc is None:
            logger.warning(
                "Editor: pattern_coaching_edits references unknown pattern %s", pid,
            )
            continue

        # Handle notes suppression (independent of coaching_note)
        if edits.get("notes") == "SUPPRESS":
            pc["notes"] = None

        # Handle coaching_note suppression
        if edits.get("coaching_note") == "SUPPRESS":
            pc["coaching_note"] = None
            pc["suggested_rewrite"] = None
            pc["rewrite_for_span_id"] = None
            # If notes wasn't also suppressed above, it keeps its value
            if edits.get("notes") != "SUPPRESS":
                # Apply notes rewrite if provided (non-SUPPRESS, non-null)
                if "notes" in edits and edits["notes"] is not None:
                    pc["notes"] = edits["notes"]
            continue

        # Apply non-null, non-SUPPRESS field edits
        for field in ("notes", "coaching_note", "suggested_rewrite",
                       "rewrite_for_span_id", "best_success_span_id"):
            if field in edits and edits[field] is not None and edits[field] != "SUPPRESS":
                pc[field] = edits[field]


def _validate_span_references(
    merged: dict,
    pc_edits: dict[str, dict],
    original: dict,
) -> None:
    """Validate span reference changes and revert invalid ones."""
    coaching = merged.get("coaching", {})
    pc_list = coaching.get("pattern_coaching", [])
    pc_by_id = {pc.get("pattern_id"): pc for pc in pc_list}

    # Build original lookup for revert
    orig_coaching = original.get("coaching", {})
    orig_pc_by_id = {
        pc.get("pattern_id"): pc
        for pc in orig_coaching.get("pattern_coaching", [])
    }

    # Build span lookup by pattern from pattern_snapshot
    snap_by_id: dict[str, dict] = {}
    for ps in merged.get("pattern_snapshot", []):
        pid = ps.get("pattern_id")
        if pid:
            snap_by_id[pid] = ps

    for pid, edits in pc_edits.items():
        pc = pc_by_id.get(pid)
        orig_pc = orig_pc_by_id.get(pid)
        snap = snap_by_id.get(pid)
        if not pc or not orig_pc or not snap:
            continue

        # Validate best_success_span_id
        if "best_success_span_id" in edits and edits["best_success_span_id"] is not None:
            success_spans = snap.get("success_evidence_span_ids", [])
            if pc.get("best_success_span_id") not in success_spans:
                logger.warning(
                    "Editor: best_success_span_id '%s' not in success spans for %s -- reverting",
                    pc.get("best_success_span_id"), pid,
                )
                pc["best_success_span_id"] = orig_pc.get("best_success_span_id")

        # Validate rewrite_for_span_id
        if "rewrite_for_span_id" in edits and edits["rewrite_for_span_id"] is not None:
            evidence_spans = snap.get("evidence_span_ids", [])
            success_spans = snap.get("success_evidence_span_ids", [])
            non_success_spans = [s for s in evidence_spans if s not in success_spans]

            new_rewrite_span = pc.get("rewrite_for_span_id")
            if new_rewrite_span not in non_success_spans:
                logger.warning(
                    "Editor: rewrite_for_span_id '%s' not valid for %s -- reverting",
                    new_rewrite_span, pid,
                )
                pc["rewrite_for_span_id"] = orig_pc.get("rewrite_for_span_id")
                pc["suggested_rewrite"] = orig_pc.get("suggested_rewrite")
            else:
                # Check if span changed but suggested_rewrite didn't
                orig_rewrite_span = orig_pc.get("rewrite_for_span_id")
                if new_rewrite_span != orig_rewrite_span:
                    orig_rewrite_text = orig_pc.get("suggested_rewrite")
                    new_rewrite_text = pc.get("suggested_rewrite")
                    if new_rewrite_text == orig_rewrite_text:
                        logger.warning(
                            "Editor: rewrite_for_span_id changed for %s but "
                            "suggested_rewrite unchanged -- reverting both",
                            pid,
                        )
                        pc["rewrite_for_span_id"] = orig_rewrite_span
                        pc["suggested_rewrite"] = orig_rewrite_text


# -- Top-level text edits ------------------------------------------------------

def _apply_toplevel_edits(merged: dict, editor_output: dict) -> None:
    """Apply top-level text edits from the editor delta."""
    coaching = merged.get("coaching", {})

    # Executive summary
    if "executive_summary" in editor_output and editor_output["executive_summary"] is not None:
        coaching["executive_summary"] = editor_output["executive_summary"]

    # Coaching themes
    if "coaching_themes" in editor_output and editor_output["coaching_themes"] is not None:
        coaching["coaching_themes"] = editor_output["coaching_themes"]

    # Strengths edits (message text only, pattern_id preserved)
    strengths_edits = editor_output.get("strengths_edits", {})
    if strengths_edits:
        for strength in coaching.get("strengths", []):
            pid = strength.get("pattern_id")
            if pid in strengths_edits:
                edit = strengths_edits[pid]
                if isinstance(edit, dict) and "message" in edit and edit["message"] is not None:
                    strength["message"] = edit["message"]

    # Focus message (text only, structure preserved)
    if "focus_message" in editor_output and editor_output["focus_message"] is not None:
        focus_items = coaching.get("focus", [])
        if focus_items:
            focus_items[0]["message"] = editor_output["focus_message"]

    # Micro-experiment text edits (text fields only)
    me_edits = editor_output.get("micro_experiment_edits", {})
    if me_edits:
        me_items = coaching.get("micro_experiment", [])
        if me_items:
            me = me_items[0]
            for field in ("title", "instruction", "success_marker"):
                if field in me_edits and me_edits[field] is not None:
                    me[field] = me_edits[field]

    # Experiment coaching edits
    ec_edits = editor_output.get("experiment_coaching_edits", {})
    if ec_edits:
        exp_coaching = coaching.get("experiment_coaching")
        if exp_coaching and isinstance(exp_coaching, dict):
            for field in ("coaching_note", "suggested_rewrite", "rewrite_for_span_id"):
                if field in ec_edits and ec_edits[field] is not None:
                    exp_coaching[field] = ec_edits[field]
