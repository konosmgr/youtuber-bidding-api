from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("auctions.urls")),
    path("silk/", include("silk.urls", namespace="silk")),  # Silk URLs
]
