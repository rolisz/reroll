"""Read reroll sessions piece by piece, without opening the JSON. Run `uv run peek.py --help`."""

import argparse
import sys
from pathlib import Path

from core import Attempt, Divergence, Session, Turn, spread

SESSIONS = Path(__file__).parent / "sessions"
KINDS = {
    "same": "consistent",
    "open_moves": "different next moves",
    "interpretation": "read you differently",
    "contradiction": "contradicting each other",
}


def rule(label: str) -> str:
    return f"──── {label} " + "─" * max(4, 70 - len(label))


def one_line(text: str, width: int = 90) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else f"{flat[:width]}… ({len(text)} chars)"


def session_files() -> list[Path]:
    return sorted(p for p in SESSIONS.glob("*.json") if not p.name.endswith(".messages.json"))


def find_session(part: str | None) -> Path:
    files = session_files()
    if not files:
        sys.exit("No sessions yet.")
    if part is None:
        return max(files, key=lambda p: p.stat().st_mtime)
    matches = [p for p in files if part in p.stem]
    if len(matches) != 1:
        sys.exit(f"{len(matches)} sessions match {part!r}: {', '.join(p.stem for p in matches) or '-'}")
    return matches[0]


def get_turn(session: Session, n: int) -> Turn:
    if not 1 <= n <= len(session.turns):
        sys.exit(f"Turn {n} doesn't exist; the session has {len(session.turns)} turns.")
    return session.turns[n - 1]


def get_attempt(turn: Turn, n: int | None) -> tuple[int, Attempt]:
    if n is None:
        return len(turn.attempts), turn.current
    if not 1 <= n <= len(turn.attempts):
        sys.exit(f"Attempt {n} doesn't exist; the turn has {len(turn.attempts)} attempts.")
    return n, turn.attempts[n - 1]


def group_letter(d: Divergence | None, sample_index: int) -> str | None:
    if d:
        for g, group in enumerate(d.groups):
            if sample_index + 1 in group.members:
                return chr(65 + g)
    return None


def verdict(a: Attempt) -> str:
    if not a.samples:
        return "all samples failed"
    if not a.divergence:
        return f"no verdict ({a.judge_error or 'fewer than 2 samples'})"
    sizes = "-".join(str(len(g.members)) for g in sorted(a.divergence.groups, key=lambda g: -len(g.members)))
    kind = "" if a.divergence.kind == "same" else f" · {KINDS[a.divergence.kind]}"
    return f"{spread(a)}{kind} · {sizes}"


def current_reply(a: Attempt) -> str:
    if not a.samples:
        return "none"
    letter = group_letter(a.divergence, a.chosen)
    return f"reply {a.chosen + 1}" + (f" (group {letter})" if letter else "")


def cmd_sessions(args: argparse.Namespace) -> None:
    for path in sorted(session_files(), reverse=True):
        s = Session.load(path, with_messages=False)
        preview = one_line(s.turns[0].attempts[0].user_message, 70) if s.turns else "(empty)"
        print(f"{path.stem} · {len(s.turns)} turns · {s.model} · {preview}")


def cmd_overview(session: Session, path: Path, args: argparse.Namespace) -> None:
    print(f"{path.stem} · {session.model} · n={session.n} · judge {session.judge_model}")
    print(f"system prompt: {one_line(session.system_prompt) if session.system_prompt else '(none)'}")
    previous_prompt = None
    for i, turn in enumerate(session.turns, start=1):
        a = turn.current
        prompt_note = " · system prompt changed" if previous_prompt is not None and a.system_prompt != previous_prompt else ""
        previous_prompt = a.system_prompt
        attempts = f" · attempt {len(turn.attempts)}/{len(turn.attempts)}" if len(turn.attempts) > 1 else ""
        print(f"turn {i}{attempts} · {verdict(a)} · current {current_reply(a)}{prompt_note} · {one_line(a.user_message, 60)}")


def cmd_turn(session: Session, path: Path, args: argparse.Namespace) -> None:
    turn = get_turn(session, args.n)
    k, a = get_attempt(turn, args.attempt)
    print(rule(f"turn {args.n} · attempt {k}/{len(turn.attempts)}"))
    print(f"user: {one_line(a.user_message, 200)}")
    print(f"verdict: {verdict(a)}")
    d = a.divergence
    if d:
        print(f"summary: {d.summary}")
        print("groups:")
        for g, group in enumerate(d.groups):
            print(f"  {chr(65 + g)} ({len(group.members)}): {group.label} · replies {', '.join(map(str, group.members))}")
        if d.clarification:
            print(f"clarification: {d.clarification}")
        if d.sycophancy:
            print(f"sycophancy: {d.sycophancy}")
    print(f"current: {current_reply(a)}")
    for error in a.errors:
        print(f"error: {error}")
    if args.n > 1 and a.system_prompt != session.turns[args.n - 2].current.system_prompt:
        print("system prompt: changed since the previous turn (`system N` shows it)")


