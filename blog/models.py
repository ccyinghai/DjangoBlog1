import logging
from abc import abstractmethod
import re # Import the regular expression module

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from ckeditor.fields import RichTextField
from ckeditor_uploader.fields import RichTextUploadingField
from uuslug import slugify

from djangoblog.utils import cache_decorator, cache
from djangoblog.utils import get_current_site

logger = logging.getLogger(__name__)


class LinkShowType(models.TextChoices):
    I = ('i', _('index'))
    L = ('l', _('list'))
    P = ('p', _('post'))
    A = ('a', _('all'))
    S = ('s', _('slide'))


class BaseModel(models.Model):
    id = models.AutoField(primary_key=True)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_modify_time = models.DateTimeField(_('modify time'), default=now)

    def save(self, *args, **kwargs):
        is_update_views = isinstance(
            self,
            Article) and 'update_fields' in kwargs and kwargs['update_fields'] == ['views']
        if is_update_views:
            Article.objects.filter(pk=self.pk).update(views=self.views)
        else:
            if 'slug' in self.__dict__:
                slug = getattr(
                    self, 'title') if 'title' in self.__dict__ else getattr(
                    self, 'name')
                setattr(self, 'slug', slugify(slug))
            super().save(*args, **kwargs)

    def get_full_url(self):
        # 确保在访问site对象时，其已经完全初始化
        from django.contrib.sites.shortcuts import get_current_site
        site = get_current_site(request=None) # get_current_site 可以接受request，这里传入None以适应模型方法
        url = "https://{site_domain}{path}".format(site_domain=site.domain,
                                            path=self.get_absolute_url())
        return url

    class Meta:
        abstract = True

    @abstractmethod
    def get_absolute_url(self):
        pass


class Article(BaseModel):
    """文章"""
    STATUS_CHOICES = (
        ('d', _('Draft')),
        ('p', _('Published')),
    )
    COMMENT_STATUS = (
        ('o', _('Open')),
        ('c', _('Close')),
    )
    TYPE = (
        ('a', _('Article')),
        ('p', _('Page')),
    )
    title = models.CharField(_('title'), max_length=200, unique=True)
    body = RichTextUploadingField(verbose_name="内容", blank=True, null=True)
    pub_time = models.DateTimeField(
        _('publish time'), blank=False, null=False, default=now)
    status = models.CharField(
        _('status'),
        max_length=1,
        choices=STATUS_CHOICES,
        default='p')
    comment_status = models.CharField(
        _('comment status'),
        max_length=1,
        choices=COMMENT_STATUS,
        default='o')
    type = models.CharField(_('type'), max_length=1, choices=TYPE, default='a')
    views = models.PositiveIntegerField(_('views'), default=0)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('author'),
        blank=False,
        null=False,
        on_delete=models.CASCADE)
    article_order = models.IntegerField(
        _('order'), blank=False, null=False, default=0)
    show_toc = models.BooleanField(_('show toc'), blank=False, null=False, default=False)
    category = models.ForeignKey(
        'Category',
        verbose_name=_('category'),
        on_delete=models.CASCADE,
        blank=False,
        null=False)
    tags = models.ManyToManyField('Tag', verbose_name=_('tag'), blank=True)
    videos = models.ManyToManyField('Video', blank=True, verbose_name=_('related videos'))
    is_premium = models.BooleanField(_('is premium'), default=False)

    def body_to_string(self):
        return self.body

    def __str__(self):
        return self.title

    def delete(self, *args, **kwargs):
        """
        Override delete to delete files referenced in the body.
        """
        import re
        from django.conf import settings
        import os

        # Regex to find Markdown images: ![alt text](url)
        markdown_image_pattern = r'!\[.*?\]\((.*?)\)'
        # Regex to find HTML video sources: <video src="url">
        html_video_pattern = r'<video.*?src="(.*?)".*?>'

        # Find all URLs in the body
        image_urls = re.findall(markdown_image_pattern, self.body)
        video_urls = re.findall(html_video_pattern, self.body)
        all_urls = image_urls + video_urls

        media_prefix = settings.MEDIA_URL
        attachment_dir = 'article_attachments/'

        for url in all_urls:
            # Clean up URL to remove potential quotes or whitespace
            url = url.strip('\'" ')
            
            # Check if the URL is a local media file in the attachments directory
            if url.startswith(media_prefix) and attachment_dir in url:
                # Construct the file path on the server
                # Remove the leading MEDIA_URL and join with MEDIA_ROOT
                file_path = os.path.join(settings.MEDIA_ROOT, url[len(media_prefix):])
                
                # Ensure the path is normalized and secure (though regex should limit this)
                # This step is a safeguard, actual security relies on MEDIA_ROOT configuration
                normalized_media_root = os.path.normpath(settings.MEDIA_ROOT)
                normalized_file_path = os.path.normpath(file_path)

                if normalized_file_path.startswith(normalized_media_root):
                    if os.path.exists(normalized_file_path):
                        try:
                            os.remove(normalized_file_path)
                            print(f"Deleted file: {normalized_file_path}") # For debugging
                        except OSError as e:
                            print(f"Error deleting file {normalized_file_path}: {e}") # For error logging
                    else:
                         print(f"File not found for deletion: {normalized_file_path}") # For debugging
                else:
                    print(f"Attempted to delete file outside MEDIA_ROOT: {normalized_file_path}") # Security warning


        # Call the original delete method to delete the Article instance
        super().delete(*args, **kwargs)

    class Meta:
        ordering = ['-article_order', '-pub_time']
        verbose_name = _('article')
        verbose_name_plural = verbose_name
        get_latest_by = 'id'

    def get_absolute_url(self):
        return reverse('blog:detailbyid', kwargs={
            'article_id': self.id,
            'year': self.creation_time.year,
            'month': self.creation_time.month,
            'day': self.creation_time.day
        })

    @cache_decorator(60 * 60 * 10)
    def get_category_tree(self):
        tree = self.category.get_category_tree()
        names = list(map(lambda c: (c.name, c.get_absolute_url()), tree))

        return names

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def viewed(self):
        self.views += 1
        self.save(update_fields=['views'])

    def comment_list(self):
        cache_key = 'article_comments_{id}'.format(id=self.id)
        value = cache.get(cache_key)
        if value:
            logger.info('get article comments:{id}'.format(id=self.id))
            return value
        else:
            comments = self.comment_set.filter(is_enable=True).order_by('-id')
            cache.set(cache_key, comments, 60 * 100)
            logger.info('set article comments:{id}'.format(id=self.id))
            return comments

    def get_admin_url(self):
        info = (self._meta.app_label, self._meta.model_name)
        return reverse('admin:%s_%s_change' % info, args=(self.pk,))

    @cache_decorator(expiration=60 * 100)
    def next_article(self):
        # 下一篇
        return Article.objects.filter(
            id__gt=self.id, status='p').order_by('id').first()

    @cache_decorator(expiration=60 * 100)
    def prev_article(self):
        # 前一篇
        return Article.objects.filter(id__lt=self.id, status='p').first()


