from django.contrib import admin
from django.urls import path, include

from foodgram.views import recipe_shared_link

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('foodgram.urls')),
    path('short/<slug>/', recipe_shared_link, name='short_url'),
]
