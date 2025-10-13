from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models, IntegrityError
from django.db.models.constraints import UniqueConstraint
from django.core.exceptions import ValidationError
from django.urls import reverse
from random import choices
from string import ascii_letters, digits

from .validators import validate_username


class RecipeValidationError(Exception):
    """Кастомное исключение для ошибок валидации рецепта."""
    pass


class DuplicateRecipeError(Exception):
    """Кастомное исключение для дублирующихся рецептов."""
    pass


class User(AbstractUser):
    """Модель пользователя с кастомными полями."""

    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']
    USERNAME_FIELD = 'email'

    email = models.EmailField(
        verbose_name='Эл. почта',
        max_length=254,
        unique=True,
    )
    username = models.CharField(
        verbose_name='Уникальный юзернейм',
        max_length=150,
        unique=True,
        validators=(validate_username,),
    )
    first_name = models.CharField(
        verbose_name='Имя',
        max_length=150
    )
    last_name = models.CharField(
        verbose_name='Фамилия',
        max_length=150
    )
    avatar = models.ImageField(
        verbose_name='Фото профиля',
        upload_to=settings.AVATARS_PATH,
        null=True,
        blank=True,
    )

    class Meta(AbstractUser.Meta):
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ('username',)

    def __str__(self) -> str:
        return self.username

    @property
    def is_subscribed(self):
        """Проверка, подписан ли текущий пользователь на этого пользователя."""
        if hasattr(self, '_is_subscribed'):
            return self._is_subscribed
        return False

    @is_subscribed.setter
    def is_subscribed(self, value):
        """Устанавливает флаг подписки."""
        self._is_subscribed = value


