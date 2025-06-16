from django.urls import path
from django.views.decorators.cache import cache_page

from . import views

app_name = "blog"
urlpatterns = [
    path(
        r'',
        views.IndexView.as_view(),
        name='index'),
    path(
        r'page/<int:page>/',
        views.IndexView.as_view(),
        name='index_page'),
    path(
        r'article/<int:year>/<int:month>/<int:day>/<int:article_id>.html',
        views.ArticleDetailView.as_view(),
        name='detailbyid'),
    path(
        r'category/<slug:category_name>.html',
        views.CategoryDetailView.as_view(),
        name='category_detail'),
    path(
        r'category/<slug:category_name>/<int:page>.html',
        views.CategoryDetailView.as_view(),
        name='category_detail_page'),
    path(
        r'author/<author_name>.html',
        views.AuthorDetailView.as_view(),
        name='author_detail'),
    path(
        r'author/<author_name>/<int:page>.html',
        views.AuthorDetailView.as_view(),
        name='author_detail_page'),
    path(
        r'tag/<slug:tag_name>.html',
        views.TagDetailView.as_view(),
        name='tag_detail'),
    path(
        r'tag/<slug:tag_name>/<int:page>.html',
        views.TagDetailView.as_view(),
        name='tag_detail_page'),
    path(
        'archives.html',
        cache_page(
            60 * 60)(
            views.ArchivesView.as_view()),
        name='archives'),
    path(
        'links.html',
        views.LinkListView.as_view(),
        name='links'),
    path(
        r'upload',
        views.fileupload,
        name='upload'),
    path(
        r'clean',
        views.clean_cache_view,
        name='clean'),
    path(
        r'video/upload/', 
        views.upload_video, 
        name='upload_video'),
    path(
        r'video/<int:video_id>.html',
        views.VideoDetailView.as_view(),
        name='video_detail'),
    path(
        r'membership/',
        views.membership_list,
        name='membership_list'),
    path(
        r'membership/create_order/',
        views.create_order,
        name='create_order'),
    path(
        r'membership/order/<str:order_id>/',
        views.order_detail,
        name='order_detail'),
    path(
        r'membership/order/<str:order_id>/pay/',
        views.simulate_pay,
        name='simulate_pay'),
]
