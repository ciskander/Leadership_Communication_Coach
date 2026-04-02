# Prompt: Generate Follow-Up Meeting Transcript (Post-Coaching)

## Instructions

You are generating a realistic meeting transcript for a leader who has received coaching feedback and been given a specific behavioral experiment to try. This meeting takes place AFTER the coaching session — the leader is aware of the feedback and is consciously (but imperfectly) working on it.

The transcript must feel natural. Real behavioral change is gradual and inconsistent:
- The leader might attempt the experiment behavior in one moment but forget it in the next
- Under pressure, they'll likely revert to old habits
- Early attempts at new behavior often feel awkward or forced — the person is thinking about it consciously, which can make them hesitate or over-correct
- Improvement is not linear — some meetings will show more progress than others

## Persona

{{PASTE PERSONA HERE}}

## Coaching Context from Prior Analysis

{{PASTE THE FOLLOWING FROM THE MOST RECENT ANALYSIS OUTPUT, using this format:}}

```
EXECUTIVE SUMMARY:
[Copy coaching.executive_summary verbatim]

COACHING THEMES:
[For each theme in coaching.coaching_themes, copy:]
- [primary/secondary]: "[theme]" — [explanation]

ACTIVE EXPERIMENT:
- Title: [experiment title]
- Instruction: [experiment instruction]
- Success marker: [experiment success_marker]

EXPERIMENT DETECTION (from most recent meeting):
- Attempt: [yes/partial/no, or "N/A" if this is the first post-baseline meeting]
- Count: [count_attempts, or "N/A"]
- Coaching note: [coaching.experiment_coaching.coaching_note, or "none"]

NOTABLE PATTERN COACHING (include only the 2-3 most insightful, skip generic ones):
- [pattern name]: "[coaching_note text]"
- [pattern name]: "[coaching_note text]"
```

Tip: the executive summary, coaching themes, and experiment details are in the `coaching` section of the analysis JSON. Experiment detection is in `experiment_tracking.detection_in_this_meeting`. Pattern coaching notes are in `coaching.pattern_coaching` — skim these and include only the ones that say something specific and interesting about this leader, not generic observations.

## Story So Far

{{PROVIDE A BRIEF RUNNING NARRATIVE OF THE COACHING ARC:}}

Describe in a short paragraph where this person is in their coaching journey. Include:
- This will be meeting N of the series (the 3 baseline meetings are meetings 1-3; follow-ups start at meeting 4)
- How many meetings the leader has been working on the current experiment
- A 1-2 sentence summary of how the experiment has been going (e.g., "first attempt was rocky, second meeting showed some progress on the behavior but only in low-stakes moments")
- What the business context has been recently (so the LLM can evolve it naturally)

Example:
> "This is meeting 5. Nadia has been working on the experiment 'Pause and name the disagreement before responding' for 2 meetings. In her first attempt, she tried it once during a low-stakes update but reverted when a peer challenged her resource proposal. The coaching noted she's making progress recognizing moments where the behavior applies. The team is now shifting from launch planning into post-launch support, and there's a new contractor joining the project."

## Your Task

Based on the persona, the coaching context, and the story so far, generate the next meeting transcript. You decide:

1. **What kind of meeting this is** — choose a meeting type and role (chair, manager in a 1:1, or participant) that fits naturally in the persona's work life at this point in the arc. Vary the meeting types across the series.

