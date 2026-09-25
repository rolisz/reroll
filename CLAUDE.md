# reroll

Local web app where every chat reply is sampled n times and Haiku judges how the samples diverge. See README.md.
An exploratory project with Roland: we work out the ideas together, so propose before building bigger changes.

- `core.py`: sampling (`Reroller`), judge prompt, `Session` models and storage
- `web.py`: FastAPI API (one open session). `static/index.html`: the whole UI, plain JS, no build step
- `main.py`: CLI flags, starts uvicorn. `peek.py`: reads sessions

Roland runs the app himself. Don't start the server, make paid API calls or burn his subscription usage via
`claude -p` unless asked, and keep self-testing light (imports, syntax) since he tries changes right away.

## Reading sessions

Don't read `sessions/*.json` directly: long texts are single escaped lines and the files get big. Use `peek.py`,
which defaults to the most recently modified session (`-s <part of id>` for another):

```
uv run peek.py sessions            # list sessions
uv run peek.py overview            # one line per turn: verdict, group sizes, current reply
uv run peek.py turn 3              # summary, groups, clarification, sycophancy, current reply
uv run peek.py replies 3 --group B # reply texts (--reply 2, --attempt 1)
uv run peek.py user 3              # full user message
uv run peek.py attempts 3          # every edited version of turn 3 with its verdict
uv run peek.py system 3            # system prompt that turn used
uv run peek.py usage               # tokens, cache read/write, time
```

Storage: `sessions/<id>.json` holds turns, attempts, sample texts and judge output; `sessions/<id>.messages.json`
holds the raw Pydantic AI messages used to rebuild API history (never needed for analysis). Older sessions have
the messages inline.

Don't generalize from one session (e.g. "outlier replies are better"): note observations as observations.
