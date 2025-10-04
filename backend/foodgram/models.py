from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator

from .validators import validate_username


class MinValue:
    COOKING_TIME = 1
    AMOUNT = 1


class Error:
    COOKING_TIME = f'Не менее {MinValue.COOKING_TIME} мин. приготовления'
    AMOUNT = f'Не менее {MinValue.AMOUNT} ед. ингредиента'
    ALREADY_IN_SHOPPING_CART = 'Рецепт уже есть в списке покупок'
    ALREADY_FAVORITED = 'Рецепт уже есть в избранном'
    NOT_IN_SHOPPING_CART = 'Рецепта нет в списке покупок'
    NOT_FAVORITED = 'Рецепта нет в избранном'
    ALREADY_SUBSCRIBED = 'Вы уже подписаны на этого автора'
    CANNOT_SUBSCRIBE_TO_YOURSELF = 'Нельзя подписаться на самого себя'
    DUPLICATES = 'Дубликаты: {}'
    NO_IMAGE = 'Поле "image" не может быть пустым'
    NOT_SUBSCRIBED = 'Вы не подписаны на этого автора'
    NO_TAGS = 'Нужен хотя бы один тег'
    NO_INGREDIENTS = 'Рецепт не может обойтись без продуктов'
    NOT_EXIST = 'Рецепт не существует'
    SHORT_URL_CODE = 'Не удалось сгенерировать уникальный код'
    SHORT_URL_CODE_GEN = (
        'Превышено количество попыток генерации short_url_code.'
    )


class CustomUser(AbstractUser):
    """Кастомная модель пользователя с аватаром"""
    email = models.EmailField(
        'email address',
        unique=True,
        help_text='Обязательное поле. 254 символа максимум.'
    )
    username = models.CharField(
        verbose_name='Уникальный юзернейм',
        max_length=150,
        unique=True,
        validators=(validate_username,),
    )
    avatar = models.ImageField(
        upload_to='users/avatars/',
        null=True,
        blank=True,
        verbose_name='Аватар',
        help_text='Загрузите изображение аватара'
    )
    first_name = models.CharField(
        'first name',
        max_length=150,
        blank=False,
        help_text='Обязательное поле. 150 символов максимум.'
    )
    last_name = models.CharField(
        'last name',
        max_length=150,
        blank=False,
        help_text='Обязательное поле. 150 символов максимум.'
    )

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.username


class Tag(models.Model):
    """Модель для тегов рецептов"""
    name = models.CharField(
        max_length=16,
        verbose_name='Название тега',
        help_text='Введите название тега (максимум 16 символов)'
    )
    slug = models.SlugField(
        unique=True,
        verbose_name='Уникальный идентификатор',
        help_text='Уникальный идентификатор для URL'
    )

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    """Модель для ингредиентов (продуктов)"""
    name = models.CharField(
        max_length=64,
        verbose_name='Название ингредиента',
        help_text='Введите название продукта (максимум 64 символа)'
    )
    measurement_unit = models.CharField(
        max_length=20,
        verbose_name='Единица измерения',
        help_text='Введите единицу измерения'
    )

    class Meta:
        verbose_name = 'Ингредиент'
        verbose_name_plural = 'Ингредиенты'

    def __str__(self):
        return f'{self.name} ({self.measurement_unit})'


class Recipe(models.Model):
    """Основная модель рецепта"""
    author = models.ForeignKey(
        CustomUser,
        related_name='recipe',
        on_delete=models.CASCADE,
        verbose_name='Автор рецепта',
        help_text='Пользователь, создавший рецепт'
    )
    name = models.CharField(
        max_length=32,
        verbose_name='Название рецепта',
        help_text='Введите название рецепта (максимум 32 символа)'
    )
    image = models.ImageField(
        upload_to='recipe/images/',
        null=True,
        default=None,
        verbose_name='Изображение рецепта',
        help_text='Загрузите фотографию готового блюда'
    )
    text = models.TextField(
        verbose_name='Описание рецепта',
        help_text='Подробное описание процесса приготовления',
    )
    ingredients = models.ManyToManyField(
        Ingredient,
        related_name='recipe',
        verbose_name='Ингредиенты',
        help_text='Выберите продукты для приготовления блюда',
        through='IngredientAmount'
    )
    tags = models.ManyToManyField(
        Tag,
        related_name='recipe',
        verbose_name='Теги',
        help_text='Выберите подходящие теги для рецепта'
    )
    cooking_time = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name='Время приготовления (в минутах)',
        help_text='Введите время приготовления в минутах (не менее 1 минуты)'
    )
    created = models.DateTimeField(
        auto_now_add=True, verbose_name='Дата создания'
    )

    class Meta:
        verbose_name = 'Рецепт'
        verbose_name_plural = 'Рецепты'
        ordering = ['-created']

    def __str__(self):
        return self.name


class IngredientAmount(models.Model):
    """Промежуточная модель для связи рецепта и ингредиента"""
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='ingredient_amounts'
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.CASCADE,
        related_name='ingredient_amounts'
    )
    amount = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
    )


class Favorite(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='favorites'
    )
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='favorites'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'recipe'],
                name='unique_favorite'
            )
        ]


class Subscription(models.Model):
    subscriber = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='subscriber'
    )
    author = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='subscribed_to'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['subscriber', 'author'],
                name='unique_subscription'
            ),
            models.CheckConstraint(
                check=~models.Q(subscriber=models.F('author')),
                name='prevent_self_subscription'
            )
        ]
        verbose_name = 'Подписка'
        verbose_name_plural = 'Подписки'

    def __str__(self):
        return f'{self.user} подписан на {self.author}'


class ShoppingCart(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='shopping_cart'
    )
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='shopping_cart'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'recipe'],
                name='unique_shopping_cart'
            )
        ]
        verbose_name = 'Список покупок'
        verbose_name_plural = 'Списки покупок'

    def __str__(self):
        return f'{self.user} - {self.recipe}'
