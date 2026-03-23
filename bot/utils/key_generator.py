import secrets
import string


def generate_key(length: int = 16) -> str:
    """Генерирует уникальный ключ доступа в формате XXXX-XXXX-XXXX-XXXX."""
    alphabet = string.ascii_uppercase + string.digits
    segments = []
    for _ in range(4):
        segment = "".join(secrets.choice(alphabet) for _ in range(length // 4))
        segments.append(segment)
    return "-".join(segments)
