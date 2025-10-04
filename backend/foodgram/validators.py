import re

from django.conf import settings
from django.core.exceptions import ValidationError


class Error:
    FORBIDDEN_USERNAME = 'Имя пользователя "{}" недопустимо!'
    INVALID_USERNAME_PATTERN = 'Обнаружены недопустимые символы: {}'


def validate_username(username):
    forbidden_symbols = re.sub(
        pattern=settings.USERNAME_PATTERN, repl='', string=username
    )
    if forbidden_symbols:
        forbidden_symbols = ''.join(set(forbidden_symbols))
        raise ValidationError(
            Error.INVALID_USERNAME_PATTERN.format(forbidden_symbols)
        )
    if username in settings.FORBIDDEN_USERNAMES:
        raise ValidationError(Error.FORBIDDEN_USERNAME.format(username))
    return username
