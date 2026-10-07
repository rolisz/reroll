"""Sampling, judging and session storage for reroll."""

import asyncio
import json
import logging
import os
import random
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

log = logging.getLogger("reroll")

Kind = Literal["same", "open_moves", "interpretation", "contradiction"]
Backend = Literal["api", "cli"]  # cli: local Claude CLI; api: programmatic Anthropic API access
Phase = Literal["sampling", "judging", "done"]


class Group(BaseModel):
    label: str = Field(description="What the replies in this group do, in under 10 words")
    members: list[int] = Field(description="1-based numbers of the replies in this group")


class Divergence(BaseModel):
    groups: list[Group]
    kind: Kind
    summary: str = Field(description="What the replies disagree on, concretely, in under 40 words")
    clarification: str | None = Field(
        description="Only for kind=interpretation: a sentence the user could add to their last message "
        "to remove the ambiguity, written in the user's voice. Otherwise null."
    )
    sycophancy: str | None = Field(
        description="If every reply accepts the user's framing or claims where an honest, thoughtful "
        "interlocutor would question them, say in one sentence what should have been questioned. Otherwise null."
    )


class Sample(BaseModel):
    text: str
    # The request/response pair this run adds to the history. Stored in <session>.messages.json, not the session file.
    messages: list[ModelMessage] = []
    seconds: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cli_session_id: str | None = None  # cli backend: the Claude Code session ending in this reply, to resume from


class Attempt(BaseModel):
    user_message: str
    system_prompt: str = ""  # the system prompt in effect for this attempt; it can be edited mid-session
    samples: list[Sample] = []
    errors: list[str] = []
    chosen: int = 0  # index into samples
    waiting_for_chosen: bool = False  # while sampling: samples[chosen] hasn't finished yet
    divergence: Divergence | None = None
    judge_error: str | None = None


class Turn(BaseModel):
    attempts: list[Attempt] = []

    @property
    def current(self) -> Attempt:
        return self.attempts[-1]


class Session(BaseModel):
    started: datetime
    model: str
    judge_model: str
    n: int
    system_prompt: str
    backend: Backend = "api"
    turns: list[Turn] = []

    def history(self, before: int) -> list[ModelMessage]:
        """Messages of the chosen path, for the turns before `before`."""
        messages: list[ModelMessage] = []
        for turn in self.turns[:before]:
            attempt = turn.current
            if attempt.samples:
                messages.extend(attempt.samples[attempt.chosen].messages)
        return messages

    def cli_session_to_resume(self, before: int) -> str | None:
        """cli backend: the Claude Code session of the chosen reply in the last answered turn before `before`."""
        for turn in reversed(self.turns[:before]):
            attempt = turn.current
            if attempt.samples:
                session_id = attempt.samples[attempt.chosen].cli_session_id
                if session_id is None:
                    raise ValueError("This turn's reply wasn't recorded with claude -p, so the conversation can't continue there")
                return session_id
        return None

    def transcript(self, before: int) -> str:
        parts = []
        for turn in self.turns[:before]:
            attempt = turn.current
            parts.append(f"USER: {attempt.user_message}")
            if attempt.samples:
                parts.append(f"ASSISTANT: {attempt.samples[attempt.chosen].text}")
        return "\n\n".join(parts)

    def save(self, path: Path) -> None:
        # Sidecar first: if we crash in between, it has extra entries rather than missing ones.
        messages = [[[sample.messages for sample in a.samples] for a in t.attempts] for t in self.turns]
        messages_path(path).write_bytes(_MESSAGES.dump_json(messages))
        path.write_text(self.model_dump_json(indent=2, exclude=_WITHOUT_MESSAGES))

    @classmethod
    def load(cls, path: Path, with_messages: bool = True) -> "Session":
        session = cls.model_validate_json(path.read_text())
        # A loaded session isn't sampling; this is only left over if the server stopped mid-turn.
        for turn in session.turns:
            for attempt in turn.attempts:
                attempt.waiting_for_chosen = False
        sidecar = messages_path(path)
        if with_messages and sidecar.exists():  # older sessions have the messages inline instead
            for turn, turn_messages in zip(session.turns, _MESSAGES.validate_json(sidecar.read_bytes())):
                for attempt, attempt_messages in zip(turn.attempts, turn_messages):
                    for sample, sample_messages in zip(attempt.samples, attempt_messages):
                        sample.messages = sample_messages
        return session


_MESSAGES = TypeAdapter(list[list[list[list[ModelMessage]]]])
_WITHOUT_MESSAGES = {"turns": {"__all__": {"attempts": {"__all__": {"samples": {"__all__": {"messages"}}}}}}}


def messages_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.messages.json")


Spread = Literal["uniform", "mostly uniform", "split", "highly divergent"]


def spread(attempt: Attempt) -> Spread | None:
    """How much the samples agree, from the share of samples in the largest group."""
    if not attempt.divergence or len(attempt.samples) < 2:
        return None
    largest = max(len(g.members) for g in attempt.divergence.groups) / len(attempt.samples)
    if largest >= 1:
        return "uniform"
    if largest >= 0.75:
        return "mostly uniform"
    if largest >= 0.5:
        return "split"
    return "highly divergent"


