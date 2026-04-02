# Prompt: Generate Baseline Meeting Transcripts

## Instructions

You are generating 3 realistic meeting transcripts for a leadership communication coaching evaluation. These 3 meetings form the coachee's **baseline** — the initial assessment of their communication patterns before any coaching intervention.

The transcripts must be internally consistent with the persona provided below, and they must feel like real meetings — not scripted demonstrations of good or bad behavior. Real meetings are messy: people interrupt, go on tangents, make small talk, revisit earlier points, and sometimes say things imperfectly even when their intent is sound.

## Persona

{{PASTE PERSONA HERE}}

## Requirements for Each Transcript

### Format
Use plain text with speaker labels. Each line should be:
```
Speaker Name: What they said in this turn.
```

Do NOT include timestamps, turn numbers, or any metadata. Just speaker labels and dialogue.

### Meeting Structure
Generate 3 different meetings. Vary the meeting types and the coachee's role:
1. **Meeting 1**: A meeting the coachee **chairs** (e.g., cross-functional team sync, standup, sprint review). 4-6 participants.
2. **Meeting 2**: A meeting the coachee **chairs** with a different dynamic (e.g., strategy discussion, planning session, decision-making meeting). 3-5 participants.
3. **Meeting 3**: A **1:1 meeting** where the coachee is the **manager** (with one of the recurring colleagues who reports to them). 2 participants.

Each meeting should have a concrete business agenda drawn from the persona's work context — specific projects, decisions, or problems to discuss. Do not create generic "placeholder" meetings.

### Participants
- Use the recurring colleagues defined in the persona. They should behave consistently with their described personalities and communication styles.
- Add 1-2 additional participants per meeting who are specific to that meeting's context (a subject matter expert, someone from another team, etc.). Give them a name and enough personality to feel real.
- Participants should have distinct voices — vary talkativeness, assertiveness, detail orientation, and how they interact with the coachee.

### Behavioral Consistency
The coachee's communication strengths and weaknesses should show up as a clear pattern across the 3 meetings, but distribution should be **natural, not quota-driven**. Some meetings will create more opportunities for certain behaviors than others:

- A meeting with a contentious decision will naturally surface how the coachee handles disagreement; a routine standup may not
- A planning meeting may showcase framing ability; a 1:1 will surface different behaviors than a group meeting
- Let the meeting agenda and dynamics create the opportunities — don't force a fixed number of strength/weakness moments per transcript

The key principle: if a coach watched all 3 meetings, they should be able to identify the persona's strengths and weaknesses without being told what to look for. But any single meeting alone might show only some of the picture.

Additional guidelines:
- Strengths should feel effortless — the coachee does these things without thinking about them
- Weaknesses should be subtle enough that the coachee might not notice them, but clear enough for a careful observer
- Include moments that are ambiguous or mixed — real communication is rarely purely good or purely bad
- The coachee's neutral habits should also appear — things they do that aren't particularly notable but add texture
- Show how the coachee's communication shifts depending on who they're talking to (per the interpersonal dynamics in the persona)
- Other participants should react naturally to the coachee's behavior (e.g., if the coachee moves on too quickly, someone might circle back to the topic later; if the coachee asks a sharp question, someone might visibly reconsider their position)

### Realism Guidelines
- Include natural meeting dynamics: brief small talk at the start, occasional tangents, someone joining a minute late, a technical issue, someone needing to leave early, etc.
- Not every turn needs to be substantive — include filler ("Got it", "Makes sense", "Let me pull that up", "Sorry, go ahead")
- Vary turn length realistically — some turns are a sentence, some are a paragraph
- Include at least one moment per meeting where things don't go smoothly (a disagreement, a confusing explanation, a missed deadline discussion, an uncomfortable pause, etc.)
- In meetings the coachee chairs, they should talk more than any individual participant but should not dominate — other participants should contribute meaningfully
- In the 1:1 (Meeting 3), the dynamic is different — the coachee has more space to listen, ask questions, and give feedback without managing a group. This is where interpersonal dynamics with that specific person should be most visible

### Transcript Quality
These transcripts must read like verbatim transcriptions of real meetings, not like a screenplay or a summary of a meeting.

