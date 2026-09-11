"""Native inventory administration; custody changes only through order services."""
from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.backstage.models import DeliveryDevice


@admin.register(DeliveryDevice)
class DeliveryDeviceAdmin(ModelAdmin):
    list_display = ("label", "identification", "active", "current_order")
    list_filter = ("active",)
    search_fields = ("label", "identification")
    fields = ("label", "identification", "active", "current_order")
    readonly_fields = ("current_order",)
    list_select_related = ("current_order",)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        # Never overwrite a dispatch that happened after the Admin form opened.
        if change:
            obj.save(update_fields=("label", "identification", "active"))
        else:
            super().save_model(request, obj, form, change)

        from shopman.shop.handlers._sse_emitters import emit_delivery_device_update

        emit_delivery_device_update()
