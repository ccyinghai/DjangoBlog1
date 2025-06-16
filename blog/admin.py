from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.conf import settings

import os
import uuid
from ckeditor_uploader.widgets import CKEditorUploadingWidget  # 导入 CKEditorUploadingWidget
# Removed: import bulk_admin # 导入bulk_admin

# Register your models here.
from .models import Article, Tag, Category, Links, SideBar, BlogSettings, MembershipType, Membership, Order # Import Order model


class MultipleClearableFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class ArticleAdminForm(forms.ModelForm):
    body = forms.CharField(widget=CKEditorUploadingWidget())

    class Meta:
        model = Article
        fields = '__all__'


# class ArticleForm(forms.ModelForm):
#     # body = forms.CharField(widget=AdminPagedownWidget())
#     file_uploads = forms.FileField(
#         label=_('批量上传文件或图片'),
#         widget=MultipleClearableFileInput(),
#         required=False,
#         help_text=_('按住Ctrl或Command键选择多个文件')
#     )

    # class Meta:
    #     model = Article
    #     fields = '__all__'

    # def __init__(self, *args, **kwargs):
    #     self.request = kwargs.pop('request', None)
    #     super().__init__(*args, **kwargs)

    # def save(self, commit=True):
    #     instance = super().save(commit=False)

    #     if self.request and self.cleaned_data.get('file_uploads'):
    #         uploaded_files = self.cleaned_data['file_uploads']
    #         for uploaded_file in uploaded_files:
    #             # 生成唯一文件名
    #             ext = os.path.splitext(uploaded_file.name)[1]
    #             new_filename = f'{uuid.uuid4().hex}{ext}'
    #             # 构建保存路径
    #             upload_dir = os.path.join(settings.MEDIA_ROOT, 'article_attachments')
    #             os.makedirs(upload_dir, exist_ok=True)
    #             save_path = os.path.join(upload_dir, new_filename)

    #             # 保存文件到文件系统
    #             with open(save_path, 'wb+') as destination:
    #                 for chunk in uploaded_file.chunks():
    #                     destination.write(chunk)

    #             # 这里可以获取文件URL，但暂不插入到编辑器，留待前端JavaScript处理
    #             file_url = os.path.join(settings.MEDIA_URL, 'article_attachments', new_filename).replace('\\', '/')
    #             # 可以在这里存储文件URL列表，以便在前端访问
    #             if not hasattr(self, 'uploaded_file_urls'):
    #                 self.uploaded_file_urls = []
    #             self.uploaded_file_urls.append(file_url)

    #     if commit:
    #         instance.save()
    #         # TODO: 如果需要，这里可以在文章保存后，将临时文件移动到以文章ID为目录的路径下

    #     return instance


def makr_article_publish(modeladmin, request, queryset):
    queryset.update(status='p')


def draft_article(modeladmin, request, queryset):
    queryset.update(status='d')


def close_article_commentstatus(modeladmin, request, queryset):
    queryset.update(comment_status='c')


def open_article_commentstatus(modeladmin, request, queryset):
    queryset.update(comment_status='o')


makr_article_publish.short_description = _('Publish selected articles')
draft_article.short_description = _('Draft selected articles')
close_article_commentstatus.short_description = _('Close article comments')
open_article_commentstatus.short_description = _('Open article comments')


class ArticlelAdmin(admin.ModelAdmin): # 改回继承admin.ModelAdmin
# Removed: # class ArticlelAdmin(admin.ModelAdmin): # 注释掉原有继承
# Removed: # class ArticlelAdmin(bulk_admin.BulkModelAdmin): # 修改为继承bulk_admin.BulkModelAdmin
    list_per_page = 20
    search_fields = ('body', 'title')
    form = ArticleAdminForm  # 使用自定义的 ArticleAdminForm
    list_display = (
        'id',
        'title',
        'author',
        'link_to_category',
        'creation_time',
        'views',
        'status',
        'type',
        'article_order')
    list_display_links = ('id', 'title')
    list_filter = ('status', 'type', 'category')
    filter_horizontal = ('tags',)
    # exclude = ('creation_time', 'last_modify_time') # Removed exclude as we will use fieldsets
    view_on_site = True
    actions = [
        makr_article_publish,
        draft_article,
        close_article_commentstatus,
        open_article_commentstatus]

    # Define custom fieldsets
    fieldsets = (
        (None, {
            'fields': ('title', 'is_premium') # Group title, is_premium, and file_uploads
        }),
        (_('Content'), {
            'fields': ('body',)
        }),
        (_('Metadata'), {
            'fields': ('author', 'category', 'tags', 'pub_time', 'status', 'comment_status', 'type', 'article_order', 'show_toc', 'videos'),
            'classes': ('collapse',)
        }),
    )

    def link_to_category(self, obj):
        info = (obj.category._meta.app_label, obj.category._meta.model_name)
        link = reverse('admin:%s_%s_change' % info, args=(obj.category.id,))
        return format_html(u'<a href="%s">%s</a>' % (link, obj.category.name))

    link_to_category.short_description = _('category')

    def get_form(self, request, obj=None, **kwargs):
        self.request = request  # Store the request object
        form = super(ArticlelAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['author'].queryset = get_user_model(
        ).objects.filter(is_superuser=True)
        # 将request传递给ArticleForm
        return form

    def save_model(self, request, obj, form, change):
        super(ArticlelAdmin, self).save_model(request, obj, form, change)

    def get_view_on_site_url(self, obj=None):
        if obj:
            url = obj.get_full_url()
            return url
        else:
            from djangoblog.utils import get_current_site
            site = get_current_site(self.request).domain
            return site


class TagAdmin(admin.ModelAdmin):
    exclude = ('slug', 'last_mod_time', 'creation_time')


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_category', 'index')
    exclude = ('slug', 'last_mod_time', 'creation_time')


class LinksAdmin(admin.ModelAdmin):
    exclude = ('last_mod_time', 'creation_time')


class SideBarAdmin(admin.ModelAdmin):
    list_display = ('name', 'content', 'is_enable', 'sequence')
    exclude = ('last_mod_time', 'creation_time')


class BlogSettingsAdmin(admin.ModelAdmin):
    pass


class MembershipTypeAdmin(admin.ModelAdmin):
    pass


admin.site.register(Article, ArticlelAdmin)
admin.site.register(Tag, TagAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Links, LinksAdmin)
admin.site.register(SideBar, SideBarAdmin)
admin.site.register(BlogSettings, BlogSettingsAdmin)

# Register MembershipType with explicit Admin class
admin.site.register(MembershipType, MembershipTypeAdmin)

# Admin interface for the Order model
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_id',
        'user',
        'membership_type',
        'amount',
        'creation_time',
        'is_paid',
        'paid_time',
    )
    list_filter = ('is_paid', 'membership_type')
    search_fields = ('order_id', 'user__username', 'user__email') # Allow searching by order ID or user details
    ordering = ('-creation_time',) # Order by creation time descending

# Register Order model
admin.site.register(Order, OrderAdmin)

# Debugging: Print registered models
print("Registered models in admin.site:")
for model, model_admin in admin.site._registry.items():
    print(f"- {model._meta.app_label}.{model._meta.model_name}")
print("-" * 20)
