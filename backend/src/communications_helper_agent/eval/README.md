# Prompt evaluation harness

Measures how well the summarization prompt (phase 1) turns a raw meeting
transcript into a summary that preserves every actionable subtask.

Downstream, those subtasks become GitHub issues. A dropped task is a task that
never gets built, so recall is the metric that matters most.

## The three stages

```
generate_dataset.py  ->  dataset/*.json     write the test cases (once, offline)
run_eval.py          ->  results.jsonl      run the prompt, grade each output
check_judge.py       ->  pass/fail          prove the judge works before paying
```

## Case format

Each file in `dataset/` is one case, in the shape you specified:

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

`solution_criteria` holds **checkable claims**, not one golden summary. Two
correct summaries can be worded completely differently, so grading against a
single reference would punish valid phrasing. Criteria are what a judge can
grade reliably.

`must_not_contain` is the hallucination trap: things raised and *rejected* in
the meeting. A system that lists a rejected proposal as a task has failed, and
this field is what catches it.

## Difficulty mix

Ten cases, spanning what the system will actually see:

| tier    | n | what it tests |
|---------|---|---------------|
| `clean` | 3 | tasks stated plainly with owners -- must score ~100%; catches outright breakage |
| `messy` | 4 | tasks buried in tangents, some owners unstated |
| `hard`  | 2 | tasks *implied*, never stated imperatively; interrupted speakers |
| `edge`  | 1 | a real meeting with **zero** tasks |

The `edge` case is the most important single case in the set. It is the only one
that catches a system inventing work to look useful -- a system that
pattern-matches "meeting -> task list" fails exactly there and nowhere else.

## Metrics

Four independent scores rather than one blended number. A blended score can't
tell you whether a regression was dropped tasks or invented ones, and those have
different fixes.

| metric | question |
|--------|----------|
| `task_recall` | of the real tasks, how many did it find? **(headline)** |
| `task_precision` | of the tasks it listed, how many were real? |
| `faithfulness` | did it avoid asserting things that were never agreed? |
| `coverage` | did it preserve the key decisions? |

Matching is by meaning, not string equality -- "set up CI" and "configure the
build pipeline" are the same task. That fuzzy match is why the judge is a model
rather than a set comparison.

## Running it

```bash
cd backend

# 1. generate the dataset (once) -- costs real money, uses claude-opus-5
uv run python -m communications_helper_agent.eval.generate_dataset

# 2. READ THE CASES. Confirm required_tasks are right.
#    A mislabelled case silently scores a correct system wrong.

# 3. prove the judge works before paying for a full run
uv run python -m communications_helper_agent.eval.check_judge

# 4. run the eval
uv run python -m communications_helper_agent.eval.run_eval --reps 2
```

Results land in `backend/.claude/hillclimb/summarize/baseline/`. To compare a
revised prompt, edit `prompts/summarize.md` and run with `--variant v1`.

### Report

```bash
R="<claude-api skill base dir>/shared/evals/report"
B="$R/build-report.mjs"; [ -f "$B" ] || B="$R/build-report-lite.mjs"
node "$B" backend/.claude/hillclimb/summarize/
```

## Prompts

| file | owner | purpose |
|------|-------|---------|
| `dataset_generation.md` | eval | writes the test cases |
| `summarize.md` | **partner** | the prompt under test -- placeholder |
| `judge.md` | eval | grades a summary against its criteria |

`summarize.md` is deliberately minimal. Everything below its marker line is the
system prompt; keep the `{transcript}` placeholder, since the runner formats
against it.

## Why the judge is a different model

`config.py` runs the summarizer on `claude-opus-5` and the judge on
`claude-sonnet-5`. A judge from the same model as the system under test tends to
prefer outputs resembling its own, which would inflate every score.

## Things that will bite you

**Generated cases are a starting point, not ground truth.** The generator writes
both the transcript and its labels, so a label error is invisible until it
depresses a score you then chase. `generate_dataset.py` checks structure --
evidence quotes must appear verbatim, edge cases must have zero tasks, non-edge
cases must have a hallucination trap -- but it cannot check whether the labels
are *right*. Only reading them does that.

**Two reps is a thin signal.** Noise on a 10-case set is roughly ±0.15 on a
0-1 metric. Treat differences smaller than that as noise, not improvement. If
you need to detect a smaller change, raise `--reps` or add cases.

**Judge cost is real.** Every case costs a summarizer call plus a judge call.
`results.jsonl` records `judge_model` and `judge_usage` separately so judge spend
stays visible rather than hiding inside the total.
