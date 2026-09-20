"""The Jinja environment the pages render through.

One instance, shared. Jinja autoescapes here, which is what keeps a user named
with an angle bracket from breaking the page that lists them.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
