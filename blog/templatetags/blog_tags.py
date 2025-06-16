import hashlib
import logging
import random
import urllib

from django import template
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import stringfilter, truncatechars_html
from django.templatetags.static import static
from django.urls import reverse
from django.utils.safestring import mark_safe

from blog.models import Article, Category, Tag, Links, SideBar, LinkShowType
from comments.models import Comment
from djangoblog.utils import CommonMarkdown, sanitize_html
from djangoblog.utils import cache
from djangoblog.utils import get_current_site
from oauth.models import OAuthUser
from bs4 import BeautifulSoup # Import BeautifulSoup

logger = logging.getLogger(__name__)

register = template.Library()


@register.simple_tag
def timeformat(data):
    try:
        return data.strftime(settings.TIME_FORMAT)
    except Exception as e:
        logger.error(e)
        return ""


@register.simple_tag
def datetimeformat(data):
    try:
        return data.strftime(settings.DATE_TIME_FORMAT)
    except Exception as e:
        logger.error(e)
        return ""


@register.filter()
@stringfilter
def custom_markdown(content):
    """
    简化版 Markdown 过滤器，只负责将 Markdown 文本转换为 HTML。
    其他内容过滤逻辑已移至 load_article_detail 标签。
    """
    return mark_safe(CommonMarkdown.get_markdown(content))


@register.simple_tag
def get_markdown_toc(content):
    from djangoblog.utils import CommonMarkdown
    body, toc = CommonMarkdown.get_markdown_with_toc(content)
    return mark_safe(toc)


@register.filter()
@stringfilter
def comment_markdown(content):
    content = CommonMarkdown.get_markdown(content)
    return mark_safe(sanitize_html(content))


@register.filter(is_safe=True)
@stringfilter
def truncatechars_content(content, is_list_page=False):
    """
    获得文章内容的摘要
    :param content:
    :return:
    """
    from djangoblog.utils import get_blog_setting
    blogsetting = get_blog_setting()
    
    html_content = truncatechars_html(content, blogsetting.article_sub_length)

    if is_list_page:
        # If it's a list page, remove video tags from truncated content as well
        soup = BeautifulSoup(html_content, 'html.parser')
        for video_tag in soup.find_all('video'):
            video_tag.decompose()
        html_content = str(soup)
        
    return html_content


@register.filter(is_safe=True)
@stringfilter
def truncate(content):
    from django.utils.html import strip_tags

    return strip_tags(content)[:150]


@register.inclusion_tag('blog/tags/breadcrumb.html', takes_context=True)
def load_breadcrumb(context, article):
    """
    获得文章面包屑
    :param article:
    :return:
    """
    names = article.get_category_tree()
    from djangoblog.utils import get_blog_setting
    blogsetting = get_blog_setting()
    request = context.get('request')
    site = get_current_site(request).domain
    names.append((blogsetting.site_name, '/'))
    names = names[::-1]

    return {
        'names': names,
        'title': article.title,
        'count': len(names) + 1
    }


@register.inclusion_tag('blog/tags/article_tag_list.html')
def load_articletags(article):
    """
    文章标签
    :param article:
    :return:
    """
    tags = article.tags.all()
    tags_list = []
    for tag in tags:
        url = tag.get_absolute_url()
        count = tag.get_article_count()
        tags_list.append((
            url, count, tag, random.choice(settings.BOOTSTRAP_COLOR_TYPES)
        ))
    return {
        'article_tags_list': tags_list
    }