class Category(BaseModel):
    """文章分类"""
    name = models.CharField(_('category name'), max_length=30, unique=True)
    parent_category = models.ForeignKey(
        'self',
        verbose_name=_('parent category'),
        blank=True,
        null=True,
        on_delete=models.CASCADE)
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)
    index = models.IntegerField(default=0, verbose_name=_('index'))

    class Meta:
        ordering = ['-index']
        verbose_name = _('category')
        verbose_name_plural = verbose_name

    def get_absolute_url(self):
        return reverse(
            'blog:category_detail', kwargs={
                'category_name': self.slug})

    def __str__(self):
        return self.name

    @cache_decorator(60 * 60 * 10)
    def get_category_tree(self):
        """
        递归获得分类目录的父级
        :return:
        """
        categorys = []

        def parse(category):
            categorys.append(category)
            if category.parent_category:
                parse(category.parent_category)

        parse(self)
        return categorys

    @cache_decorator(60 * 60 * 10)
    def get_sub_categorys(self):
        """
        获得当前分类目录所有子集
        :return:
        """
        categorys = []
        all_categorys = Category.objects.all()

        def parse(category):
            if category not in categorys:
                categorys.append(category)
            childs = all_categorys.filter(parent_category=category)
            for child in childs:
                if category not in categorys:
                    categorys.append(child)
                parse(child)

        parse(self)
        return categorys


class Tag(BaseModel):
    """文章标签"""
    name = models.CharField(_('tag name'), max_length=30, unique=True)
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('blog:tag_detail', kwargs={'tag_name': self.slug})

    @cache_decorator(60 * 60 * 10)
    def get_article_count(self):
        return Article.objects.filter(tags__name=self.name).distinct().count()

    class Meta:
        ordering = ['name']
        verbose_name = _('tag')
        verbose_name_plural = verbose_name


class Video(BaseModel):
    """视频模型"""
    title = models.CharField(_('title'), max_length=200)
    video_file = models.FileField(_('video file'), upload_to='videos/')
    upload_time = models.DateTimeField(_('upload time'), default=now)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('author'),
        blank=False,
        null=False,
        on_delete=models.CASCADE)
    views = models.PositiveIntegerField(_('views'), default=0)

    class Meta:
        ordering = ['-upload_time']
        verbose_name = _('video')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('blog:video_detail', kwargs={'video_id': self.id})

    def viewed(self):
        self.views += 1
        self.save(update_fields=['views'])


