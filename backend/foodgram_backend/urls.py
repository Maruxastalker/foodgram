from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from foodgram.views import recipe_shared_link

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('foodgram.urls')),
    path('s/<slug>/', recipe_shared_link, name='short_url'),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )
