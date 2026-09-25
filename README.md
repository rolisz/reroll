# reroll

A local web chat where every reply is sampled n times. A judge model (Haiku by default) compares the samples
and says whether they diverge, and how:

- **consistent**: the replies are interchangeable
- **different next moves**: same reading of you, different (compatible) directions
- **read you differently**: your message was ambiguous; the label suggests what to add
- **contradicting each other**: the replies make incompatible claims, so don't trust that turn

You see a random sample, the same thing a normal chat would give you. The label flags when it's in a minority group.

## Run

By default reroll runs every sample through `claude -p` (Claude Code's non-interactive mode), so it uses your
Claude subscription's usage limits instead of API billing. Each turn is n Opus samples plus a Haiku call, so it
drains those limits quickly; `--model claude-sonnet-5` or `-n 3` stretch them. With `--backend api` it uses the
Anthropic API instead (put `ANTHROPIC_API_KEY` in `.env`). A session keeps the backend it was started with.

Then:

```bash
uv run main.py --system prompts/demartini.md
```

This opens http://127.0.0.1:8765. `--system` only prefills the prompt for new sessions.
Options: `--model` (default `anthropic:claude-opus-5`), `--judge` (default `anthropic:claude-haiku-4-5`),
`-n` (default 5), `--concurrency` (default 2, raise it if your API rate limit allows), `--effort`, `--port`.

## Using it

- Click a reply's label to see all samples side by side, grouped; "Continue with this" switches the last turn to another sample.
- "Edit" on your last message resamples it with the new text; earlier versions and their verdicts stay visible under it.
- "Resample" reruns the last turn with the same message.
- The system prompt (top bar) can be edited mid-session; it applies from the next message.
- "Export" (top bar) downloads the session as one read-only HTML page: readers can open every turn's samples and groups,
  but can't send messages. It needs no server, so it can be uploaded anywhere or embedded in an iframe.

Every session is saved to `sessions/` with all attempts, samples, judge output and the system prompt each attempt used.
Errors are logged to `reroll.log`.

## Reading sessions from the command line

`uv run peek.py overview` gives one line per turn of the latest session; see `uv run peek.py --help` for
`turn`, `replies`, `user`, `attempts`, `system` and `usage`. Raw API messages live in `sessions/<id>.messages.json`.
