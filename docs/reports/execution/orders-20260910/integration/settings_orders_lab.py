from config.settings_test import *  # noqa: F403 — lab inherits the hermetic test adapters

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
