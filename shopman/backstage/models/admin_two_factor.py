"""Durable individual Admin 2FA policy, independent of remaining devices/codes."""
from django.conf import settings
from django.db import models


class AdminTwoFactorEnrollment(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="admin_two_factor_enrollment")
    enrolled_at = models.DateTimeField(auto_now_add=True)
