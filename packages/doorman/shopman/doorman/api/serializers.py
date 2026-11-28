from __future__ import annotations

from rest_framework import serializers


class RequestCodeSerializer(serializers.Serializer):
    target = serializers.CharField()
    delivery_method = serializers.ChoiceField(
        choices=["whatsapp", "sms", "email"],
        default="whatsapp",
        required=False,
    )

class RequestCodeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    code_id = serializers.CharField(allow_null=True)
    expires_at = serializers.CharField(allow_null=True)


class VerifyCodeSerializer(serializers.Serializer):
    target = serializers.CharField()
    code = serializers.CharField(max_length=6)


class VerifyCodeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    customer_id = serializers.UUIDField(allow_null=True)
    created_customer = serializers.BooleanField()


class AuthErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()
    error_code = serializers.CharField(required=False, allow_null=True)
    attempts_remaining = serializers.IntegerField(required=False, allow_null=True)
