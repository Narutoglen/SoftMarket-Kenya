"""Template helpers for cache-busting static assets by modification time."""
import os

from django.conf import settings
from django.template import Library
from django.templatetags.static import static

register = Library()


@register.filter
def static_file_mtime(path):
    """Return a cache-busting query-string value based on file mtime.

    Usage: {% static 'marketplace/styles.css' %}?v={{ 'marketplace/styles.css'|static_file_mtime }}
    Django serves the file ignoring the query string, but the browser sees a new
    URL whenever the file changes on disk, forcing a re-fetch.
    """
    try:
        abs_path = os.path.join(settings.STATICFILES_DIRS[0], path)
        return int(os.path.getmtime(abs_path))
    except Exception:
        return "1"
