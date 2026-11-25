from django import template

register = template.Library()

@register.filter
def replace_underscore(value):
    """Заменяет все подчеркивания на пробелы"""
    if not isinstance(value, str):
        return value
    return value.replace('_', ' ')


@register.filter
def get_item(mapping, key):
    """Значение словаря по ключу в шаблоне."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None
