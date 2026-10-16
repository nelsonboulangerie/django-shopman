from django.urls import include, path

urlpatterns = [path("health/", include("shopman.watchman.urls"))]
