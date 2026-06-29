"""
Celery configuration for CrestPoint Credit.
Uses Redis as broker and result backend.
"""

import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crestpoint_credit.settings")

app = Celery("crestpoint_credit")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for verifying Celery is running."""
    print(f"Request: {self.request!r}")
