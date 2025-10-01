from django_filters.rest_framework import FilterSet
from django_filters.rest_framework.filters import (
    BooleanFilter,
    ModelMultipleChoiceFilter,
)
from rest_framework.filters import SearchFilter

from .models import Recipe, Tag


class IngredientFilter(SearchFilter):
    search_param = 'name'


class RecipeFilterSet(FilterSet):
    tags = ModelMultipleChoiceFilter(
        field_name='tags__slug',
        to_field_name='slug',
        queryset=Tag.objects.all(),
    )
    is_favorited = BooleanFilter(method='get_is_favorited')
    is_in_shopping_cart = BooleanFilter(method='get_is_in_shopping_cart')

    class Meta:
        model = Recipe
        fields = ('tags', 'author', 'is_favorited', 'is_in_shopping_cart')

    def get_is_favorited(self, recipes, name, value):
        if self.request.user.is_authenticated and value:
            return recipes.filter(favorites__user=self.request.user)
        return recipes

    def get_is_in_shopping_cart(self, recipes, name, value):
        if self.request.user.is_authenticated and value:
            return recipes.filter(shoppingcarts__user=self.request.user)
        return recipes