@register.inclusion_tag('blog/tags/sidebar.html')
def load_sidebar(user, linktype):
    """
    加载侧边栏
    :return:
    """
    value = cache.get("sidebar" + linktype)
    if value:
        value['user'] = user
        return value
    else:
        logger.info('load sidebar')
        from djangoblog.utils import get_blog_setting
        blogsetting = get_blog_setting()
        recent_articles = Article.objects.filter(
            status='p')[:blogsetting.sidebar_article_count]
        sidebar_categorys = Category.objects.all()
        extra_sidebars = SideBar.objects.filter(
            is_enable=True).order_by('sequence')
        most_read_articles = Article.objects.filter(status='p').order_by(
            '-views')[:blogsetting.sidebar_article_count]
        dates = Article.objects.datetimes('creation_time', 'month', order='DESC')
        links = Links.objects.filter(is_enable=True).filter(
            Q(show_type=str(linktype)) | Q(show_type=LinkShowType.A))
        commment_list = Comment.objects.filter(is_enable=True).order_by(
            '-id')[:blogsetting.sidebar_comment_count]
        # 标签云 计算字体大小
        # 根据总数计算出平均值 大小为 (数目/平均值)*步长
        increment = 5
        tags = Tag.objects.all()
        sidebar_tags = None
        if tags and len(tags) > 0:
            s = [t for t in [(t, t.get_article_count()) for t in tags] if t[1]]
            count = sum([t[1] for t in s])
            dd = 1 if (count == 0 or not len(tags)) else count / len(tags)
            import random
            sidebar_tags = list(
                map(lambda x: (x[0], x[1], (x[1] / dd) * increment + 10), s))
            random.shuffle(sidebar_tags)

        value = {
            'recent_articles': recent_articles,
            'sidebar_categorys': sidebar_categorys,
            'most_read_articles': most_read_articles,
            'article_dates': dates,
            'sidebar_comments': commment_list,
            'sidabar_links': links,
            'show_google_adsense': blogsetting.show_google_adsense,
            'google_adsense_codes': blogsetting.google_adsense_codes,
            'open_site_comment': blogsetting.open_site_comment,
            'show_gongan_code': blogsetting.show_gongan_code,
            'sidebar_tags': sidebar_tags,
            'extra_sidebars': extra_sidebars
        }
        # Remove 'sidebar_categorys' and 'most_read_articles' from the value dictionary
        if 'sidebar_categorys' in value:
            del value['sidebar_categorys']
        if 'most_read_articles' in value:
            del value['most_read_articles']

        cache.set("sidebar" + linktype, value, 60 * 60 * 60 * 3)
        logger.info('set sidebar cache.key:{key}'.format(key="sidebar" + linktype))
        value['user'] = user
        return value


@register.inclusion_tag('blog/tags/article_meta_info.html')
def load_article_metas(article, user):
    """
    获得文章meta信息
    :param article:
    :return:
    """
    return {
        'article': article,
        'user': user
    }


@register.inclusion_tag('blog/tags/article_pagination.html')
def load_pagination_info(page_obj, page_type, tag_name):
    previous_url = ''
    next_url = ''
    if page_type == '':
        if page_obj.has_next():
            next_number = page_obj.next_page_number()
            next_url = reverse('blog:index_page', kwargs={'page': next_number})
        if page_obj.has_previous():
            previous_number = page_obj.previous_page_number()
            previous_url = reverse(
                'blog:index_page', kwargs={
                    'page': previous_number})
    if page_type == '分类标签归档':
        tag = get_object_or_404(Tag, name=tag_name)
        if page_obj.has_next():
            next_number = page_obj.next_page_number()
            next_url = reverse(
                'blog:tag_detail_page',
                kwargs={
                    'page': next_number,
                    'tag_name': tag.slug})
        if page_obj.has_previous():
            previous_number = page_obj.previous_page_number()
            previous_url = reverse(
                'blog:tag_detail_page',
                kwargs={
                    'page': previous_number,
                    'tag_name': tag.slug})
    if page_type == '作者文章归档':
        if page_obj.has_next():
            next_number = page_obj.next_page_number()
            next_url = reverse(
                'blog:author_detail_page',
                kwargs={
                    'page': next_number,
                    'author_name': tag_name})
        if page_obj.has_previous():
            previous_number = page_obj.previous_page_number()
            previous_url = reverse(
                'blog:author_detail_page',
                kwargs={
                    'page': previous_number,
                    'author_name': tag_name})

    if page_type == '分类目录归档':
        category = get_object_or_404(Category, name=tag_name)
        if page_obj.has_next():
            next_number = page_obj.next_page_number()
            next_url = reverse(
                'blog:category_detail_page',
                kwargs={
                    'page': next_number,
                    'category_name': category.slug})
        if page_obj.has_previous():
            previous_number = page_obj.previous_page_number()
            previous_url = reverse(
                'blog:category_detail_page',
                kwargs={
                    'page': previous_number,
                    'category_name': category.slug})

    return {
        'previous_url': previous_url,
        'next_url': next_url,
        'page_obj': page_obj
    }


