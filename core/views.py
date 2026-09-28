from django.shortcuts import render
from django.http import HttpResponse

def landing(request):
    """Render the FrameForge public landing page."""
    return render(request, "landing.html")

def custom_404(request, exception=None):
    """Custom 404 page for FrameForge."""
    return render(request, "404.html", status=404)

def robots_txt(request):
    """Serve robots.txt for search engines."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /dashboard/\n"
        "Disallow: /projects/\n"
        "Disallow: /project/\n"
        "Disallow: /admin-panel/\n"
        "Disallow: /asset-library/\n"
        "Disallow: /visuals/\n"
        "Disallow: /exports/\n\n"
        "Sitemap: " + request.build_absolute_uri('/sitemap.xml') + "\n"
    )
    return HttpResponse(content, content_type="text/plain")

def sitemap_xml(request):
    """Serve public sitemap.xml."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url>\n'
        '    <loc>' + request.build_absolute_uri('/') + '</loc>\n'
        '    <changefreq>weekly</changefreq>\n'
        '    <priority>1.0</priority>\n'
        '  </url>\n'
        '  <url>\n'
        '    <loc>' + request.build_absolute_uri('/login/') + '</loc>\n'
        '    <changefreq>monthly</changefreq>\n'
        '    <priority>0.8</priority>\n'
        '  </url>\n'
        '  <url>\n'
        '    <loc>' + request.build_absolute_uri('/signup/') + '</loc>\n'
        '    <changefreq>monthly</changefreq>\n'
        '    <priority>0.8</priority>\n'
        '  </url>\n'
        '</urlset>'
    )
    return HttpResponse(content, content_type="application/xml")
