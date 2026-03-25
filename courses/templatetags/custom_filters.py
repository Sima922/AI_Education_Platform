# custom_filters.py
from django import template
import re

register = template.Library()

@register.filter(name='dictget')
def dictget(dictionary, key):
    """
    Custom filter to safely get a value from a dictionary by key.
    Returns None if the input is not a dictionary or the key doesn't exist.
    """
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)

@register.filter(name='youtube_id')
def youtube_id(value):
    """
    Extracts YouTube ID from various URL formats.
    Supports:
    - Full URLs (https://www.youtube.com/watch?v=VIDEO_ID)
    - Short URLs (https://youtu.be/VIDEO_ID)
    - Embed URLs (https://www.youtube.com/embed/VIDEO_ID)
    - URLs with additional parameters or fragments
    - URLs with or without 'www' or 'https://'
    - Bare YouTube IDs (returns as-is if already an ID)
    """
    if not value:
        return ''

    # Regular expression to match YouTube video IDs
    regex = (
        r'(?:https?:\/\/)?'  # Optional protocol (http:// or https://)
        r'(?:www\.)?'         # Optional 'www.'
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)'  # URL patterns
        r'([a-zA-Z0-9_-]{11})'  # YouTube video ID (11 characters)
        r'(?:\?.*)?$'          # Optional query parameters
    )

    # Match the regex against the input value
    match = re.search(regex, value)

    # If a match is found, return the video ID
    if match:
        return match.group(1)

    # If the input is already a valid YouTube ID (11 characters), return it as-is
    if re.match(r'^[a-zA-Z0-9_-]{11}$', value):
        return value

    # If no match is found, return an empty string
    return ''

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using key."""
    return dictionary.get(key)

@register.filter
def add(value, arg):
    """Concatenate value and arg."""
    return f"{value}{arg}"

@register.filter
def get_dict_item(dictionary, key):
    """
    Custom filter to get a value from a dictionary by a partial key match.
    Returns the value of the first key that starts with the given key.
    Returns None if no match is found.
    """
    if not isinstance(dictionary, dict):
        return None
    for k in dictionary.keys():
        if k.startswith(key):
            return dictionary.get(k)
    return None