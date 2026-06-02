from django import template
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def article_body(value):
    if not value:
        return ""

    blocks = []
    paragraphs = str(value).replace("\r\n", "\n").split("\n\n")
    for paragraph in paragraphs:
        text = paragraph.strip()
        if not text:
            continue

        if text.startswith("## "):
            blocks.append(format_html("<h2>{}</h2>", text[3:].strip()))
            continue

        if text.startswith("### "):
            blocks.append(format_html("<h3>{}</h3>", text[4:].strip()))
            continue

        escaped = conditional_escape(text).replace("\n", "<br>")
        blocks.append(format_html("<p>{}</p>", mark_safe(escaped)))

    return mark_safe("".join(str(block) for block in blocks))