class Subscription(models.Model):
    """Модель подписки пользователей друг на друга."""

    subscriber = models.ForeignKey(
        to=User,
        verbose_name='Подписчик',
        related_name='subscriptions',
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        to=User,
        verbose_name='Автор',
        related_name='authors',
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(
        verbose_name='Дата подписки',
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'Подписка'
        verbose_name_plural = 'Подписки'
        ordering = ('-created_at',)
        constraints = (
            UniqueConstraint(
                fields=('subscriber', 'author'),
                name='unique_user_subscription'
            ),
        )

    def clean(self):
        """Валидация подписки."""
        if self.subscriber == self.author:
            raise ValidationError('Нельзя подписаться на собственный аккаунт')

    def save(self, *args, **kwargs):
        """Сохраняет подписку с валидацией."""
        try:
            self.full_clean()
            super().save(*args, **kwargs)
        except ValidationError as e:
            if 'subscriber' in e.message_dict and 'author' in e.message_dict:
                raise IntegrityError("Subscription already exists")
            raise e

    def __str__(self) -> str:
        return f'{self.subscriber} -> {self.author}'


class Tag(models.Model):
    """Модель тегов для рецептов."""

    name = models.CharField(
        verbose_name='Название',
        max_length=32,
        unique=True,
    )
    slug = models.SlugField(
        verbose_name='Идентификатор',
        max_length=32,
        unique=True,
    )
    color = models.CharField(
        verbose_name='Цвет',
        max_length=7,
        default='#ffffff',
        help_text='Цвет в HEX-формате (например, #FF0000)'
    )

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'
        default_related_name = 'tags'
        ordering = ('name',)

    def __str__(self) -> str:
        return self.name

    def clean(self):
        """Валидация тега."""
        if self.color and not self.color.startswith('#'):
            raise ValidationError(
                {'color': 'Цвет должен быть в HEX-формате (#FFFFFF)'}
            )


class Ingredient(models.Model):
    """Модель ингредиентов для рецептов."""

    name = models.CharField(
        verbose_name='Название',
        max_length=128,
    )
    measurement_unit = models.CharField(
        verbose_name='Ед. измерения',
        max_length=64,
    )

    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Продукты'
        default_related_name = 'ingredients'
        ordering = ('name',)
        constraints = [
            UniqueConstraint(
                fields=['name', 'measurement_unit'],
                name='unique_ingredient'
            )
        ]

    def __str__(self):
        return f'{self.name}, {self.measurement_unit}'


class Recipe(models.Model):
    """Основная модель рецептов."""

    MAX_GENERATION_ATTEMPTS = 30
    SHORT_CODE_CHARS = ascii_letters + digits

    name = models.CharField(
        verbose_name='Название',
        max_length=256,
    )
    author = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        verbose_name='Автор',
        related_name='recipes'
    )
    image = models.ImageField(
        verbose_name='Изображение',
        upload_to=settings.RECIPES_IMAGES_PATH,
    )
    text = models.TextField(verbose_name='Описание')
    cooking_time = models.PositiveIntegerField(
        verbose_name='Время приготовления (в минутах)',
        validators=[
            MinValueValidator(
                limit_value=1,
                message='Мин. время приготовления: 1 мин.',
            )
        ],
    )
    tags = models.ManyToManyField(
        to=Tag,
        verbose_name='Теги',
        related_name='recipes'
    )
    ingredients = models.ManyToManyField(
        to=Ingredient,
        through='RecipeIngredient',
        verbose_name='Продукты',
        related_name='recipes'
    )
    short_url_code = models.SlugField(
        verbose_name='Код рецепта',
        max_length=6,
        unique=True,
        blank=True,
    )
    pub_date = models.DateTimeField(
        verbose_name='Дата публикации',
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'Рецепт'
        verbose_name_plural = 'Рецепты'
        default_related_name = 'recipes'
        ordering = ('-pub_date',)
        indexes = [
            models.Index(fields=['pub_date']),
            models.Index(fields=['author', 'pub_date']),
        ]

    @staticmethod
    def generate_short():
        """Создает уникальный короткий код для URL."""
        attempts = 0
        while attempts < Recipe.MAX_GENERATION_ATTEMPTS:
            code = ''.join(choices(Recipe.SHORT_CODE_CHARS, k=6))
            if not Recipe.objects.filter(short_url_code=code).exists():
                return code
            attempts += 1
        raise RuntimeError('Превышено количество попыток создания ссылки.')

    def clean(self):
        """Валидация рецепта перед сохранением."""
        super().clean()

        if not self.image:
            raise ValidationError(
                {'image': 'Изображение обязательно для загрузки'}
            )

        if self.cooking_time < 1:
            raise ValidationError({
                'cooking_time': 'Мин. время приготовления: 1 мин.'
            })

    def validate_ingredients(self, ingredients_data):
        """Валидирует данные ингредиентов."""
        if not ingredients_data:
            raise RecipeValidationError(
                'Список ингредиентов не может быть пустым'
            )

        if not isinstance(ingredients_data, list):
            raise RecipeValidationError("Ingredients data must be a list")

        ingredient_ids = []
        for ingredient in ingredients_data:
            # Проверяем структуру данных
            if not isinstance(ingredient, dict):
                raise RecipeValidationError(
                    "Each ingredient must be a dictionary"
                )

            ingredient_id = ingredient.get('id')
            amount = ingredient.get('amount')

            # Проверяем обязательные поля
            if not ingredient_id:
                raise RecipeValidationError("Ingredient ID is required")

            if amount is None:
                raise RecipeValidationError("Ingredient amount is required")

            # Проверяем тип и значение amount
            try:
                amount = int(amount)
            except (TypeError, ValueError):
                raise RecipeValidationError("Amount must be a valid integer")

            if amount < 1:
                raise RecipeValidationError(
                    'Количество ингредиента должно быть положительным числом'
                )

            ingredient_ids.append(ingredient_id)

        # Проверяем дубликаты
        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise RecipeValidationError('Обнаружены повторяющиеся ингредиенты')

    def validate_tags(self, tags_data):
        """Валидирует данные тегов."""
        if not tags_data:
            raise RecipeValidationError('Список тегов не может быть пустым')

        if len(tags_data) != len(set(tags_data)):
            raise RecipeValidationError('Обнаружены повторяющиеся теги')

    def add_ingredients(self, ingredients_data):
        """Добавляет ингредиенты к рецепту."""
        self.validate_ingredients(ingredients_data)

        recipe_ingredients = []
        for ingredient_data in ingredients_data:
            recipe_ingredients.append(
                RecipeIngredient(
                    recipe=self,
                    ingredient_id=ingredient_data['id'],
                    amount=ingredient_data['amount']
                )
            )
        RecipeIngredient.objects.bulk_create(recipe_ingredients)

    def add_tags(self, tags_data):
        """Добавляет теги к рецепту."""
        self.validate_tags(tags_data)
        self.tags.set(tags_data)

    def is_favorited_by(self, user):
        """Проверяет, добавлен ли рецепт в избранное пользователем."""
        if not user.is_authenticated:
            return False
        return self.favorites.filter(user=user).exists()

    def is_in_shopping_cart_of(self, user):
        """Проверяет, добавлен ли рецепт в корзину пользователем."""
        if not user.is_authenticated:
            return False
        return self.shoppingcarts.filter(user=user).exists()

    def save(self, *args, **kwargs):
        """Сохраняет рецепт с генерацией короткого кода и валидацией."""
        if not self.short_url_code:
            self.short_url_code = self.generate_short()

        attempts = 0
        while attempts < self.MAX_GENERATION_ATTEMPTS:
            try:
                # Валидация и сохранение
                self.full_clean()
                super().save(*args, **kwargs)
                return
            except IntegrityError as e:
                if 'short_url_code' in str(e):
                    attempts += 1
                    self.short_url_code = self.generate_short()
                else:
                    raise e
            except ValidationError as e:
                raise e

        raise RuntimeError('Превышено количество попыток создания ссылки.')

    @classmethod
    def get_by_short_code(cls, code):
        """Безопасное получение рецепта по короткому коду."""
        try:
            return cls.objects.get(short_url_code=code)
        except cls.DoesNotExist:
            return None

    def get_absolute_url(self):
        """Генерирует абсолютный URL для рецепта."""
        if not self.short_url_code:
            # Если код не установлен, генерируем его
            self.short_url_code = self.generate_short()
            self.save(update_fields=['short_url_code'])
        return reverse('recipes:short_link', args=[self.short_url_code])

    def __str__(self):
        return self.name


class RecipeIngredient(models.Model):
    """Промежуточная модель для связи рецептов и ингредиентов."""

    recipe = models.ForeignKey(
        to=Recipe,
        on_delete=models.CASCADE,
        verbose_name='Рецепт',
        related_name='recipe_ingredients'
    )
    ingredient = models.ForeignKey(
        to=Ingredient,
        on_delete=models.CASCADE,
        verbose_name='Продукт',
        related_name='recipe_ingredients'
    )
    amount = models.PositiveIntegerField(
        verbose_name='Мера',
        validators=[
            MinValueValidator(
                limit_value=1,
                message='Минимальное количество ингредиента: 1 ед.',
            )
        ],
    )

    class Meta:
        default_related_name = 'recipe_ingredients'
        ordering = ('recipe', 'ingredient')
        constraints = (
            UniqueConstraint(
                fields=('recipe', 'ingredient'),
                name='unique_recipe_ingredient_combo'
            ),
        )
        verbose_name = 'Продукт рецепта'
        verbose_name_plural = 'Продукты рецепта'

    def clean(self):
        """Валидация количества ингредиента."""
        if self.amount < 1:
            raise ValidationError(
                {'amount': 'Минимальное количество ингредиента: 1 ед.'}
            )

    def __str__(self) -> str:
        return f'{self.recipe} - {self.ingredient} ({self.amount})'


class BaseUserRecipeModel(models.Model):
    """Базовая модель для связей пользователь-рецепт."""

    user = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        verbose_name='Пользователь',
    )
    recipe = models.ForeignKey(
        to=Recipe,
        on_delete=models.CASCADE,
        verbose_name='Рецепт',
    )
    created_at = models.DateTimeField(
        verbose_name='Дата добавления',
        auto_now_add=True
    )

    class Meta:
        abstract = True
        ordering = ('-created_at',)

    def clean(self):
        """Базовая валидация для связей пользователь-рецепт."""
        if not self.user_id:
            raise ValidationError("User is required")
        if not self.recipe_id:
            raise ValidationError("Recipe is required")

        # Проверяем существование рецепта
        if not Recipe.objects.filter(id=self.recipe_id).exists():
            raise ValidationError("Recipe does not exist")

    def save(self, *args, **kwargs):
        """Сохраняет с валидацией."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user} - {self.recipe}'


class Favorite(BaseUserRecipeModel):
    """Модель для избранных рецептов пользователя."""

    class Meta(BaseUserRecipeModel.Meta):
        verbose_name = 'Избранное'
        verbose_name_plural = 'Избранные рецепты'
        default_related_name = 'favorites'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'recipe'],
                name='unique_favorite_recipe',
            ),
        ]


class ShoppingCart(BaseUserRecipeModel):
    """Модель для корзины покупок пользователя."""

    class Meta(BaseUserRecipeModel.Meta):
        verbose_name = 'Корзина покупок'
        verbose_name_plural = 'Корзины покупок'
        default_related_name = 'shoppingcarts'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'recipe'],
                name='unique_shopping_cart_recipe',
            ),
        ]
