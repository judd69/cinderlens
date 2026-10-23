"""Allow ``python -m cinderlens`` as an entry point."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