RATE_LIMIT_RETRIES = 6  # waits 1, 2, 4, 8, 15, 15 seconds

JUDGE_PROMPT = """\
You compare several candidate replies that a conversational AI produced at the same point in a conversation.
They were sampled independently from the same model, with the same history and the same user message.
The user reads your analysis to decide whether their last message was underspecified, and whether the
reply they happened to get is typical or a fluke.

Group the replies by what they actually do, ignoring wording, tone, length and formatting. Two replies
belong in the same group if the user would respond to them in essentially the same way: the same question
asked, the same point made, the same reading of the user's message.

Then classify the most important divergence, picking the first of these that applies:
- contradiction: replies make claims (about facts, or about the user) that cannot all be true.
- interpretation: replies read the user's last message differently: a different meaning, referent,
  goal or assumed context.
- open_moves: replies read the user the same way but take different, compatible next steps,
  such as probing different topics.
- same: the replies are essentially interchangeable.

Be concrete in the summary: name what differs, don't just say that the replies differ. Keep it short: the user
reads it under every reply, so use at most two sentences and under 40 words. Group labels stay under 10 words.
"""


CLI_DIR = Path(__file__).parent / ".claude-cli"  # keeps these runs out of the user's normal Claude Code history
# Without a system prompt, claude -p would use Claude Code's coding-agent prompt.
CLI_DEFAULT_SYSTEM_PROMPT = "You are Claude, a helpful assistant."


class CliError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


