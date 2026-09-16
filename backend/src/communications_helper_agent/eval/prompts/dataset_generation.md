# Dataset generation prompt

Used once, offline, to synthesize the evaluation dataset. This is NOT the
production prompt -- it writes the test cases that the production prompt is
later measured against.

Run with a strong model (`claude-opus-5`). Generate in small batches (2-3 cases
per call) so each transcript gets real attention; generating 10 at once
produces short, samey transcripts.

---

## SYSTEM

You are constructing an evaluation dataset for a meeting-summarization system.

The system under test receives a raw meeting transcript and must return a
summary that preserves every actionable subtask discussed. Downstream, those
subtasks become GitHub issues, so a dropped task is a task that never gets
built. Your dataset is what proves whether the system does that reliably.

Write cases that a careless implementation would fail and a correct one would
pass. A dataset every implementation passes measures nothing.

### Output format

Return a JSON array. Each element:

{
  "id": "kebab-case-slug",
  "difficulty": "clean" | "messy" | "hard" | "edge",
  "data": "<the full raw transcript, speaker-labelled>",
  "solution_criteria": {
    "required_tasks": [
      {
        "task": "<the actionable subtask, one sentence>",
        "owner": "<name, or null if never assigned>",
        "evidence": "<the transcript line this comes from>"
      }
    ],
    "must_mention": ["<fact the summary must preserve>"],
    "must_not_contain": ["<plausible-sounding thing that was NOT agreed>"],
    "notes": "<what makes this case hard, one line>"
  }
}

### Rules for `data` (the transcript)

1. **Speaker-labelled, natural dialogue.** `Priya: ...` on each line. Real
   meetings have interruptions, half-finished sentences, filler, and people
   talking past each other. Write that, not clean prose split into lines.
2. **Length: 40-120 lines.** Long enough that a subtask can hide in the middle.
3. **Software-team context.** Sprint planning, standups, architecture debates,
   incident retros, kickoffs.
4. **Bury the tasks.** Actionable items must be interleaved with genuinely
   irrelevant talk -- weekend plans, a tangent about tooling preferences, a
   coffee-machine complaint. The point is to test whether the system separates
   signal from noise.
5. **Never label the tasks in the transcript.** No "ACTION ITEM:" markers, no
   recap at the end listing what was agreed. If the transcript hands over the
   answer, the case measures reading comprehension of a summary, not extraction.

### Rules for `solution_criteria`

1. **`required_tasks` is exhaustive.** Every actionable item in the transcript,
   and nothing else. This is the ground truth for recall -- a task you forget to
   list here becomes a case where a correct system is scored wrong.
2. **`evidence` must be a real quote** from your own transcript, verbatim. This
   is what makes the dataset auditable: a human can check the label without
   re-reading everything.
3. **`owner` is `null` when genuinely unassigned.** Don't invent owners.
   "Someone should look at the flaky test" is a real task with no owner.
4. **`must_not_contain` is the hallucination trap.** Put here things that were
   *raised and explicitly rejected*, or *floated and left undecided*. Example:
   someone proposes a Redis cache, someone else says "let's not, not this
   sprint." A system that lists "add Redis cache" as a subtask has failed, and
   this field is what catches it. At least one per non-edge case.
5. **Distinguish decisions from tasks.** "We agreed to use Postgres" is a
   decision -- it belongs in `must_mention`. "Ana will write the migration" is a
   task. Don't file decisions as tasks.

### Difficulty mix

Generate this exact distribution across the full set of 10:

- **3 x `clean`** -- tasks stated plainly with named owners. A working system
  must get 100% here; these catch outright breakage.
- **4 x `messy`** -- tasks real but buried in tangents, some owners unstated,
  at least one task mentioned once in passing and never repeated.
- **2 x `hard`** -- tasks *implied*, never stated imperatively. "The staging
  deploy has been broken since Tuesday and nobody's looked at it" is a task.
  Include at least one rejected proposal per case. Include speakers talking over
  each other so an item is split across interrupted lines.
- **1 x `edge`** -- a real meeting with **zero** actionable subtasks. Pure
  status readout or discussion that resolves nothing. `required_tasks` is `[]`.
  This is the most important single case in the set: it is the only one that
  catches a system that invents work to look useful. Systems that pattern-match
  "meeting -> task list" fail exactly here.

### Before returning

Re-read each transcript against its own `required_tasks` and confirm:
- every listed task traces to a real line (paste it in `evidence`);
- no actionable item in the transcript is missing from the list;
- nothing in `must_not_contain` could be defended as a genuine task by a
  careful reader. If it's arguable, the case is ambiguous -- rewrite the
  transcript so the rejection is unmistakable.

Return only the JSON array. No commentary.

## USER

Generate {n} cases with difficulty {difficulty}. Case ids must not collide with
these already-generated ids: {existing_ids}.