def cmd_replies(session: Session, path: Path, args: argparse.Namespace) -> None:
    turn = get_turn(session, args.n)
    _, a = get_attempt(turn, args.attempt)
    for i, sample in enumerate(a.samples):
        letter = group_letter(a.divergence, i)
        if args.reply and i + 1 not in args.reply:
            continue
        if args.group and letter != args.group.upper():
            continue
        label = f"turn {args.n} · reply {i + 1}" + (f" · group {letter}" if letter else "")
        label += " · current" if i == a.chosen else ""
        print(rule(label))
        print(sample.text.strip())
        print()


def cmd_user(session: Session, path: Path, args: argparse.Namespace) -> None:
    _, a = get_attempt(get_turn(session, args.n), args.attempt)
    print(a.user_message)


def cmd_attempts(session: Session, path: Path, args: argparse.Namespace) -> None:
    turn = get_turn(session, args.n)
    for k, a in enumerate(turn.attempts, start=1):
        print(rule(f"turn {args.n} · attempt {k}/{len(turn.attempts)} · {verdict(a)}"))
        print(a.user_message)
        if a.divergence:
            print(f"\nsummary: {a.divergence.summary}")
        print()


def cmd_system(session: Session, path: Path, args: argparse.Namespace) -> None:
    if args.n is None:
        print(session.system_prompt or "(none)")
        return
    _, a = get_attempt(get_turn(session, args.n), args.attempt)
    print(a.system_prompt or "(none)")


def cmd_usage(session: Session, path: Path, args: argparse.Namespace) -> None:
    def k(tokens: int) -> str:
        return f"{tokens / 1000:.1f}k"

    totals = [0, 0, 0, 0]
    for i, turn in enumerate(session.turns, start=1):
        for j, a in enumerate(turn.attempts, start=1):
            if not a.samples:
                continue
            row = [sum(getattr(s, f) for s in a.samples) for f in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")]
            totals = [t + r for t, r in zip(totals, row)]
            slowest = max(s.seconds for s in a.samples)
            print(
                f"turn {i} · attempt {j} · {len(a.samples)} samples · input {k(row[0])} · cache read {k(row[1])}"
                f" · cache write {k(row[2])} · output {k(row[3])} · slowest {slowest:.0f}s"
            )
    print(f"total · input {k(totals[0])} · cache read {k(totals[1])} · cache write {k(totals[2])} · output {k(totals[3])}")


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-s", "--session", default=argparse.SUPPRESS, help="part of a session id (default: the most recently modified)")
    parser = argparse.ArgumentParser(description=__doc__, parents=[common])
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("sessions", parents=[common], help="list sessions")
    commands.add_parser("overview", parents=[common], help="one line per turn: verdict, group sizes, current reply")
    p = commands.add_parser("turn", parents=[common], help="verdict, summary and groups for a turn")
    p.add_argument("n", type=int)
    p.add_argument("--attempt", type=int, help="earlier attempt (default: current)")
    p = commands.add_parser("replies", parents=[common], help="reply texts for a turn")
    p.add_argument("n", type=int)
    p.add_argument("--reply", type=int, action="append", help="only this reply (repeatable)")
    p.add_argument("--group", help="only replies in this group, e.g. A")
    p.add_argument("--attempt", type=int, help="earlier attempt (default: current)")
    p = commands.add_parser("user", parents=[common], help="the full user message for a turn")
    p.add_argument("n", type=int)
    p.add_argument("--attempt", type=int, help="earlier attempt (default: current)")
    p = commands.add_parser("attempts", parents=[common], help="every version of a turn's message, with verdicts")
    p.add_argument("n", type=int)
    p = commands.add_parser("system", parents=[common], help="system prompt: current, or the one a turn used")
    p.add_argument("n", type=int, nargs="?")
    p.add_argument("--attempt", type=int, help="earlier attempt (default: current)")
    commands.add_parser("usage", parents=[common], help="tokens, cache and time per turn")
    args = parser.parse_args()

    if args.command == "sessions":
        cmd_sessions(args)
        return
    path = find_session(getattr(args, "session", None))
    session = Session.load(path, with_messages=False)
    globals()[f"cmd_{args.command}"](session, path, args)


if __name__ == "__main__":
    main()