class Links(models.Model):
    """友情链接"""

    name = models.CharField(_('link name'), max_length=30, unique=True)
    link = models.URLField(_('link'))
    sequence = models.IntegerField(_('order'), unique=True)
    is_enable = models.BooleanField(
        _('is show'), default=True, blank=False, null=False)
    show_type = models.CharField(
        _('show type'),
        max_length=1,
        choices=LinkShowType.choices,
        default=LinkShowType.I)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_mod_time = models.DateTimeField(_('modify time'), default=now)

    class Meta:
        ordering = ['sequence']
        verbose_name = _('link')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class SideBar(models.Model):
    """侧边栏,可以展示一些html内容"""
    name = models.CharField(_('title'), max_length=100)
    content = models.TextField(_('content'))
    sequence = models.IntegerField(_('order'), unique=True)
    is_enable = models.BooleanField(_('is enable'), default=True)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_mod_time = models.DateTimeField(_('modify time'), default=now)

    class Meta:
        ordering = ['sequence']
        verbose_name = _('sidebar')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class BlogSettings(models.Model):
    """blog的配置"""
    site_name = models.CharField(
        _('site name'),
        max_length=200,
        null=False,
        blank=False,
        default='')
    site_description = models.TextField(
        _('site description'),
        max_length=1000,
        null=False,
        blank=False,
        default='')
    site_seo_description = models.TextField(
        _('site seo description'), max_length=1000, null=False, blank=False, default='')
    site_keywords = models.TextField(
        _('site keywords'),
        max_length=1000,
        null=False,
        blank=False,
        default='')
    article_sub_length = models.IntegerField(_('article sub length'), default=300)
    sidebar_article_count = models.IntegerField(_('sidebar article count'), default=10)
    sidebar_comment_count = models.IntegerField(_('sidebar comment count'), default=5)
    article_comment_count = models.IntegerField(_('article comment count'), default=5)
    show_google_adsense = models.BooleanField(_('show adsense'), default=False)
    google_adsense_codes = models.TextField(
        _('adsense code'), max_length=2000, null=True, blank=True, default='')
    open_site_comment = models.BooleanField(_('open site comment'), default=True)
    global_header = models.TextField("公共头部", null=True, blank=True, default='')
    global_footer = models.TextField("公共尾部", null=True, blank=True, default='')
    beian_code = models.CharField(
        '备案号',
        max_length=2000,
        null=True,
        blank=True,
        default='')
    analytics_code = models.TextField(
        "网站统计代码",
        max_length=1000,
        null=False,
        blank=False,
        default='')
    show_gongan_code = models.BooleanField(
        '是否显示公安备案号', default=False, null=False)
    gongan_beiancode = models.TextField(
        '公安备案号',
        max_length=2000,
        null=True,
        blank=True,
        default='')
    comment_need_review = models.BooleanField(
        '评论是否需要审核', default=False, null=False)

    class Meta:
        verbose_name = _('Website configuration')
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.site_name

    def clean(self):
        if BlogSettings.objects.exclude(id=self.id).count():
            raise ValidationError(_('There can only be one configuration'))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from djangoblog.utils import cache
        cache.clear()


class MembershipType(models.Model):
    """会员类型模型"""
    name = models.CharField(_('membership name'), max_length=50, unique=True)
    price = models.DecimalField(_('price'), max_digits=10, decimal_places=2)
    duration_months = models.IntegerField(_('duration in months'))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Membership Type')
        verbose_name_plural = _('Membership Types')


class Membership(models.Model):
    """用户会员订阅模型"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name=_('user'))
    membership_type = models.ForeignKey(MembershipType, on_delete=models.SET_NULL, null=True, verbose_name=_('membership type'))
    start_date = models.DateTimeField(_('start date'), default=now)
    end_date = models.DateTimeField(_('end date'))
    is_active = models.BooleanField(_('is active'), default=True)

    def __str__(self):
        return f"{self.user.username} - {self.membership_type.name}"

    class Meta:
        verbose_name = _('Membership')
        verbose_name_plural = _('Memberships')

    def is_membership_active(self):
        """检查会员是否在有效期内"""
        return self.is_active and self.end_date >= now()


class Order(models.Model):
    """订单模型"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name=_('user'))
    membership_type = models.ForeignKey('MembershipType', on_delete=models.SET_NULL, null=True, verbose_name=_('membership type'))
    order_id = models.CharField(_('order id'), max_length=100, unique=True)
    amount = models.DecimalField(_('amount'), max_digits=10, decimal_places=2)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    is_paid = models.BooleanField(_('is paid'), default=False)
    paid_time = models.DateTimeField(_('paid time'), null=True, blank=True)

    def __str__(self):
        return f"Order {self.order_id} for {self.user.username}"

    class Meta:
        ordering = ['-creation_time']
        verbose_name = _('Order')
        verbose_name_plural = _('Orders')
