"""ASGI config for the Shopman project.

Exposed as ``application`` so daphne (or any ASGI server) can serve the
django-eventstream SSE endpoints alongside regular Django views. WSGI
remains available for projects that don't need streaming.

Depois do boot, ``tune_gc_after_boot`` congela os objetos do boot e ajusta os
limiares do coletor (ver ``config/gc_tuning.py``; envs ``SHOPMAN_GC_FREEZE`` e
``SHOPMAN_GC_THRESHOLD``).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()

from config.gc_tuning import tune_gc_after_boot  # noqa: E402 - depois do django.setup()

tune_gc_after_boot()