async def run_claude_cli(prompt: str, *args: str) -> dict:
    """Run `claude -p` as a plain local chat; return its final `result` event."""
    CLI_DIR.mkdir(exist_ok=True)
    # With ANTHROPIC_API_KEY in the environment (e.g. from .env), claude -p would bill the API instead.
    env = {key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"}
    process = await asyncio.create_subprocess_exec(
        "claude", "-p", "--output-format", "json",
        "--safe-mode", "--tools", "",  # no CLAUDE.md, hooks, plugins, MCP servers or tools
        *args,
        cwd=CLI_DIR, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        # The prompt goes in on stdin, so messages starting with "-" aren't read as flags.
        stdout, stderr = await process.communicate(prompt.encode())
    except asyncio.CancelledError:
        process.kill()
        raise
    try:
        result = next(event for event in json.loads(stdout) if event.get("type") == "result")
    except (json.JSONDecodeError, StopIteration, TypeError, AttributeError):
        output = (stderr or stdout).decode(errors="replace").strip()
        raise CliError(f"claude -p exited with code {process.returncode}: {output[-500:]}") from None
    if result.get("is_error"):
        raise CliError(f"claude -p: {result.get('result') or result.get('subtype')}", result.get("api_error_status"))
    return result


def _is_rate_limit(error: BaseException) -> bool:
    return (isinstance(error, ModelHTTPError) and error.status_code == 429) or (
        isinstance(error, CliError) and error.status == 429
    )


def _describe_error(error: BaseException) -> str:
    if isinstance(error, (CliError, ValueError)):
        return str(error)
    if isinstance(error, ModelHTTPError) and isinstance(error.body, dict):
        message = (error.body.get("error") or {}).get("message")
        if message:
            return f"HTTP {error.status_code}: {message}"
    return f"{type(error).__name__}: {error}"


def _judge_input(transcript: str, attempt: Attempt, system_prompt: str) -> str:
    replies = "\n\n".join(
        f'<reply n="{i}">\n{sample.text}\n</reply>' for i, sample in enumerate(attempt.samples, start=1)
    )
    return (
        f"<assistant_setup>\n{system_prompt or '(none)'}\n</assistant_setup>\n\n"
        f"<conversation_so_far>\n{transcript or '(this is the first message)'}\n</conversation_so_far>\n\n"
        f"<last_user_message>\n{attempt.user_message}\n</last_user_message>\n\n"
        f"<candidate_replies>\n{replies}\n</candidate_replies>"
    )


class Reroller:
    def __init__(
        self,
        session: Session,
        model: Model | str,
        judge_model: Model | str,
        effort: str | None = None,
        concurrency: int = 2,
        max_tokens: int = 32000,
    ):
        self.session = session
        # Backends limit concurrent requests, so samples beyond the configured limit wait for a free slot.
        self.slots = asyncio.Semaphore(concurrency)
        self.concurrency = concurrency
        self.effort = effort
        if session.backend == "cli":
            if not (isinstance(model, str) and isinstance(judge_model, str)):
                raise ValueError("The claude -p backend needs model names, not model objects")
            self.cli_model = model.removeprefix("anthropic:")
            self.cli_judge_model = judge_model.removeprefix("anthropic:")
            return
        self.agent = Agent(
            model,
            # Samples in a turn share their whole prompt, and each turn extends the last one's, so cache it (5 min TTL).
            # max_tokens covers thinking too; Pydantic AI's default of 4096 can be used up before any reply is written.
            # (Above the SDK's non-streaming limit, Pydantic AI streams the request under the hood.)
            model_settings={"anthropic_cache": True, "max_tokens": max_tokens}
            | ({"anthropic_effort": effort} if effort else {}),
        )
        self.judge_agent = Agent(judge_model, output_type=Divergence, instructions=JUDGE_PROMPT)

    async def _sample(self, prompt: str, context: list[ModelMessage] | str | None) -> Sample:
        """One reply. `context` is the message history (api) or the Claude Code session to fork from (cli)."""
        # A 429 on concurrent connections clears up once another request finishes, but the SDK's own retries
        # give up within a couple of seconds. Wait longer, outside the slot so running samples can finish.
        for retry in range(RATE_LIMIT_RETRIES + 1):
            async with self.slots:
                start = time.monotonic()
                try:
                    if self.session.backend == "cli":
                        sample = await self._sample_cli(prompt, context)
                    else:
                        sample = await self._sample_api(prompt, context)
                    break
                except Exception as e:
                    if not _is_rate_limit(e) or retry == RATE_LIMIT_RETRIES:
                        log.exception("Sample failed after %.0fs", time.monotonic() - start)
                        raise
            delay = min(2**retry, 15)
            log.warning("Sample rate limited, retrying in %ds", delay)
            await asyncio.sleep(delay)
        sample.seconds = time.monotonic() - start
        log.info(
            "Sample done in %.0fs: %d output tokens, %d cached, %d written to cache",
            sample.seconds, sample.output_tokens, sample.cache_read_tokens, sample.cache_write_tokens,
        )
        return sample

    async def _sample_api(self, prompt: str, history: list[ModelMessage]) -> Sample:
        result = await self.agent.run(prompt, message_history=history, instructions=self.session.system_prompt or None)
        usage = result.usage
        return Sample(
            text=result.output,
            messages=result.new_messages(),
            seconds=0,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
        )

    async def _sample_cli(self, prompt: str, resume: str | None) -> Sample:
        args = [
            "--model", self.cli_model,
            "--system-prompt", self.session.system_prompt or CLI_DEFAULT_SYSTEM_PROMPT,
            "--system-prompt-snapshot", "off",  # use the current system prompt on resume, so mid-session edits apply
        ]
        if self.effort:
            args += ["--effort", self.effort]
        if resume:
            args += ["--resume", resume, "--fork-session"]  # each sample branches off the chosen reply's session
        result = await run_claude_cli(prompt, *args)
        usage = result.get("usage") or {}
        return Sample(
            text=result.get("result") or "",
            cli_session_id=result["session_id"],
            seconds=0,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
        )

    async def _judge(self, judge_input: str) -> Divergence:
        if self.session.backend == "cli":
            result = await run_claude_cli(
                judge_input,
                "--model", self.cli_judge_model,
                "--system-prompt", JUDGE_PROMPT,
                "--json-schema", json.dumps(Divergence.model_json_schema()),
                "--no-session-persistence",
            )
            return Divergence.model_validate(result["structured_output"])
        return (await self.judge_agent.run(judge_input)).output

    async def run(self, attempt: Attempt, on_progress: Callable[[Phase], None]) -> None:
        """Sample the last turn's `attempt` n times, then judge how the samples diverge."""
        turn_index = len(self.session.turns) - 1
        if self.session.backend == "cli":
            context = self.session.cli_session_to_resume(before=turn_index)
        else:
            context = self.session.history(before=turn_index)
        attempt.system_prompt = self.session.system_prompt
        tasks = [asyncio.create_task(self._sample(attempt.user_message, context)) for _ in range(self.session.n)]
        log.info("Turn %d: sampling %d replies to %r", turn_index + 1, self.session.n, attempt.user_message[:80])

        # Show a random sample, not whichever finishes first: that would favour short replies. Pick it from the
        # samples that start right away, so it isn't stuck waiting for a slot. Record every sample as it finishes.
        shown = tasks[random.randrange(min(len(tasks), self.concurrency))]
        attempt.samples, attempt.errors, attempt.chosen, attempt.waiting_for_chosen = [], [], 0, True
        pending = set(tasks)
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if error := task.exception():  # already logged in _sample
                        attempt.errors.append(_describe_error(error))
                    else:
                        if task is shown:
                            attempt.chosen = len(attempt.samples)
                        attempt.samples.append(task.result())
                    if task is shown:  # if it failed, fall back to the first sample that succeeds
                        attempt.waiting_for_chosen = False
                on_progress("sampling")
        finally:
            for task in pending:
                task.cancel()

        if len(attempt.samples) >= 2:
            on_progress("judging")
            try:
                judge_input = _judge_input(self.session.transcript(before=turn_index), attempt, self.session.system_prompt)
                attempt.divergence = await self._judge(judge_input)
                sizes = "-".join(sorted((str(len(g.members)) for g in attempt.divergence.groups), reverse=True))
                log.info("Turn %d: %s, %s (%s)", turn_index + 1, spread(attempt), attempt.divergence.kind, sizes)
            except Exception as e:
                log.exception("Judge failed")
                attempt.judge_error = _describe_error(e)
        on_progress("done")
