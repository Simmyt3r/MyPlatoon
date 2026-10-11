"""WSGI entry point.

Used by:
  * `flask run` locally (via FLASK_APP=wsgi.py)
  * gunicorn in traditional hosting: gunicorn wsgi:app
  * Vercel's Python runtime (see vercel.json), which imports `app` directly.
"""
import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "production"))

if __name__ == "__main__":
    app.run(debug=(os.environ.get("FLASK_ENV") == "development"))