@register.inclusion_tag('blog/tags/article_info.html')
def load_article_detail(article, isindex, user, exclude_initial_images=False):
    """
    加载文章详情，并在渲染前处理文章内容。
    :param article:
    :param isindex: 是否列表页，若是列表页只显示摘要
    :param exclude_initial_images: 是否在初始加载时排除图片
    :return:
    """
    from djangoblog.utils import get_blog_setting
    blogsetting = get_blog_setting()

    # 首先将 Markdown 转换为 HTML
    full_html_content = CommonMarkdown.get_markdown(article.body)
    logger.debug(f"load_article_detail: Full HTML content length after markdown: {len(full_html_content)}")
    
    soup = BeautifulSoup(full_html_content, 'html.parser')
    
    gallery_media_elements_strings = []

    # Process images first
    for img_tag in list(soup.find_all('img')):
        img_src = img_tag.get('src')
        img_alt = img_tag.get('alt', '')
        if img_src:
            fancybox_link = soup.new_tag("a", href=img_src)
            fancybox_link['data-fancybox'] = "gallery"
            if img_alt:
                fancybox_link['data-caption'] = img_alt
            
            # Replace the img tag with the new fancybox_link containing the img
            img_tag.replace_with(fancybox_link)
            fancybox_link.append(img_tag) # Put the original img back inside the new <a>
            
            gallery_media_elements_strings.append(str(fancybox_link))
            if not isindex: # For detail page, remove images from the main content for initial load
                fancybox_link.decompose()
        else:
            img_tag.decompose()

    # Process videos
    for video_tag in list(soup.find_all('video')):
        video_src = video_tag.get('src')
        if not video_src:
            source_tag = video_tag.find('source')
            if source_tag:
                video_src = source_tag.get('src')
        
        if video_src:
            fancybox_link = soup.new_tag("a", href=video_src)
            fancybox_link['data-fancybox'] = "gallery"
            fancybox_link['data-type'] = "html5video"
            fancybox_link['data-width'] = "535.8"
            fancybox_link['data-height'] = "300"
            
            # Replace the video tag with the new fancybox_link containing the video
            video_tag.replace_with(fancybox_link)
            fancybox_link.append(video_tag) # Put the original video back inside the new <a>
            
            # Videos are always kept inline in the main text body (wrapped for Fancybox).
            # They are NOT added to processed_article_media_elements_for_gallery.
        else:
            video_tag.decompose()

    # At this point, `soup` contains the original HTML with img/video tags replaced by their Fancybox-wrapped <a> versions.
    # For detail page, all wrapped image tags have been removed from the main content, but wrapped video tags remain.
    # For list page, all wrapped image and video tags are still in the main content.

    # Now, handle the content based on whether it's a list page or detail page
    processed_article_text_body = ""
    processed_article_media_elements_for_gallery = [] 

    if isindex: # For list page
        # Create a deep copy of the soup to remove media elements for text truncation
        temp_soup_for_text_truncation = BeautifulSoup(str(soup), 'html.parser')
        # Remove all fancybox links (which now wrap both img and video)
        for fancybox_a_tag in list(temp_soup_for_text_truncation.find_all('a', attrs={'data-fancybox': 'gallery'})):
            fancybox_a_tag.decompose()
        
        # Final cleanup for empty tags in the list page text content
        final_list_page_text_soup = BeautifulSoup(str(temp_soup_for_text_truncation), 'html.parser')
        empty_tags_to_remove = ['p', 'div', 'br', 'span', 'strong', 'em', 'a']
        for tag_name in empty_tags_to_remove:
            for tag in final_list_page_text_soup.find_all(tag_name):
                if not tag.get_text(strip=True) and not tag.find_all(True):
                    tag.decompose()
        
        processed_article_text_body = truncatechars_html(str(final_list_page_text_soup), blogsetting.article_sub_length)
        
        # 列表页图片限制For list page, processed_article_media_elements_for_gallery includes both images and videos, limited
        max_media_for_list = 6
        processed_article_media_elements_for_gallery = gallery_media_elements_strings[:max_media_for_list]

    else: # Detail page
        # For detail page, the main text body should be the soup after only images have been decomposed.
        final_detail_page_text_soup = BeautifulSoup(str(soup), 'html.parser')
        empty_tags_to_remove = ['p', 'div', 'br', 'span', 'strong', 'em', 'a']
        for tag_name in empty_tags_to_remove:
            for tag in final_detail_page_text_soup.find_all(tag_name):
                if not tag.get_text(strip=True) and not tag.find_all(True):
                    tag.decompose()
        processed_article_text_body = str(final_detail_page_text_soup)

        # For detail page, processed_article_media_elements_for_gallery is always empty for initial load,
        # as all media will be loaded via AJAX for images, and videos are inline.
        processed_article_media_elements_for_gallery = []
        
    logger.debug(f"load_article_detail: Final processed_article_text_body length: {len(processed_article_text_body)}")
    logger.debug(f"load_article_detail: Number of processed_article_media_elements_for_gallery: {len(processed_article_media_elements_for_gallery)}")

    return {
        'article': article,
        'isindex': isindex,
        'user': user,
        'open_site_comment': blogsetting.open_site_comment,
        'processed_article_text_body': mark_safe(processed_article_text_body),
        'processed_article_media_elements': processed_article_media_elements_for_gallery, 
        'exclude_initial_images': exclude_initial_images,
    }


