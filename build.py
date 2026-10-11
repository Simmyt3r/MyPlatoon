"""Static asset mirror — run this manually, not a Vercel build hook.

Vercel serves static assets from public/**, not through the Flask app
(see DEPLOYMENT.md). Rather than hand-maintain two copies of app/static,
run this script to mirror app/static into public/static whenever you
change something under app/static/, then commit the result:

    python build.py

(Earlier this was wired up as an automatic Vercel build step via
pyproject.toml's [tool.vercel.scripts], but merely having a pyproject.toml
present makes Vercel's newer build pipeline switch dependency resolution
from requirements.txt to uv+pyproject.toml — which then fails unless
pyproject.toml is a fully valid PEP 621 project file. Simplest fix: no
pyproject.toml at all, and run this manually before deploying instead.)
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "app" / "static"
DEST = ROOT / "public" / "static"


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(SRC, DEST)
    print(f"Mirrored {SRC} -> {DEST}")
    print("Remember to commit the public/static/ changes before deploying.")


if __name__ == "__main__":
    main()
