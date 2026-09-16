# Summarization prompt (PLACEHOLDER -- owned by partner)

The production prompt under test. Left intentionally blank: this is the artifact
being evaluated, not part of the eval harness.

The runner reads this file and substitutes `{transcript}`. Anything you write
below the marker becomes the system prompt.

Keep the `{transcript}` placeholder -- the runner formats against it.

--- SYSTEM PROMPT BELOW THIS LINE ---

You are a meeting summarization assistant.

Summarize the following meeting transcript. Preserve every actionable subtask
that was discussed.

<transcript>
{transcript}
</transcript>
