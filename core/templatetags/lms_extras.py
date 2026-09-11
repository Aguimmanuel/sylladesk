"""Template helpers: size labels (FR-08), WAT timestamps (D-13), inline-SVG icons (UX-3)."""
from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

from core.utils import human_size

register = template.Library()

_ICONS = {
    "leaf": '<path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14zm0 0c2-4 5-7 9-9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "sun": '<circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 3v2.4M12 18.6V21M3 12h2.4M18.6 12H21M5.6 5.6l1.7 1.7M16.7 16.7l1.7 1.7M18.4 5.6l-1.7 1.7M7.3 16.7l-1.7 1.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "moon": '<path d="M20 13.5A8 8 0 1 1 10.5 4a6.5 6.5 0 0 0 9.5 9.5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    "flask": '<path d="M10 3h4M11 3v6l-5.2 8.7A2 2 0 0 0 7.5 21h9a2 2 0 0 0 1.7-3.3L13 9V3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "box": '<path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5v-9zM3.5 7.5 12 12l8.5-4.5M12 12v9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
}


@register.simple_tag
def icon(name: str, size: int = 18) -> str:
    path = _ICONS.get(name, _ICONS["leaf"])
    return mark_safe(
        f'<svg class="icon icon-{name}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'aria-hidden="true">{path}</svg>'
    )


@register.filter
def size_label(num_bytes) -> str:
    try:
        return human_size(int(num_bytes))
    except (TypeError, ValueError):
        return ""


@register.filter
def wat(value) -> str:
    """Any UTC timestamp -> '10 Sep 2026, 14:05 WAT' (D-13)."""
    if not value:
        return ""
    local = timezone.localtime(value)
    return f"{local:%d %b %Y, %H:%M} WAT"
