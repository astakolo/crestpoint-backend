"""
ASGI config for CrestPoint Credit project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crestpoint_credit.settings")

application = get_asgi_application()
