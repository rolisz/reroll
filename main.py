import argparse
import copy
import logging
import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn
from uvicorn.config import LOGGING_CONFIG
from dotenv import load_dotenv

from web import Settings, create_app

ROOT = Path(__file__).parent


class SkipPolling(logging.Filter):
    """The page polls the session every second while sampling; those requests would drown out everything else."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return '"GET /api/session HTTP' not in message and '"GET /api/sessions HTTP' not in message


def model_name(name: str) -> str:
    return name if ":" in name else f"anthropic:{name}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat where every reply is sampled n times and compared.")
    parser.add_argument("--system", type=Path, help="default system prompt for new sessions, e.g. prompts/demartini.md")
    parser.add_argument(
        "--backend",
        choices=["cli", "api"],
        default="cli",
        help="cli: local experimentation through `claude -p` (default); api: programmatic Anthropic API access",
    )
    parser.add_argument("--model", default="anthropic:claude-opus-5")
    parser.add_argument("--judge", default="anthropic:claude-haiku-4-5")
    parser.add_argument("-n", type=int, default=5, help="samples per turn")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="effort for Claude models")
    parser.add_argument("--concurrency", type=int, default=2, help="max samples requested at once (API rate limit)")
    parser.add_argument("--max-tokens", type=int, default=32000, help="api backend: per reply, including thinking")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    # The terminal gets reroll's own lines plus any warnings; per-request HTTP client lines only go to the file.
    console = logging.StreamHandler()
    console.addFilter(lambda record: record.name.startswith("reroll") or record.levelno >= logging.WARNING)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(ROOT / "reroll.log"), console],
    )

    settings = Settings(
        model=model_name(args.model),
        judge_model=model_name(args.judge),
        n=args.n,
        concurrency=args.concurrency,
        max_tokens=args.max_tokens,
        effort=args.effort,
        default_system_prompt=args.system.read_text() if args.system else "",
        backend=args.backend,
    )
    if args.backend == "cli":
        if not shutil.which("claude"):
            sys.exit("The cli backend needs Claude Code's `claude` command on your PATH (or use --backend api).")
        if not all(m.startswith("anthropic:") for m in (settings.model, settings.judge_model)):
            sys.exit("The cli backend only runs Claude models.")
    elif any(m.startswith("anthropic:") for m in (settings.model, settings.judge_model)) and not os.environ.get(
        "ANTHROPIC_API_KEY"
    ):
        sys.exit(f"ANTHROPIC_API_KEY is not set. Put it in {ROOT / '.env'} or export it.")

    url = f"http://127.0.0.1:{args.port}"
    print(f"reroll running at {url}")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    log_config = copy.deepcopy(LOGGING_CONFIG)
    log_config["filters"] = {"skip_polling": {"()": SkipPolling}}
    log_config["handlers"]["access"]["filters"] = ["skip_polling"]
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, log_config=log_config)


if __name__ == "__main__":
    main()
