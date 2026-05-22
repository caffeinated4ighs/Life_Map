"""
main.py — CLI entry point for the Life System orchestrator.

Usage:
  python -m orchestrator morning
  python -m orchestrator eod
  python -m orchestrator health
  python -m orchestrator complete "user message here"
"""

import json
import sys

from orchestrator.config import load_config
from orchestrator.logger import setup_logger
from orchestrator.health import health_check
from orchestrator.sequencer import run_morning, run_eod, run_complete_task


def _print_json(data):
    print(json.dumps(data, indent=2, default=str))


def main(argv=None):
    argv = argv or sys.argv[1:]

    if not argv:
        print(
            "Usage:\n"
            "  python -m orchestrator morning\n"
            "  python -m orchestrator eod\n"
            "  python -m orchestrator health\n"
            "  python -m orchestrator complete \"<user message>\"\n",
            file=sys.stderr,
        )
        sys.exit(1)

    command = argv[0].lower()

    # Load config first — fail fast on missing env vars
    try:
        config = load_config()
    except EnvironmentError as e:
        print(f"[CONFIG ERROR]\n{e}", file=sys.stderr)
        sys.exit(1)

    # Set up logging
    logger = setup_logger(config.log_level)

    try:
        if command == "health":
            ok = health_check(config)
            if ok:
                _print_json({"status": "ok"})
                sys.exit(0)
            else:
                _print_json({"status": "error", "detail": "Supabase health check failed"})
                sys.exit(1)

        elif command == "morning":
            result = run_morning(config)
            _print_json(result)
            sys.exit(0)

        elif command == "eod":
            result = run_eod(config)
            _print_json(result)
            sys.exit(0)

        elif command == "complete":
            if len(argv) < 2:
                print("Error: 'complete' requires a message argument.\n"
                      "  python -m orchestrator complete \"Complete task X on time\"",
                      file=sys.stderr)
                sys.exit(1)
            user_message = " ".join(argv[1:])
            result = run_complete_task(config, user_message)
            _print_json(result)
            sys.exit(0)

        else:
            print(f"Unknown command: '{command}'. Valid: morning, eod, health, complete",
                  file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        logger.error(f"Unhandled error in command '{command}': {e}", exc_info=True)
        _print_json({"status": "error", "detail": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
