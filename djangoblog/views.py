from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from bs4 import BeautifulSoup
from blog.models import Article

from djangoblog.utils import get_blog_setting, CommonMarkdown

def age_verification_view(request):
    if request.method == 'POST':
        if request.POST.get('confirm_age') == 'true':
            request.session['age_verified'] = True
            return redirect('blog:index') # Redirect to homepage
    
    # Get site name from blog settings
    blog_setting = get_blog_setting()
    site_name = blog_setting.site_name if blog_setting and hasattr(blog_setting, 'site_name') else 'Your Website Name'

    context = {
        'SITE_NAME': site_name
    }
    return render(request, 'age_verification.html', context)


def get_paginated_images(request, article_id, page_num=1):
    try:
        article = get_object_or_404(Article, id=article_id)
    except Article.DoesNotExist:
        return JsonResponse({'error': 'Article not found'}, status=404)

    html_content = CommonMarkdown.get_markdown(article.body)
    soup = BeautifulSoup(html_content, 'html.parser')
    images = soup.find_all('img')

    images_per_page = 50
    start_index = (page_num - 1) * images_per_page
    end_index = start_index + images_per_page

    paginated_images = images[start_index:end_index]
    has_next_page = len(images) > end_index

    image_html_snippets = []
    for img_tag in paginated_images:
        img_src = img_tag.get('src')
        img_alt = img_tag.get('alt', '')
        if img_src:
            # Create a new BeautifulSoup object for the link to avoid modifying the original soup structure for slicing
            temp_soup = BeautifulSoup('', 'html.parser')
            fancybox_link = temp_soup.new_tag("a", href=img_src)
            fancybox_link['data-fancybox'] = "gallery"
            if img_alt:
                fancybox_link['data-caption'] = img_alt
            
            # Append the original img tag to the new link tag
            fancybox_link.append(img_tag)
            image_html_snippets.append(str(fancybox_link))

    return JsonResponse({
        'images': image_html_snippets,
        'has_next_page': has_next_page
    }) 