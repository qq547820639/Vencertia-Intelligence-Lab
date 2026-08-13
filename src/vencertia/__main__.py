"""``python -m vencertia`` entry point (forwards to the typer CLI app)."""

from vencertia.cli import app

if __name__ == "__main__":
    app()
