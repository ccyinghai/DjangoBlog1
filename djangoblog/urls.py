from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include, re_path
from haystack.views import search_view_factory
from django.contrib import admin
from filebrowser.sites import site as filebrowser_site
from storages.backends.s3boto3 import S3Boto3Storage
from djangoblog.custom_s3_storage import CustomS3Boto3Storage

from blog.views import EsSearchView
from djangoblog.admin_site import admin_site
from djangoblog.elasticsearch_backend import ElasticSearchModelSearchForm
from djangoblog.feeds import DjangoBlogFeed
from djangoblog.sitemap import ArticleSiteMap, CategorySiteMap, StaticViewSitemap, TagSiteMap, UserSiteMap
from django.views.decorators.cache import cache_page
from djangoblog import views as djangoblog_views
from blog import views as blog_views

# filebrowser_site.storage = CustomS3Boto3Storage() # Explicitly set FileBrowser to use CustomS3Boto3Storage

sitemaps = {
    'blog': ArticleSiteMap,
    'Category': CategorySiteMap,
    'Tag': TagSiteMap,
    'User': UserSiteMap,
    'static': StaticViewSitemap
}

handler404 = 'blog.views.page_not_found_view'
handler500 = 'blog.views.server_error_view'
handle403 = 'blog.views.permission_denied_view'

urlpatterns = [
    # Global URLs (not localized)
    path('age_verify/', djangoblog_views.age_verification_view, name='age_verify'),
    path('i18n/', include('django.conf.urls.i18n')),
    path('grappelli/', include('grappelli.urls')),
    re_path(r'^admin/filebrowser/', filebrowser_site.urls),
    re_path(r'^admin/', admin_site.urls),
    # CKEditor Uploader URLs
    re_path(r'^ckeditor/', include('ckeditor_uploader.urls')),
    path('wasabi-file-browser/', blog_views.wasabi_file_browser, name='wasabi_file_browser'),
    path('wasabi-file-list-json/', blog_views.wasabi_file_list_json, name='wasabi_file_list_json'),
    path('captcha/', include('captcha.urls')),
]
# Localized URLs (prefixed with language code)
urlpatterns += i18n_patterns(
    re_path(r'', include('blog.urls', namespace='blog')),
    re_path(r'', include('comments.urls', namespace='comment')),
    re_path(r'', include('accounts.urls', namespace='account')),
    re_path(r'', include('oauth.urls', namespace='oauth')),
    re_path(r'', include('servermanager.urls', namespace='servermanager')),
    re_path(r'', include('owntracks.urls', namespace='owntracks')),

    # Sitemap and Feed URLs
    re_path(r'^sitemap\.xml$', cache_page(60 * 20)(sitemap), {'sitemaps': sitemaps},
            name='django.contrib.sitemaps.views.sitemap'),
    re_path(r'^feed/$', DjangoBlogFeed()),
    re_path(r'^rss/$', DjangoBlogFeed()),
    re_path('^search', search_view_factory(view_class=EsSearchView, form_class=ElasticSearchModelSearchForm),
            name='search'),
    # New URL pattern for paginated images
    path('articles/<int:article_id>/images/<int:page_num>/', djangoblog_views.get_paginated_images, name='get_paginated_images'),

    prefix_default_language=False # Correctly placed as a keyword argument
)

# Static and media file serving (always outside i18n_patterns)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
