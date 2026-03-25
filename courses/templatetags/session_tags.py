from django import template

register = template.Library()

@register.simple_tag
def get_session_value(session, key):
    return session.get(key)