# return only the URL of the gravatar
# TEMPLATE USE:  {{ email|gravatar_url:150 }}
@register.filter
def gravatar_url(email, size=40):
    """获得gravatar头像"""
    cachekey = 'gravatat/' + email
    url = cache.get(cachekey)
    if url:
        return url
    else:
        usermodels = OAuthUser.objects.filter(email=email)
        if usermodels:
            o = list(filter(lambda x: x.picture is not None, usermodels))
            if o:
                return o[0].picture
        email = email.encode('utf-8')

        default = static('blog/img/avatar.png')

        url = "https://www.gravatar.com/avatar/%s?%s" % (hashlib.md5(
            email.lower()).hexdigest(), urllib.parse.urlencode({'d': default, 's': str(size)}))
        cache.set(cachekey, url, 60 * 60 * 10)
        logger.info('set gravatar cache.key:{key}'.format(key=cachekey))
        return url


@register.filter
def gravatar(email, size=40):
    """获得gravatar头像"""
    url = gravatar_url(email, size)
    return mark_safe(
        '<img src="%s" height="%d" width="%d">' %
        (url, size, size))


@register.simple_tag
def query(qs, **kwargs):
    """ template tag which allows queryset filtering. Usage:
          {% query books author=author as mybooks %}
          {% for book in mybooks %}
            ...
          {% endfor %}
    """
    return qs.filter(**kwargs)


@register.filter
def addstr(arg1, arg2):
    """concatenate arg1 & arg2"""
    return str(arg1) + str(arg2)