- **Do NOT summarize.** Each topic should unfold across many turns with back-and-forth, clarifying questions, and incremental contributions. If a topic takes 30 seconds in a real meeting, it should take 5-10 turns in the transcript, not 2 tidy paragraphs.
- **Do NOT structure dialogue as bullet points or lists.** No one speaks in formatted lists. People say "so there's the timeline issue, and then there's the resourcing question, and honestly I'm also a little worried about..." — not "First, timeline. Second, resourcing. Third, risk."
- **Use realistic pacing.** Real meetings spend extended stretches on a single topic. Resist the urge to advance to a new topic every few turns. Some topics take 15-20 turns to work through. Others get resolved quickly.
- **People don't speak in perfect paragraphs.** Include false starts, self-corrections, and sentences that change direction. "I think we should — well, actually, let me back up. The issue isn't really the timeline, it's that we don't have agreement on scope yet."
- **Not every topic gets resolved.** Some things get tabled, deferred, or simply dropped when the meeting runs long or gets derailed.
- **Adjacent turns should connect.** Each person's response should build on, react to, or redirect what was just said. Don't have participants introduce unrelated new topics in sequence — that's a series of monologues, not a conversation.
- **Within each transcript, output only dialogue.** No summaries, explanations, or commentary between speakers. (The "Initial Story So Far" requested after the transcripts is a separate deliverable, not part of the transcripts themselves.)

### What NOT to Do
- Do NOT write stage directions or descriptions of behavior ("[crosses arms]", "[long pause]", "[nods]")
- Do NOT include narrator commentary about what's happening
- Do NOT make the weaknesses cartoonish or the strengths superhuman
- Do NOT have participants explicitly comment on the coachee's communication style
- Do NOT reference coaching, communication patterns, or behavioral frameworks
- Do NOT distribute strengths and weaknesses evenly like a checklist — let the meeting context drive which behaviors surface

### Length
Aim for transcripts that feel like realistic meetings of their type:
- Group meetings (Meetings 1 and 2): roughly 80-150 speaking turns
- 1:1 meeting (Meeting 3): roughly 50-100 speaking turns

These are rough guidelines, not hard constraints. Let the meeting's natural rhythm determine the length. A tense decision-making meeting might run longer; a routine standup might be shorter.

Note: If generating all 3 transcripts in a single response is difficult, it is acceptable to generate them one at a time. Maintain consistency with the persona and recurring participants across all three.

## Output

Return 3 transcripts separated by clear headers, followed by an initial "Story So Far" paragraph:

```
=== MEETING 1: [Brief descriptive title] ===
Role: Chair
Participants: [Name (role), Name (role), ...]

[transcript]

=== MEETING 2: [Brief descriptive title] ===
Role: Chair
Participants: [Name (role), Name (role), ...]

[transcript]

=== MEETING 3: [Brief descriptive title] ===
Role: Manager (1:1)
Participants: [Coachee name], [Direct report name (role)]

[transcript]

INITIAL STORY SO FAR (paste into follow-up prompt):
[A paragraph summarizing the 3 baseline meetings — what kinds of meetings they were, what the key business topics were, and what communication patterns were visible. Do NOT include coaching analysis or experiment information — those don't exist yet at baseline. This should read like: "This is meeting 4. Nadia's baseline consisted of 3 meetings: a cross-functional sync about X, a strategy session about Y, and a 1:1 with Z about... The meetings showed a consistent pattern of..."]
```

---

## Reference for the User (not part of the LLM prompt)

After you run the baseline analysis through the coaching system, you'll need to paste the coaching output into the follow-up prompt (Prompt 3). Here's where to find each field in the analysis JSON:

| What to copy | Where to find it |
|---|---|
| Executive summary | `coaching.executive_summary` |
| Coaching themes | `coaching.coaching_themes` — copy each theme's `theme`, `explanation`, and `priority` |
| Active experiment | The experiment the system proposed — copy `title`, `instruction`, `success_marker` |
| Experiment detection | `N/A` for the first follow-up (no experiment was active during baseline) |
| Notable pattern coaching | Skim `coaching.pattern_coaching` — copy the 2-3 most specific `coaching_note` values |
