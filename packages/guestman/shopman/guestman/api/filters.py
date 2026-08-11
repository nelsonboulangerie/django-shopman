from __future__ import annotations

from django_filters import rest_framework as filters
from shopman.guestman.models import Customer


class CustomerFilter(filters.FilterSet):
    price_tier = filters.CharFilter(field_name="price_tier__ref")

    class Meta:
        model = Customer
        fields = {
            "is_active": ["exact"],
        }
