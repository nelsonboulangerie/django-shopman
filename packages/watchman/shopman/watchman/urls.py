from django.urls import path

from shopman.watchman.views import LiveView, ReadyView, StatusView

app_name = "watchman"

urlpatterns = [
    path("live/", LiveView.as_view(), name="live"),
    path("ready/", ReadyView.as_view(), name="ready"),
    path("status/", StatusView.as_view(), name="status"),
]
