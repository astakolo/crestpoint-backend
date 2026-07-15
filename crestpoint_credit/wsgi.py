"""
WSGI config for CrestPoint Credit project.

Vercel serverless fix: The deployed filesystem is read-only, so SQLite
cannot write to its default location.  On cold start we copy ``db.sqlite3``
into ``/tmp`` (writable) and point Django at the copy so that POST/PUT/PATCH
requests that touch the database succeed.
"""

import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup – make sure the project root (containing manage.py) is on
# sys.path so that ``crestpoint_credit`` is importable.
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crestpoint_credit.settings")

# ---------------------------------------------------------------------------
# Vercel read-only filesystem workaround
# ---------------------------------------------------------------------------
_DB_FILENAME = "db.sqlite3"
_READONLY_DB = _project_root / _DB_FILENAME
_WRITABLE_DB = Path("/tmp") / _DB_FILENAME


def _ensure_writable_db() -> None:
    """Copy the deployed SQLite file into /tmp so Django can write to it.

    This is a no-op when running locally (the DB is already writable) or
    when a writable copy already exists from a previous warm invocation.
    """
    # Skip if we're not on Vercel (local dev, Docker, etc.)
    if not os.environ.get("VERCEL"):
        return

    # If a writable copy already exists from a previous warm invocation, reuse it.
    if _WRITABLE_DB.exists():
        os.environ["DB_NAME"] = str(_WRITABLE_DB)
        return

    # Copy the read-only DB shipped with the deployment into /tmp.
    if _READONLY_DB.exists():
        shutil.copy2(str(_READONLY_DB), str(_WRITABLE_DB))
        os.environ["DB_NAME"] = str(_WRITABLE_DB)
    else:
        # No pre-existing DB – just point at /tmp so Django can create one.
        os.environ["DB_NAME"] = str(_WRITABLE_DB)


_ensure_writable_db()

# ---------------------------------------------------------------------------
# Django WSGI application
# ---------------------------------------------------------------------------
from django.core.wsgi import get_wsgi_application  # noqa: E402

_django_app = get_wsgi_application()

# ---------------------------------------------------------------------------
# Additional Vercel WSGI fix: ensure header names are uppercased
# ---------------------------------------------------------------------------
import io  # noqa: E402


class _VercelWsgiFix:
    """Thin wrapper that normalises a few WSGI environ keys that Vercel's
    Python runtime sometimes leaves in the wrong case, and guarantees that
    ``wsgi.input`` is always a readable ``BytesIO`` for body-bearing methods.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Normalise HTTP headers that may arrive lowercase from Vercel.
        for raw in ("content-type", "content-length", "authorization"):
            wsgi_key = "HTTP_" + raw.upper().replace("-", "_") if raw != "content-type" and raw != "content-length" else raw.upper().replace("-", "_")
            if raw in environ and wsgi_key not in environ:
                environ[wsgi_key] = environ.pop(raw)

        # Guarantee wsgi.input exists for methods that carry a body.
        method = environ.get("REQUEST_METHOD", "").upper()
        if method in ("POST", "PUT", "PATCH") and environ.get("wsgi.input") is None:
            length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            environ["wsgi.input"] = io.BytesIO(b"" if length == 0 else b"\x00" * length)

        return self.app(environ, start_response)


application = _VercelWsgiFix(_django_app)