2. **What happens with the experiment** — based on where the leader is in their journey, decide how the experiment behavior shows up (or doesn't) in this meeting. Be realistic: early attempts are inconsistent, progress is gradual, setbacks happen, and eventually the behavior starts to feel more natural. Tell me what you decided in a brief note before the transcript.

   **Experiment transitions:** If the coaching context shows a NEW experiment (different title/instruction from the previous round), this means the coaching system completed the old experiment and proposed a new one. In this case: the old experiment behavior should now be fairly natural and ingrained (it doesn't disappear — it becomes part of who this person is). The new experiment is just starting, so early attempts should feel awkward and inconsistent, just like the first experiment did at the beginning.

3. **What business content drives the meeting** — create a concrete agenda that evolves naturally from the persona's work context and the story so far.

### How the Leader's Other Behaviors Should Evolve
The persona has multiple communication strengths and weaknesses. The experiment targets only one area. For everything else:
- **Strengths should persist** — these are ingrained habits that don't change
- **Non-experiment weaknesses should remain roughly stable.** The leader hasn't received specific coaching on these, so they shouldn't magically improve. They may even be slightly more visible in meetings where the leader is spending cognitive effort on the experiment behavior — there's a limited attention budget for conscious behavior change.
- **Neutral habits persist** — these add texture and consistency

## Requirements

### Format
Plain text with speaker labels:
```
Speaker Name: What they said.
```

No timestamps, turn numbers, or metadata.

### Participants
Reuse recurring colleagues from the persona for continuity. Add new participants when the business context calls for it (a new stakeholder, someone from another team). For group meetings, 4-6 people. For 1:1s, 2 people.

### Length
Let the meeting's natural rhythm determine length. Rough guidance: 80-150 turns for group meetings, 50-100 turns for 1:1s. Not a hard constraint.

### Behavioral Requirements
- The persona's core strengths should STILL be visible — coaching doesn't change everything, and strengths persist
- The experiment behavior should emerge from the natural flow of conversation — not as a separate, highlighted moment
- Include at least one moment where the old behavior pattern reasserts itself, even in meetings where the leader is making progress
- Other participants should react naturally to any changes in the leader's behavior — they might not notice subtle shifts, or they might respond positively to better facilitation without commenting on it explicitly
- Show the persona's neutral habits and interpersonal dynamics as well — these add texture and shouldn't change

### Realism Guidelines
- Same standards as the baseline: natural meeting dynamics, varied turn lengths, filler, tangents, etc.
- If the leader is attempting a new behavior, it should sometimes feel slightly out of character — they're trying something new and it's not fully natural yet
- The meeting should have its own substantive agenda and business content — it's a real meeting, not a coaching exercise
- Evolve the business context over time. New projects start, old ones conclude, team dynamics shift. This creates fresh conversational contexts for the persona's patterns to manifest.

### Transcript Quality
These transcripts must read like verbatim transcriptions of real meetings, not like a screenplay or a summary of a meeting.

- **Do NOT summarize.** Each topic should unfold across many turns with back-and-forth, clarifying questions, and incremental contributions. If a topic takes 30 seconds in a real meeting, it should take 5-10 turns in the transcript, not 2 tidy paragraphs.
- **Do NOT structure dialogue as bullet points or lists.** No one speaks in formatted lists.
- **Use realistic pacing.** Real meetings spend extended stretches on a single topic. Resist the urge to advance to a new topic every few turns.
- **People don't speak in perfect paragraphs.** Include false starts, self-corrections, and sentences that change direction.
- **Not every topic gets resolved.** Some things get tabled, deferred, or dropped.
- **Adjacent turns should connect.** Each person's response should build on, react to, or redirect what was just said.
- **Output only the transcript** (plus the meeting design note and updated story so far). No summaries or commentary within the dialogue itself.

### What NOT to Do
- Do NOT have the leader explicitly mention coaching, experiments, or that they're "trying something new"
- Do NOT make the experiment attempt feel theatrical or staged
- Do NOT have other participants comment on the leader's behavior change
- Do NOT write stage directions or narrator commentary
- The improvement (or lack thereof) should be visible to a careful observer reviewing the transcript, but not announced

## Output

Provide three things in order:

1. **Meeting Design Note** (2-4 sentences): What kind of meeting you chose, what happens with the experiment, and why.

2. **The transcript itself.**

3. **Updated Story So Far**: An updated version of the "Story So Far" paragraph that incorporates this meeting. This should be ready to paste directly into the next round's prompt — include the meeting number, what happened with the experiment, and how the business context evolved. Do NOT include the coaching system's analysis (that hasn't happened yet when this is pasted into the next prompt — the user will add the coaching output separately).

```
MEETING DESIGN NOTE:
[Your decisions about meeting type, experiment progression, and rationale]

=== MEETING [N]: [Brief descriptive title] ===
Role: [Chair / Manager (1:1) / Participant]
Participants: [Name (role), Name (role), ...]

[transcript]

UPDATED STORY SO FAR (paste into next prompt):
[Updated narrative paragraph incorporating this meeting]
```
