from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def stars(value, size=None):
    """Render 5 star icons based on numerical rating."""
    try:
        val = float(value or 0)
    except (ValueError, TypeError):
        val = 0.0

    full = int(val)
    half = 1 if (val - full) >= 0.5 else 0
    empty = max(0, 5 - full - half)
    style = f' style="font-size:{size}px"' if size else ''

    html = f'<span class="rating-stars"{style}>'
    html += '<i class="bi bi-star-fill" style="color:var(--gold,#d4a373)"></i> ' * full
    html += '<i class="bi bi-star-half" style="color:var(--gold,#d4a373)"></i> ' * half
    html += '<i class="bi bi-star" style="color:rgba(23,19,12,.2)"></i> ' * empty
    html += '</span>'
    return mark_safe(html)


@register.simple_tag(takes_context=True)
def add_query(context, **kwargs):
    """Preserve current GET query parameters while updating/adding new ones."""
    request = context.get("request")
    if not request:
        return "?"
    query = request.GET.copy()
    for key, value in kwargs.items():
        if value == "" or value is None:
            query.pop(key, None)
        else:
            query[key] = str(value)
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.filter(name="lookup")
def lookup(d, key):
    """Look up a key in a dictionary."""
    if isinstance(d, dict):
        return d.get(key, key)
    return ""


@register.filter(name="percent_of")
def percent_of(value, maximum):
    """Calculate percentage (0-100) for chart heights."""
    try:
        val = float(value or 0)
        max_val = float(maximum or 0)
        if max_val <= 0:
            return 0
        return min(100, max(0, round((val / max_val) * 100)))
    except (ValueError, TypeError, ZeroDivisionError):
        return 0
