from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Allow dict lookups with variable keys in templates: {{ dict|get_item:key }}"""
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)
