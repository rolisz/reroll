"""FastAPI backend for reroll: one local user, one open session at a time."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from core import Attempt, Phase, Reroller, Session, Turn, spread

log = logging.getLogger("reroll")

ROOT = Path(__file__).parent
SESSIONS = ROOT / "sessions"
EXPORT_PLACEHOLDER = "<!-- reroll-export-data -->"


@dataclass
class Settings:
    model: str
    judge_model: str
    n: int
    concurrency: int
    max_tokens: int
    effort: str | None
    default_system_prompt: str
    backend: str = "cli"  # for new sessions; opened sessions keep the backend they were recorded with


class TextIn(BaseModel):
    text: str


class ChooseIn(BaseModel):
    index: int


class State:
    reroller: Reroller | None = None
    path: Path | None = None
    phase: Phase | None = None
    task: asyncio.Task | None = None

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    state = State()

    def session() -> Session:
        if state.reroller is None:
            raise HTTPException(404, "No session is open")
        return state.reroller.session

    def save() -> None:
        session().save(state.path)

    def require_idle() -> None:
        if state.busy:
            raise HTTPException(409, "Still sampling the last turn")

    def open_session(s: Session, path: Path) -> None:
        state.reroller = Reroller(
            s,
            s.model,
            s.judge_model,
            effort=settings.effort,
            concurrency=settings.concurrency,
            max_tokens=settings.max_tokens,
        )
        state.path = path
        log.info("Opened session %s (%d turns)", path.stem, len(s.turns))

    def view() -> dict:
        if state.reroller is None:
            return {"session": None, "busy": False, "phase": None}
        s = state.reroller.session
        turns = []
        for turn in s.turns:
            current = turn.current.model_dump(mode="json", exclude={"samples": {"__all__": {"messages"}}})
            current["spread"] = spread(turn.current)
            current["earlier"] = [
                {
                    "user_message": a.user_message,
                    "kind": a.divergence.kind if a.divergence else None,
                    "summary": a.divergence.summary if a.divergence else None,
                }
                for a in turn.attempts[:-1]
            ]
            turns.append(current)
        return {
            "session": {
                "id": state.path.stem,
                "model": s.model,
                "judge_model": s.judge_model,
                "n": s.n,
                "system_prompt": s.system_prompt,
                "backend": s.backend,
                "turns": turns,
            },
            "busy": state.busy,
            "phase": state.phase,
        }

    async def run(attempt: Attempt) -> None:
        def on_progress(phase: Phase) -> None:
            state.phase = phase
            save()

        try:
            await state.reroller.run(attempt, on_progress)
        except Exception as e:
            log.exception("Turn failed")
            attempt.errors.append(f"{type(e).__name__}: {e}")
        finally:
            state.phase = None
            save()

    def start(turn: Turn, text: str) -> dict:
        if not text.strip():
            raise HTTPException(400, "Empty message")
        attempt = Attempt(user_message=text.strip())
        turn.attempts.append(attempt)
        save()
        state.phase = "sampling"
        state.task = asyncio.create_task(run(attempt))
        return view()

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(ROOT / "static" / "index.html")

    @app.get("/api/config")
    async def config() -> dict:
        return {
            "model": settings.model,
            "judge_model": settings.judge_model,
            "n": settings.n,
            "default_system_prompt": settings.default_system_prompt,
            "backend": settings.backend,
        }

    @app.get("/api/sessions")
    async def list_sessions() -> list[dict]:
        items = []
        for path in sorted(SESSIONS.glob("*.json"), reverse=True):
            if path.name.endswith(".messages.json"):
                continue
            try:
                s = Session.load(path, with_messages=False)
            except Exception:
                log.exception("Could not read session %s", path)
                continue
            preview = s.turns[0].attempts[0].user_message[:100] if s.turns else ""
            items.append({"id": path.stem, "started": s.started, "turns": len(s.turns), "preview": preview})
        return items

    @app.post("/api/sessions")
    async def new_session(body: TextIn) -> dict:
        require_idle()
        s = Session(
            started=datetime.now(),
            model=settings.model,
            judge_model=settings.judge_model,
            n=settings.n,
            system_prompt=body.text,
            backend=settings.backend,
        )
        SESSIONS.mkdir(exist_ok=True)
        open_session(s, SESSIONS / f"{s.started:%Y%m%d-%H%M%S}.json")
        save()
        return view()

    @app.post("/api/sessions/{session_id}/open")
    async def open_existing(session_id: str) -> dict:
        require_idle()
        path = SESSIONS / f"{session_id}.json"
        if not re.fullmatch(r"[\w-]+", session_id) or not path.exists():
            raise HTTPException(404, "No such session")
        open_session(Session.load(path), path)
        return view()

    @app.get("/api/session/export")
    async def export() -> HTMLResponse:
        """The UI as one self-contained, read-only HTML file with this session embedded."""
        require_idle()
        data = view()
        if data["session"] is None:
            raise HTTPException(404, "No session is open")
        page = (ROOT / "static" / "index.html").read_text()
        # Escaping "<" keeps session text from closing the script tag early.
        payload = json.dumps(data).replace("<", "\\u003c")
        page = page.replace(EXPORT_PLACEHOLDER, f"<script>window.REROLL_EXPORT = {payload};</script>")
        filename = f"reroll-{data['session']['id']}.html"
        return HTMLResponse(page, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/session")
    async def get_session() -> dict:
        return view()

    @app.put("/api/session/system_prompt")
    async def set_system_prompt(body: TextIn) -> dict:
        require_idle()
        session().system_prompt = body.text
        save()
        return view()

    @app.post("/api/session/messages")
    async def send(body: TextIn) -> dict:
        require_idle()
        turns = session().turns
        # If the last turn failed completely, retry it instead of leaving a gap in the history.
        if turns and not turns[-1].current.samples:
            turn = turns[-1]
        else:
            turn = Turn()
            turns.append(turn)
        return start(turn, body.text)

    @app.post("/api/session/edit")
    async def edit(body: TextIn) -> dict:
        require_idle()
        if not session().turns:
            raise HTTPException(400, "Nothing to edit")
        return start(session().turns[-1], body.text)

    @app.post("/api/session/resample")
    async def resample() -> dict:
        require_idle()
        if not session().turns:
            raise HTTPException(400, "Nothing to resample")
        turn = session().turns[-1]
        return start(turn, turn.current.user_message)

    @app.post("/api/session/choose")
    async def choose(body: ChooseIn) -> dict:
        require_idle()
        if not session().turns:
            raise HTTPException(400, "No turns yet")
        attempt = session().turns[-1].current
        if not 0 <= body.index < len(attempt.samples):
            raise HTTPException(400, "No such sample")
        attempt.chosen = body.index
        save()
        return view()

    return app
