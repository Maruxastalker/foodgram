from django.utils import timezone
from io import BytesIO

TIME_FORMAT = '%d-%m-%Y %H:%M'


def make_shopping_cart_file(ingredients, recipes):
    """
    Создает файл списка покупок в памяти.

    Args:
        ingredients: QuerySet ингредиентов с аннотацией total_amount
        recipes: QuerySet рецептов
    """
    current_time = timezone.now().strftime(TIME_FORMAT)

    # Форматируем ингредиенты
    ingredients_list = []
    for index, item in enumerate(ingredients, start=1):
        ingredient_name = item["ingredient__name"].capitalize()
        measurement_unit = item["ingredient__measurement_unit"]
        total_amount = item["total_amount"]

        ingredients_list.append(
            f'{index}. {ingredient_name} ({measurement_unit}) - {total_amount}'
        )

    # Форматируем рецепты
    recipes_list = []
    for index, recipe in enumerate(recipes, start=1):
        recipes_list.append(f'{index}. {recipe.name}')

    # Собираем содержимое
    content_lines = [
        f'Дата и время: {current_time}',
        '',
        'Список покупок:',
        *ingredients_list,
        '',
        'Список рецептов:',
        *recipes_list,
        ''
    ]

    content = '\n'.join(content_lines)

    # Создаем файл в памяти
    file_buffer = BytesIO()
    file_buffer.write(content.encode('utf-8'))
    file_buffer.seek(0)

    return file_buffer
