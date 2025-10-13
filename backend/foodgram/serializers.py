from collections import Counter

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import transaction
from djoser.serializers import UserSerializer as DjoserSerializer
from drf_extra_fields.fields import Base64ImageField
from rest_framework import serializers
from rest_framework.serializers import ValidationError

from .models import (
    Favorite,
    Ingredient,
    Recipe,
    RecipeIngredient,
    ShoppingCart,
    Subscription,
    Tag,
)


User = get_user_model()


class UserSerializer(DjoserSerializer):
    is_subscribed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            *DjoserSerializer.Meta.fields,
            'avatar',
            'is_subscribed'
        )

    def get_is_subscribed(self, author_obj):
        current_user = self.context.get('request').user
        return (
            current_user.is_authenticated
            and Subscription.objects.filter(
                author=author_obj, subscriber=current_user
            ).exists()
        )


class UserCreateSerializer(DjoserSerializer):
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=True, max_length=150)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'password'
        )
        extra_kwargs = {
            'password': {'write_only': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
        }


class AvatarSerializer(serializers.ModelSerializer):
    avatar = Base64ImageField()

    class Meta:
        model = User
        fields = ('avatar',)


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = '__all__'


class RecipeIngredientSerializer(serializers.ModelSerializer):
    id = serializers.PrimaryKeyRelatedField(
        queryset=Ingredient.objects.all(), source='ingredient'
    )
    name = serializers.ReadOnlyField(source='ingredient.name')
    measurement_unit = serializers.ReadOnlyField(
        source='ingredient.measurement_unit',
    )
    amount = serializers.IntegerField(
        validators=[
            MinValueValidator(
                limit_value=1,
                message='Должно быть не менее 1 единицы'
            )
        ]
    )

    class Meta:
        model = RecipeIngredient
        fields = ('id', 'name', 'measurement_unit', 'amount')


class ReadRecipeSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)
    author = UserSerializer(read_only=True)
    ingredients = RecipeIngredientSerializer(
        source='recipe_ingredients', many=True
    )
    is_in_shopping_cart = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = (
            'id',
            'tags',
            'author',
            'ingredients',
            'name',
            'image',
            'text',
            'cooking_time',
            'is_in_shopping_cart',
            'is_favorited',
        )
        read_only_fields = (
            'id', 'author', 'is_in_shopping_cart', 'is_favorited'
        )

    def get_is_in_shopping_cart(self, recipe_obj):
        current_user = self.context.get('request').user
        return (
            current_user.is_authenticated
            and ShoppingCart.objects.filter(
                user=current_user, recipe=recipe_obj
            ).exists()
        )

    def get_is_favorited(self, recipe_obj):
        current_user = self.context.get('request').user
        return (
            current_user.is_authenticated
            and Favorite.objects.filter(
                user=current_user, recipe=recipe_obj
            ).exists()
        )


class WriteRecipeSerializer(serializers.ModelSerializer):
    ingredients = RecipeIngredientSerializer(many=True, required=True)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True,
        required=True
    )
    image = Base64ImageField(required=True)
    cooking_time = serializers.IntegerField(
        validators=[
            MinValueValidator(
                limit_value=1,
                message='Минимальное время: 1 минута'
            )
        ],
        required=True
    )

    class Meta:
        model = Recipe
        fields = (
            'id',
            'tags',
            'author',
            'ingredients',
            'name',
            'image',
            'text',
            'cooking_time',
        )
        read_only_fields = ('id', 'author')

    def validate_ingredients(self, components_data):
        if not components_data:
            raise ValidationError('Требуются ингредиенты для рецепта')

        ingredient_identifiers = [
            item['ingredient'].id for item in components_data
        ]
        duplicate_items = [item_id for item_id, count in Counter(
            ingredient_identifiers
        ).items() if count > 1]

        if duplicate_items:
            raise ValidationError(
                f'Повторяющиеся ингредиенты: {duplicate_items}'
            )

        exist_ingredient = set(Ingredient.objects.filter(
            id__in=ingredient_identifiers
        ).values_list('id', flat=True))

        missing_ingredient_ids = set(ingredient_identifiers) - exist_ingredient
        if missing_ingredient_ids:
            raise ValidationError(
                f"Не найдены ингредиенты с ID: {missing_ingredient_ids}"
            )

        for component_item in components_data:
            if component_item['amount'] < 1:
                raise ValidationError(
                    "Количество должно быть положительным числом"
                )

        return components_data

    def validate_tags(self, tags_data):
        if not tags_data:
            raise ValidationError('Необходимо указать теги')

        tag_identifiers = [tag.id for tag in tags_data]
        duplicate_tags = [tag_id for tag_id, count in Counter(
            tag_identifiers
        ).items() if count > 1]

        if duplicate_tags:
            raise ValidationError(f'Повторяющиеся теги: {duplicate_tags}')

        existing_tag_ids = set(
            Tag.objects.filter(
                id__in=tag_identifiers
            ).values_list('id', flat=True)
        )
        missing_tag_ids = set(tag_identifiers) - existing_tag_ids
        if missing_tag_ids:
            raise ValidationError(f"Не найдены теги с ID: {missing_tag_ids}")

        return tags_data

    def validate(self, data_dict):
        if 'ingredients' not in data_dict or not data_dict['ingredients']:
            raise ValidationError({'ingredients': 'Добавьте ингредиенты'})

        if 'tags' not in data_dict or not data_dict['tags']:
            raise ValidationError({'tags': 'Укажите теги'})

        return data_dict

    @transaction.atomic
    def create(self, validated_data_dict):
        components_info = validated_data_dict.pop('ingredients')
        tags_info = validated_data_dict.pop('tags')

        new_recipe = Recipe.objects.create(**validated_data_dict)
        new_recipe.tags.set(tags_info)

        recipe_component_list = []
        for component_info in components_info:
            recipe_component_list.append(
                RecipeIngredient(
                    recipe=new_recipe,
                    ingredient=component_info['ingredient'],
                    amount=component_info['amount']
                )
            )

        RecipeIngredient.objects.bulk_create(recipe_component_list)
        return new_recipe

    @transaction.atomic
    def update(self, recipe_instance, validated_data_dict):
        components_info = validated_data_dict.pop('ingredients', None)
        tags_info = validated_data_dict.pop('tags', None)

        updated_recipe = super().update(recipe_instance, validated_data_dict)

        if tags_info is not None:
            updated_recipe.tags.set(tags_info)

        if components_info is not None:
            updated_recipe.ingredients.clear()
            recipe_component_list = []
            for component_info in components_info:
                recipe_component_list.append(
                    RecipeIngredient(
                        recipe=updated_recipe,
                        ingredient=component_info['ingredient'],
                        amount=component_info['amount']
                    )
                )
            RecipeIngredient.objects.bulk_create(recipe_component_list)

        return updated_recipe


class ShortRecipeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipe
        fields = (
            'id',
            'name',
            'image',
            'cooking_time',
        )


class ReadSubscriptionSerializer(UserSerializer):
    recipes = serializers.SerializerMethodField()
    recipes_count = serializers.ReadOnlyField(source='recipes.count')

    class Meta(UserSerializer.Meta):
        fields = (*UserSerializer.Meta.fields, 'recipes', 'recipes_count')

    def get_recipes(self, user_obj):
        limit_value = self.context.get('request').GET.get(
            'recipes_limit', 10**10
        )
        return ShortRecipeSerializer(
            user_obj.recipes.all()[
                : int(limit_value)
            ],
            context=self.context,
            many=True,
        ).data
