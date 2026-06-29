"""
WSGI config for CrestPoint Credit project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crestpoint_credit.settings")

application = get_wsgi_application()
