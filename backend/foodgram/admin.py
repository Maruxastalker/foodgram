from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Tag, Ingredient, Recipe


User = get_user_model()


class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = (
        'username',
        'email',
    )
    list_display_links = ('username', 'email')


class TagAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug'
    )

    list_editable = (
        'slug',
    )
    list_display_links = ('name',)


class IngredientAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'measurement_unit',
    )
    list_editable = (
        'measurement_unit',
    )
    search_fields = (
        'name',
    )
    list_display_links = ('name',)


class RecipeAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'author',
        'image',
        'text',
        'cooking_time'

    )
    list_editable = (
        'cooking_time',
    )
    search_fields = (
        'author',
        'name',
        'tag',
    )
    list_display_links = ('name',)


admin.site.register(Tag, TagAdmin)
admin.site.register(Ingredient, IngredientAdmin)
admin.site.register(Recipe, RecipeAdmin)
admin.site.register(User, CustomUserAdmin)
