from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from foodgram.views import (
    CustomUserViewSet, 
    IngredientViewSet, 
    TagViewSet, 
    RecipeViewSet,
    TokenViewSet
)

router = DefaultRouter()
router.register(r'users', CustomUserViewSet, basename='users')
router.register(r'ingredients', IngredientViewSet, basename='ingredients')
router.register(r'tags', TagViewSet, basename='tags')
router.register(r'recipes', RecipeViewSet, basename='recipes')

urlpatterns = [ 
    path('', include(router.urls)),
    path('auth/', include('djoser.urls.authtoken')),
]   