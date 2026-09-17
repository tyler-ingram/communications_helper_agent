# Prompt evaluation harness

Measures how well `MEETING_TO_ISSUES_PROMPT` (in `llm/system_prompts.py`) turns
a raw meeting transcript into a JSON array of proposed GitHub issues.

A missed item is work that never gets tracked; an invented one wastes a
reviewer's time. Recall is the headline metric, with precision beside it so a
system cannot win by proposing everything.

**The eval runs the real pipeline.** It calls `llm.service.ask()` with the
prompt read from `llm/system_prompts.py` — the same entry point and the same
local model (LM Studio, `qwen/qwen3-4b-2507`) that production uses. Nothing is
reconstructed here, so the prompt cannot drift out from under the eval. Only
the judge calls the Claude API.

## The three stages

```
generate_dataset.py  ->  dataset/*.json     write the test cases (once, offline)
check_judge.py       ->  pass/fail          prove the judge works before paying
run_eval.py          ->  results.jsonl      run the pipeline, grade each output
```

`generate_dataset.py` and `check_judge.py` call the Claude API and cost money.
`run_eval.py` runs the pipeline locally and free; only its judge half is paid.

## Case format

Each file in `dataset/` is one case:

```json
{
  "id": "sprint-planning-auth-rewrite",
  "difficulty": "messy",
  "data": "Priya: okay so before we get into it...",
  "solution_criteria": {
    "required_tasks": [
      {
        "task": "Write the migration script for the user table",
        "owner": "Ana",
        "evidence": "Ana: I can take the migration script, probably Thursday."
      }
    ],
    "must_mention": ["The team agreed to postpone the Redis cache"],
    "must_not_contain": ["Add a Redis caching layer"],
    "notes": "The migration task is mentioned once, mid-tangent."
  }
}
```

`solution_criteria` holds **checkable claims**, not one golden output. Two
correct issue lists can be worded completely differently, so grading against a
single reference would punish valid phrasing.

`must_not_contain` is the hallucination trap: things raised and *rejected* in
the meeting. A system that files a rejected proposal as an issue has failed,
and this field is what catches it.

`evidence` must be a verbatim transcript quote. The system under test must also
quote the transcript in each issue's `source_excerpt`, and the harness verifies
those quotes really appear — so verbatim evidence keeps both sides honest.

## Difficulty mix

Ten cases, spanning what the system will actually see:

| tier    | n | what it tests |
|---------|---|---------------|
| `clean` | 3 | items stated plainly with owners — must score ~100%; catches outright breakage |
| `messy` | 4 | items buried in tangents, some owners unstated |
| `hard`  | 2 | items *implied*, never stated imperatively; interrupted speakers |
| `edge`  | 1 | a real meeting with **zero** actionable items |

The `edge` case is the most important single case in the set. It is the only
one that catches a system inventing work to look useful — a system that
pattern-matches "meeting -> issue list" fails exactly there and nowhere else.
Its correct output is an empty JSON array.

## Metrics

Seven independent scores rather than one blended number: a recall drop (missed
issues) and a precision drop (invented issues) have different fixes, and a
single number would hide which one moved.

**Graded by the judge** — these need fuzzy matching, since "fix slow search"
and "search performance issue" are the same item:

| metric | question |
|--------|----------|
| `issue_recall` | of the real items, how many became issues? **(headline)** |
| `issue_precision` | of the issues proposed, how many were real? |
| `faithfulness` | do descriptions stay within what the transcript supports? |

**Graded by code** (`graders.py`) — free, instant, no judge noise:

| metric | question |
|--------|----------|
| `schema_valid` | every issue carries exactly the required fields |
| `fields_valid` | `type` in the enum, `priority` 1-5, `status == "proposed"`, <=4 tags |
| `excerpt_grounded` | does each `source_excerpt` really appear in the transcript? |
| `assignee_safe` | is every assignee a real speaker, and is confidence consistent? |

`excerpt_grounded` is the one that earns its keep. The prompt requires every
issue to quote its justification, so a fabricated issue usually needs a
fabricated quote — and a fabricated quote fails a plain string search. That
catches hallucination for free, without a model call.

Anything checkable without judgment belongs in `graders.py`, not `judge.md`. A
model call to verify `1 <= priority <= 5` is wasted money and adds noise to a
deterministic answer.

## Running it

```bash
cd backend

# 1. generate the dataset (once) -- costs money, uses claude-opus-5
uv run python -m communications_helper_agent.eval.generate_dataset

# 2. READ THE CASES. Confirm required_tasks are right.
#    A mislabelled case silently scores a correct system wrong.

# 3. prove the judge works before paying for a full run
uv run python -m communications_helper_agent.eval.check_judge

# 4. run the eval -- needs LM Studio running with the model loaded
uv run python -m communications_helper_agent.eval.run_eval --reps 2
```

Results land in `backend/.claude/hillclimb/meeting_to_issues/baseline/`.

To compare a revised prompt: edit `MEETING_TO_ISSUES_PROMPT` in
`llm/system_prompts.py`, then run with `--variant v1`. Both runs land side by
side and the report shows the delta per metric.

To compare models instead, pass `--model` with any key LM Studio has loaded.

### Report

```bash
R="<claude-api skill base dir>/shared/evals/report"
B="$R/build-report.mjs"; [ -f "$B" ] || B="$R/build-report-lite.mjs"
node "$B" backend/.claude/hillclimb/meeting_to_issues/
```

## Prompts

| file | owner | purpose |
|------|-------|---------|
| `llm/system_prompts.py` | **partner** | the prompt under test — read live, not copied |
| `prompts/dataset_generation.md` | eval | writes the test cases |
| `prompts/judge.md` | eval | grades the fuzzy half |

The prompt under test deliberately lives in the app, not here. `config.py`
imports it, so an edit to `system_prompts.py` is picked up by the next eval run
with no sync step — the eval can never measure a stale copy.

## Models

| role | model | cost |
|------|-------|------|
| pipeline (under test) | LM Studio, `$LM_MODEL` | free, local |
| dataset generator | `claude-opus-5` | paid, once |
| judge | `claude-sonnet-5` | paid, per case |

The pipeline model matches production, so the numbers transfer. The judge is
deliberately a different family from the system under test — a judge sharing a
model with the thing it grades prefers outputs resembling its own.

## Things that will bite you

**Generated cases are a starting point, not ground truth.** The generator
writes both the transcript and its labels, so a label error is invisible until
it depresses a score you then chase. `generate_dataset.py` checks structure —
evidence quotes must appear verbatim, edge cases must have zero items, non-edge
cases must have a hallucination trap — but it cannot check whether the labels
are *right*. Only reading them does that.

**Two reps is a thin signal.** Noise on a 10-case set is roughly ±0.15 on a
0-1 metric. Treat differences smaller than that as noise, not improvement. If
you need to detect a smaller change, raise `--reps` or add cases.

**LM Studio must be running** with the model loaded before `run_eval`. If it
is not, every case lands in `errors.jsonl` as `harness_error` rather than
scoring 0 — which is the point of the sidecar, but check there first if a run
comes back empty.

**A small local model may not hold the format.** `qwen3-4b` is being asked for
a 10-field JSON array with a reasoning preamble. If `schema_valid` or
`fields_valid` comes back low while `issue_recall` is decent, the prompt is
finding the right work but losing the format — a different problem than missing
items, which is exactly why those are separate metrics.

**Judge cost is real, the pipeline is free.** Every case still costs one judge
call. `results.jsonl` records `judge_model` and `judge_usage` separately so
that spend stays visible.
