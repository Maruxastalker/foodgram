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
    ingredients = serializers.ListField(
        child=RecipeIngredientSerializer(),
        allow_empty=False,
        required=True,
    )
    tags = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(
            queryset=Tag.objects.all(),
        ),
        allow_empty=False,
        required=True,
    )
    image = Base64ImageField(allow_empty_file=False, required=True)
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
            'ingredients',
            'tags',
            'image',
            'name',
            'text',
            'cooking_time',
        )

    @staticmethod
    def _check_duplicates(array, field_name):
        counts = Counter(array)
        duplicates = {item for item, count in counts.items() if count > 1}
        if duplicates:
            raise ValidationError(
                {field_name: Error.DUPLICATES.format(duplicates)}
            )

    def validate_tags(self, tags):
        self._check_duplicates([tag.id for tag in tags], 'tags')
        return tags

    def validate_ingredients(self, ingredients):
        self._check_duplicates(
            [item['ingredient'].id for item in ingredients],
            'ingredients',
        )
        return ingredients

    def validate_image(self, image):
        if not image:
            raise ValidationError(Error.NO_IMAGE)
        return image

    @staticmethod
    def _save_ingredients(recipe, ingredients):
        RecipeIngredient.objects.bulk_create(
            RecipeIngredient(
                recipe=recipe,
                ingredient=ingredient['ingredient'],
                amount=ingredient['amount'],
            )
            for ingredient in ingredients
        )

    @transaction.atomic
    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients')
        recipe = super().create(validated_data)
        self._save_ingredients(recipe, ingredients_data)
        return recipe

    @transaction.atomic
    def update(self, recipe, validated_data):
        try:
            new_ingredients = validated_data.pop('ingredients')
            recipe.ingredients.clear()
            self._save_ingredients(recipe, new_ingredients)
        except KeyError:
            pass
        return super().update(recipe, validated_data)

    def to_representation(self, recipe):
        context = self.context or {}
        return ReadRecipeSerializer(
            recipe,
            context=context
        ).data


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
