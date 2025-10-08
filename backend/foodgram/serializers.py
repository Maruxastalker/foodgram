from collections import Counter

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import transaction
from djoser.serializers import UserSerializer as DjoserUserSerializer
from drf_extra_fields.fields import Base64ImageField
from rest_framework import serializers
from rest_framework.serializers import ValidationError

from .models import (
    Error,
    Favorite,
    Ingredient,
    MinValue,
    Recipe,
    RecipeIngredient,
    ShoppingCart,
    Subscription,
    Tag,
)


User = get_user_model()


class UserSerializer(DjoserUserSerializer):
    is_subscribed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (*DjoserUserSerializer.Meta.fields, 'avatar', 'is_subscribed')

    def get_is_subscribed(self, author):
        user = self.context.get('request').user
        return (
            user.is_authenticated
            and Subscription.objects.filter(
                author=author, subscriber=user
            ).exists()
        )


class UserCreateSerializer(DjoserUserSerializer):
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
                limit_value=MinValue.AMOUNT, message=Error.AMOUNT
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
        source='recipeingredients', many=True
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

    def get_is_in_shopping_cart(self, recipe):
        user = self.context.get('request').user
        return (
            user.is_authenticated
            and ShoppingCart.objects.filter(user=user, recipe=recipe).exists()
        )

    def get_is_favorited(self, recipe):
        user = self.context.get('request').user
        return (
            user.is_authenticated
            and Favorite.objects.filter(user=user, recipe=recipe).exists()
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
                limit_value=MinValue.COOKING_TIME,
                message=Error.COOKING_TIME
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

    def validate_ingredients(self, value):
        if not value:
            raise ValidationError(Error.NO_INGREDIENTS)

        ingredient_ids = [item['ingredient'].id for item in value]
        duplicates = [item for item, count in Counter(
            ingredient_ids
        ).items() if count > 1]
        if duplicates:
            raise ValidationError(Error.DUPLICATES.format(duplicates))

        # Проверка существования ингредиентов
        existing_ids = set(Ingredient.objects.filter(
            id__in=ingredient_ids
        ).values_list('id', flat=True))
        missing_ids = set(ingredient_ids) - existing_ids
        if missing_ids:
            raise ValidationError(
                f"Ингредиенты с id {missing_ids} не существуют"
            )

        # Проверка количества ингредиентов
        for ingredient_data in value:
            if ingredient_data['amount'] < 1:
                raise ValidationError(
                    "Количество ингредиента должно быть не менее 1"
                )

        return value

    def validate_tags(self, value):
        if not value:
            raise ValidationError(Error.NO_TAGS)

        tag_ids = [tag.id for tag in value]
        duplicates = [item for item, count in Counter(
            tag_ids
        ).items() if count > 1]
        if duplicates:
            raise ValidationError(Error.DUPLICATES.format(duplicates))

        # Проверка существования тегов
        existing_ids = set(
            Tag.objects.filter(id__in=tag_ids).values_list('id', flat=True)
        )
        missing_ids = set(tag_ids) - existing_ids
        if missing_ids:
            raise ValidationError(f"Теги с id {missing_ids} не существуют")

        return value

    def validate(self, data):
        # Дополнительная валидация на уровне всего объекта
        if 'ingredients' not in data or not data['ingredients']:
            raise ValidationError({'ingredients': Error.NO_INGREDIENTS})

        if 'tags' not in data or not data['tags']:
            raise ValidationError({'tags': Error.NO_TAGS})

        return data

    @transaction.atomic
    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients')
        tags_data = validated_data.pop('tags')

        recipe = Recipe.objects.create(**validated_data)
        recipe.tags.set(tags_data)

        recipe_ingredients = []
        for ingredient_data in ingredients_data:
            recipe_ingredients.append(
                RecipeIngredient(
                    recipe=recipe,
                    ingredient=ingredient_data['ingredient'],
                    amount=ingredient_data['amount']
                )
            )

        RecipeIngredient.objects.bulk_create(recipe_ingredients)
        return recipe

    @transaction.atomic
    def update(self, instance, validated_data):
        ingredients_data = validated_data.pop('ingredients', None)
        tags_data = validated_data.pop('tags', None)

        instance = super().update(instance, validated_data)

        if tags_data is not None:
            instance.tags.set(tags_data)

        if ingredients_data is not None:
            instance.ingredients.clear()
            recipe_ingredients = []
            for ingredient_data in ingredients_data:
                recipe_ingredients.append(
                    RecipeIngredient(
                        recipe=instance,
                        ingredient=ingredient_data['ingredient'],
                        amount=ingredient_data['amount']
                    )
                )
            RecipeIngredient.objects.bulk_create(recipe_ingredients)

        return instance


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

    def get_recipes(self, user):
        return ShortRecipeSerializer(
            user.recipes.all()[
                : int(
                    self.context.get('request').GET.get(
                        'recipes_limit', 10**10
                    )
                )
            ],
            context=self.context,
            many=True,
        ).data
