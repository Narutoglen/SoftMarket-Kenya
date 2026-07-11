"""SEO endpoints: sitemaps + robots.txt for SoftMarket Kenya.

- StaticViewSitemap covers the server-rendered marketing pages.
- BlogSitemap covers only PUBLISHED posts (drafts are excluded).
- robots_txt view points crawlers at the sitemap.
"""
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.urls import reverse

from .models import BlogPost


class StaticViewSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return ["marketplace:home", "marketplace:work", "marketplace:about",
                "marketplace:process", "marketplace:blog_list"]

    def location(self, item):
        return reverse(item)


class BlogSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED)

    def lastmod(self, item):
        return item.published_at or item.updated_at


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
        f"Sitemap: {request.build_absolute_uri(reverse('marketplace:sitemap'))}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
