import re
from django.core.exceptions import ValidationError


def validate_username(username):
    """Валидация имени пользователя."""

    ALLOWED_PATTERN = r'[\w.@+-]'
    BANNED_NAMES = {'me', 'admin', 'administrator', 'root', 'superuser'}

    invalid_chars = set(re.sub(ALLOWED_PATTERN, '', username))
    if invalid_chars:
        raise ValidationError(
            f'Недопустимые символы: {"".join(invalid_chars)}'
        )

    if username.lower() in {name.lower() for name in BANNED_NAMES}:
        raise ValidationError(f'Имя "{username}" запрещено')

    return username
