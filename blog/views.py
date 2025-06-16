import logging
import os
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.shortcuts import render
from django.templatetags.static import static
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from haystack.views import SearchView
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.urls import reverse
from storages.backends.s3boto3 import S3Boto3Storage

from blog.models import Article, Category, LinkShowType, Links, Tag, Video, MembershipType, Order
from comments.forms import CommentForm
from blog.forms import VideoUploadForm
from djangoblog.utils import cache, get_blog_setting
from accounts.models import RedemptionCode, UserMembership

logger = logging.getLogger(__name__)


class ArticleListView(ListView):
    # template_name属性用于指定使用哪个模板进行渲染
    template_name = 'blog/article_index.html'

    # context_object_name属性用于给上下文变量取名（在模板中使用该名字）
    context_object_name = 'article_list'

    # 页面类型，分类目录或标签列表等
    page_type = ''
    paginate_by = settings.PAGINATE_BY
    page_kwarg = 'page'
    link_type = LinkShowType.L

    def get_view_cache_key(self):
        return self.request.get['pages']

    @property
    def page_number(self):
        page_kwarg = self.page_kwarg
        page = self.kwargs.get(
            page_kwarg) or self.request.GET.get(page_kwarg) or 1
        return page

    def get_queryset_cache_key(self):
        """
        子类重写.获得queryset的缓存key
        """
        raise NotImplementedError()

    def get_queryset_data(self):
        """
        子类重写.获取queryset的数据
        """
        raise NotImplementedError()

    def get_queryset_from_cache(self, cache_key):
        '''
        缓存页面数据
        :param cache_key: 缓存key
        :return:
        '''
        value = cache.get(cache_key)
        if value:
            logger.info('get view cache.key:{key}'.format(key=cache_key))
            return value
        else:
            article_list = self.get_queryset_data()
            cache.set(cache_key, article_list)
            logger.info('set view cache.key:{key}'.format(key=cache_key))
            return article_list

    def get_queryset(self):
        '''
        重写默认，从缓存获取数据
        :return:
        '''
        key = self.get_queryset_cache_key()
        value = self.get_queryset_from_cache(key)
        return value

    def get_context_data(self, **kwargs):
        kwargs['linktype'] = self.link_type
        return super(ArticleListView, self).get_context_data(**kwargs)


class IndexView(ArticleListView):
    '''
    首页
    '''
    # 友情链接类型
    link_type = LinkShowType.I

    def dispatch(self, request, *args, **kwargs):
        # 检查会话中是否有年龄验证标志
        if not request.session.get('age_verified'):
            # 如果没有，重定向到年龄验证页面
            return redirect(reverse('age_verify'))
        return super().dispatch(request, *args, **kwargs)

    def get_queryset_data(self):
        article_list = Article.objects.filter(type='a', status='p')
        return article_list

    def get_queryset_cache_key(self):
        cache_key = 'index_{page}'.format(page=self.page_number)
        return cache_key


class ArticleDetailView(DetailView):
    '''
    文章详情页面
    '''
    template_name = 'blog/article_detail.html'
    model = Article
    pk_url_kwarg = 'article_id'
    context_object_name = "article"

    def get_object(self, queryset=None):
        # 调试：打印从URL获取的article_id
        article_id = self.kwargs.get(self.pk_url_kwarg)
        logger.debug(f"ArticleDetailView: Attempting to retrieve article with ID: {article_id}")
        
        obj = super(ArticleDetailView, self).get_object()
        
        # 调试：打印检索到的文章对象ID
        if obj:
            logger.debug(f"ArticleDetailView: Successfully retrieved article with ID: {obj.id}")
        else:
            logger.debug("ArticleDetailView: Failed to retrieve article object.")

        obj.viewed()
        self.object = obj
        return obj

    def get_context_data(self, **kwargs):
        # 调试：打印在上下文中传递的文章ID
        if self.object:
            logger.debug(f"ArticleDetailView: Passing article ID to context: {self.object.id}")
        else:
            logger.debug("ArticleDetailView: No article object available in get_context_data.")

        comment_form = CommentForm()

        article_comments = self.object.comment_list()
        parent_comments = article_comments.filter(parent_comment=None)
        blog_setting = get_blog_setting()
        paginator = Paginator(parent_comments, blog_setting.article_comment_count)
        page = self.request.GET.get('comment_page', '1')
        if not page.isnumeric():
            page = 1
        else:
            page = int(page)
            if page < 1:
                page = 1
            if page > paginator.num_pages:
                page = paginator.num_pages

        p_comments = paginator.page(page)
        next_page = p_comments.next_page_number() if p_comments.has_next() else None
        prev_page = p_comments.previous_page_number() if p_comments.has_previous() else None

        if next_page:
            kwargs[
                'comment_next_page_url'] = self.object.get_absolute_url() + f'?comment_page={next_page}#commentlist-container'
        if prev_page:
            kwargs[
                'comment_prev_page_url'] = self.object.get_absolute_url() + f'?comment_page={prev_page}#commentlist-container'
        kwargs['form'] = comment_form
        kwargs['article_comments'] = article_comments
        kwargs['p_comments'] = p_comments
        kwargs['comment_count'] = len(
            article_comments) if article_comments else 0

        kwargs['next_article'] = self.object.next_article
        kwargs['prev_article'] = self.object.prev_article

        logger.debug(f"ArticleDetailView: User authenticated: {self.request.user.is_authenticated}")
        is_premium_article = self.object.is_premium
        is_member = False
        if self.request.user.is_authenticated:
            logger.debug(f"ArticleDetailView: User {self.request.user.username} is authenticated.")
            try:
                # Check if the user has an active membership
                user_membership = self.request.user.usermembership
                logger.debug(f"ArticleDetailView: UserMembership found for {self.request.user.username}: is_active={user_membership.is_active}, end_date={user_membership.end_date}, now={timezone.now()}")
                if user_membership.is_membership_active():
                    is_member = True
                    logger.debug(f"ArticleDetailView: User {self.request.user.username} is an active member.")
                else:
                    logger.debug(f"ArticleDetailView: User {self.request.user.username} is NOT an active member (is_active: {user_membership.is_active}, end_date: {user_membership.end_date}).")
            except UserMembership.DoesNotExist: # Use specific exception
                logger.debug(f"ArticleDetailView: User {self.request.user.username} has no UserMembership record.")
                pass # User has no membership
            except Exception as e:
                logger.error(f"ArticleDetailView: Error checking membership for {self.request.user.username}: {e}")
                pass

        logger.debug(f"ArticleDetailView: is_premium_article={is_premium_article}, is_member={is_member}")
        if is_premium_article and not is_member:
            # 如果是会员文章且用户不是活跃会员，设置标志并在模板中处理
            kwargs['is_premium_restricted'] = True
            logger.debug(f"ArticleDetailView: Article is premium restricted for user {self.request.user.username}.")
        else:
            kwargs['is_premium_restricted'] = False
            logger.debug(f"ArticleDetailView: Article is NOT premium restricted for user {self.request.user.username}.")

        # Add exception for superusers and staff
        if self.request.user.is_authenticated and (self.request.user.is_superuser or self.request.user.is_staff):
            kwargs['is_premium_restricted'] = False
            logger.debug(f"ArticleDetailView: User {self.request.user.username} is superuser/staff, not restricted.")

        # Pass is_member to context for general front-end display (e.g., membership badge)
        kwargs['is_member'] = is_member
        kwargs['request'] = self.request

        return super(ArticleDetailView, self).get_context_data(**kwargs)


class CategoryDetailView(ArticleListView):
    '''
    分类目录列表
    '''
    page_type = "分类目录归档"

    def get_queryset_data(self):
        slug = self.kwargs['category_name']
        category = get_object_or_404(Category, slug=slug)

        categoryname = category.name
        self.categoryname = categoryname
        categorynames = list(
            map(lambda c: c.name, category.get_sub_categorys()))
        article_list = Article.objects.filter(
            category__name__in=categorynames, status='p')
        return article_list

    def get_queryset_cache_key(self):
        slug = self.kwargs['category_name']
        category = get_object_or_404(Category, slug=slug)
        categoryname = category.name
        self.categoryname = categoryname
        cache_key = 'category_list_{categoryname}_{page}'.format(
            categoryname=categoryname, page=self.page_number)
        return cache_key

    def get_context_data(self, **kwargs):

        categoryname = self.categoryname
        try:
            categoryname = categoryname.split('/')[-1]
        except BaseException:
            pass
        kwargs['page_type'] = CategoryDetailView.page_type
        kwargs['tag_name'] = categoryname
        return super(CategoryDetailView, self).get_context_data(**kwargs)


class AuthorDetailView(ArticleListView):
    '''
    作者详情页
    '''
    page_type = '作者文章归档'

    def get_queryset_cache_key(self):
        from uuslug import slugify
        author_name = slugify(self.kwargs['author_name'])
        cache_key = 'author_{author_name}_{page}'.format(
            author_name=author_name, page=self.page_number)
        return cache_key

    def get_queryset_data(self):
        author_name = self.kwargs['author_name']
        article_list = Article.objects.filter(
            author__username=author_name, type='a', status='p')
        return article_list

    def get_context_data(self, **kwargs):
        author_name = self.kwargs['author_name']
        kwargs['page_type'] = AuthorDetailView.page_type
        kwargs['tag_name'] = author_name
        return super(AuthorDetailView, self).get_context_data(**kwargs)


class TagDetailView(ArticleListView):
    '''
    标签列表页面
    '''
    page_type = '分类标签归档'

    def get_queryset_data(self):
        slug = self.kwargs['tag_name']
        tag = get_object_or_404(Tag, slug=slug)
        tag_name = tag.name
        self.name = tag_name
        article_list = Article.objects.filter(
            tags__name=tag_name, type='a', status='p')
        return article_list

    def get_queryset_cache_key(self):
        slug = self.kwargs['tag_name']
        tag = get_object_or_404(Tag, slug=slug)
        tag_name = tag.name
        self.name = tag_name
        cache_key = 'tag_{tag_name}_{page}'.format(
            tag_name=tag_name, page=self.page_number)
        return cache_key

    def get_context_data(self, **kwargs):
        # tag_name = self.kwargs['tag_name']
        tag_name = self.name
        kwargs['page_type'] = TagDetailView.page_type
        kwargs['tag_name'] = tag_name
        return super(TagDetailView, self).get_context_data(**kwargs)


class ArchivesView(ArticleListView):
    '''
    文章归档页面
    '''
    page_type = '文章归档'
    paginate_by = None
    page_kwarg = None
    template_name = 'blog/article_archives.html'

    def get_queryset_data(self):
        return Article.objects.filter(status='p').all()

    def get_queryset_cache_key(self):
        cache_key = 'archives'
        return cache_key


class LinkListView(ListView):
    model = Links
    template_name = 'blog/links_list.html'

    def get_queryset(self):
        return Links.objects.filter(is_enable=True)


class EsSearchView(SearchView):
    def get_context(self):
        paginator, page = self.build_page()
        context = {
            "query": self.query,
            "form": self.form,
            "page": page,
            "paginator": paginator,
            "suggestion": None,
        }
        if hasattr(self.results, "query") and self.results.query.backend.include_spelling:
            context["suggestion"] = self.results.query.get_spelling_suggestion()
        context.update(self.extra_context())

        return context


@csrf_exempt
def fileupload(request):
    """
    该方法需自己写调用端来上传图片，该方法仅提供图床功能
    :param request:
    :return:
    """
    if request.method == 'POST':
        # 保持原有的签名检查
        sign = request.GET.get('sign', None)
        if not sign or not sign == get_sha256(get_sha256(settings.SECRET_KEY)):
            return HttpResponseForbidden()

        # mdeditor expects a JSON response with 'url' and 'error'
        response_data = []

        for filename, file in request.FILES.items():
            fname = file.name
            # 检查文件扩展名以区分图片和视频
            imgextensions = ['.jpg', '.png', '.jpeg', '.bmp', '.gif']
            videoextensions = ['.mp4', '.webm', '.ogg', '.avi', '.mov'] # Add more video extensions as needed
            ext = os.path.splitext(fname)[1].lower()

            is_image = ext in imgextensions
            is_video = ext in videoextensions

            if is_image:
                # 原有的图片处理逻辑
                timestr = timezone.now().strftime('%Y/%m/%d')
                base_dir = os.path.join(settings.STATICFILES, "image", timestr)
                if not os.path.exists(base_dir):
                    os.makedirs(base_dir)
                # Use a unique filename
                savepath = os.path.normpath(os.path.join(base_dir, f"{uuid.uuid4().hex}{ext}"))
                # Basic security check
                if not savepath.startswith(base_dir):
                    response_data.append({'url': None, 'error': 'Invalid path'})
                    continue
                try:
                    with open(savepath, 'wb+') as wfile:
                        for chunk in file.chunks():
                            wfile.write(chunk)
                    # Optional: image optimization
                    from PIL import Image
                    image = Image.open(savepath)
                    image.save(savepath, quality=80, optimize=True) # Reduced quality for smaller size
                    url = static(os.path.relpath(savepath, settings.BASE_DIR))
                    response_data.append({'url': url, 'error': None})
                except Exception as e:
                    logger.error(f"Error saving image file {fname}: {e}")
                    response_data.append({'url': None, 'error': f'Error saving image: {e}'})

            elif is_video:
                # 使用 VideoUploadForm 处理视频上传
                # Since request.FILES contains the InMemoryUploadedFile, we can pass it directly
                # We need to create a temporary data dict for the form's non-file fields if any
                # For now, let's assume title is generated or not strictly required for this quick upload
                # A more robust solution might require user input for title or deriving it from filename
                # Let's create a basic form instance. The 'title' field in Video model is required.
                # We can use the filename as a temporary title or generate one.
                # For simplicity here, let's just use the filename and associate the current user.
                # Let's assume for direct editor upload, the user is logged in.
                if request.user.is_authenticated:
                    video = Video(title=fname, video_file=file)
                    video.author = request.user
                    video.save()
                    # Return the URL of the saved video file
                    video_url = video.video_file.url
                    response_data.append({'url': video_url, 'error': None, 'file_type': 'video'})
                else:
                    response_data.append({'url': None, 'error': 'Authentication required for video upload.'})
            else:
                # Handle other file types or return error
                response_data.append({'url': None, 'error': f'Unsupported file type: {ext}'})

        # mdeditor expects a single JSON object if multiple files are uploaded, 
        # or a list of objects. Let's return a list for consistency.
        # The mdeditor documentation suggests a JSON object with url and error.
        # Let's return a list of such objects if multiple files were in the request.FILES.
        # If only one file, return the single object.
        if len(response_data) == 1:
            return JsonResponse(response_data[0])
        elif len(response_data) > 1:
            # This case might need adjustment based on how mdeditor handles multiple file uploads at once.
            # For now, let's return the list, or just the first result.
            # Let's return the list as it's more informative.
            return JsonResponse(response_data, safe=False) # safe=False is needed for list serialization
        else:
            # No files processed, maybe an error occurred before file processing
            return JsonResponse({'url': None, 'error': 'No files uploaded or processed.'})

    else:
        return HttpResponse("only for post")


@require_POST  # 只允许POST请求
@csrf_exempt  # 暂时禁用CSRF保护，前端需要自行处理
def upload_attachment(request):
    # 打印request.FILES的内容进行调试 (可选，调试完成后可以移除)
    print("Request FILES:", request.FILES)

    if request.FILES:
        # 从 request.FILES 中获取文件列表，注意这里的键是'files[]'
        uploaded_files = request.FILES.getlist('files[]')
        if not uploaded_files:
            return JsonResponse({'error': '没有文件上传或字段名不匹配'}, status=400)

        file_urls = []
        for uploaded_file in uploaded_files:
            try:
                # 生成唯一文件名，并构建保存路径，让default_storage处理实际存储位置
                ext = os.path.splitext(uploaded_file.name)[1]
                new_filename = f'{uuid.uuid4().hex}{ext}'
                # 定义在Wasabi桶中的路径，例如 'article_attachments/uuid.ext'
                wasabi_path = os.path.join('article_attachments', new_filename)

                # 使用 default_storage 保存文件
                # default_storage 会自动处理文件到配置的后端（这里是Wasabi）
                saved_filename = default_storage.save(wasabi_path, uploaded_file)

                # 获取文件URL
                # default_storage.url() 会返回文件的完整可访问URL
                file_url = default_storage.url(saved_filename)
                file_urls.append({'url': file_url, 'name': uploaded_file.name, 'type': uploaded_file.content_type})

            except Exception as e:
                # 处理文件保存中的错误
                logger.error(f"文件上传失败: {e}")
                return JsonResponse({'error': f'文件 {uploaded_file.name} 上传失败: {e}'}, status=500)

        # 返回文件URL列表给前端
        if file_urls:
            # 返回第一个文件的URL，兼容前端当前的期望
            # 如果需要插入所有文件，前端JS的done回调需要迭代处理 file_urls
            return JsonResponse({'url': file_urls[0]['url'], 'name': file_urls[0]['name'], 'type': file_urls[0]['type']}, status=200)
        else:
            # 理论上不会走到这里，因为uploaded_files不为空时才进入这个if
            return JsonResponse({'error': '没有文件成功处理'}, status=500)

    else:
        return JsonResponse({'error': '无效的请求，没有文件数据'}, status=400)


def page_not_found_view(
        request,
        exception,
        template_name='blog/error_page.html'):
    if exception:
        logger.error(exception)
    url = request.get_full_path()
    return render(request,
                  template_name,
                  {'message': _('Sorry, the page you requested is not found, please click the home page to see other?'),
                   'statuscode': '404'},
                  status=404)


def server_error_view(request, template_name='blog/error_page.html'):
    return render(request,
                  template_name,
                  {'message': _('Sorry, the server is busy, please click the home page to see other?'),
                   'statuscode': '500'},
                  status=500)


def permission_denied_view(
        request,
        exception,
        template_name='blog/error_page.html'):
    if exception:
        logger.error(exception)
    return render(
        request, template_name, {
            'message': _('Sorry, you do not have permission to access this page?'),
            'statuscode': '403'}, status=403)


def clean_cache_view(request):
    cache.clear()
    return HttpResponse('ok')


@login_required
def upload_video(request):
    """
    This view is for direct video uploads, not necessarily from mdeditor.
    The fileupload view is modified to handle mdeditor's upload requests.
    Keeping this view for separate video upload page if needed.
    """
    if request.method == 'POST':
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.author = request.user
            video.save()
            # Redirect to the video detail page after successful upload
            return redirect('blog:video_detail', video_id=video.id)
    else:
        form = VideoUploadForm()
    # Render the upload video form template
    return render(request, 'blog/upload_video.html', {'form': form})


class VideoDetailView(DetailView):
    model = Video
    template_name = 'blog/video_detail.html' # 假设你有一个视频详情页面的模板文件为 'blog/video_detail.html'
    pk_url_kwarg = 'video_id'
    context_object_name = "video"

    def get_object(self, queryset=None):
        obj = super().get_object()
        obj.viewed()
        return obj


def membership_list(request):
    """
    会员类型列表页面视图
    """
    membership_types = MembershipType.objects.all()
    return render(request, 'blog/membership_list.html', {'membership_types': membership_types})


@login_required
def create_order(request):
    """
    创建订单
    """
    if request.method == 'POST':
        membership_type_id = request.POST.get('membership_type_id')
        try:
            membership_type = MembershipType.objects.get(id=membership_type_id)
        except MembershipType.DoesNotExist:
            # 处理会员类型不存在的错误
            return redirect('blog:membership_list') # 或者渲染一个错误页面

        user = request.user
        amount = membership_type.price
        # 生成唯一的订单号，例如使用 UUID
        order_id = f"ORD-{uuid.uuid4().hex}"

        order = Order.objects.create(
            user=user,
            membership_type=membership_type,
            order_id=order_id,
            amount=amount,
            is_paid=False # 初始状态为未支付
        )

        # TODO: 集成支付流程，目前先简单重定向
        # 可以在这里重定向到支付页面，并将订单信息传递过去

        # 简单重定向到会员列表页面，表示订单创建成功（或待支付）
        # 修改为重定向到订单详情页面
        return redirect('blog:order_detail', order_id=order.order_id)
    else:
        # 不允许非 POST 请求
        return redirect('blog:membership_list') # 或者返回 HttpResponseForbidden


@login_required
def order_detail(request, order_id):
    """
    订单详情页面视图
    """
    user = request.user  # Move user definition to the beginning
    try:
        order = Order.objects.get(order_id=order_id, user=user)
    except Order.DoesNotExist:
        # 处理订单不存在或不属于当前用户的错误
        return redirect('blog:membership_list') # 或者渲染一个错误页面

    redemption_message = None

    # Initialize context and membership status variables
    is_member = False
    user_membership_status = _('None')
    user_membership_plan = _('None')

    if hasattr(user, 'membership') and user.membership:
        if user.membership.is_membership_active():
            is_member = True
            user_membership_status = _('Active')
            user_membership_plan = user.membership.get_membership_type_display()
        else:
            is_member = False
            user_membership_status = _('Inactive / Expired')
            user_membership_plan = user.membership.get_membership_type_display()

    context = {
        'order': order,
        'redemption_message': redemption_message,
        'is_member': is_member,
        'user_membership_status': user_membership_status,
        'user_membership_plan': user_membership_plan,
        'membership_types': RedemptionCode.MEMBERSHIP_CHOICES # Pass choices to the template
    }

    if request.method == 'POST':
        redemption_code_str = request.POST.get('redemption_code').strip()
        if not redemption_code_str:
            messages.error(request, _('Please enter a redemption code.'))
            return render(request, 'blog/order_detail.html', context)

        try:
            redemption_code = RedemptionCode.objects.get(code=redemption_code_str)
        except RedemptionCode.DoesNotExist:
            messages.error(request, _('Invalid redemption code.'))
            return render(request, 'blog/order_detail.html', context)

        if redemption_code.is_used:
            messages.error(request, _('This redemption code has already been used.'))
            return render(request, 'blog/order_detail.html', context)

        # Apply the redemption code
        try:
            user_membership, created = UserMembership.objects.get_or_create(user=user)

            # Determine the correct start_date for the new membership period
            # Fetch the latest UserMembership from DB if it exists, to get accurate end_date for renewals
            current_user_membership = None
            try:
                current_user_membership = UserMembership.objects.get(user=user)
            except UserMembership.DoesNotExist:
                pass

            if created or not (current_user_membership and current_user_membership.is_membership_active()):
                # New membership or reactivating an expired/inactive one
                user_membership.start_date = timezone.now()
            else:
                # Renewal of an existing active membership
                # Use the existing end_date as the start date for the new period
                user_membership.start_date = current_user_membership.end_date

            user_membership.membership_type = redemption_code.membership_type
            user_membership.is_active = True
            user_membership.save()

            # Reload user_membership to ensure latest data from DB (optional, but good for debugging)
            user_membership = UserMembership.objects.get(user=user)
            logger.debug(f"UserMembership reloaded after save: is_active={user_membership.is_active}, start_date={user_membership.start_date}, end_date={user_membership.end_date}")

            redemption_code.is_used = True
            redemption_code.used_by = user
            redemption_code.used_time = timezone.now()
            redemption_code.save()

            messages.success(request, _(f'Congratulations! Your {user_membership.get_membership_type_display()} membership has been activated.'))

            # Mark order as paid if redemption is successful
            order.is_paid = True
            order.paid_time = timezone.now()
            order.save()

        except Exception as e:
            messages.error(request, _(f'An error occurred during redemption: {e}'))
            logger.error(f"Redemption error for user {user.username} with code {redemption_code_str}: {e}")

    # Re-evaluate user's membership status for the context after any POST operations or for GET requests
    is_member = False
    user_membership_status = _('None')
    user_membership_plan = _('None')

    # Fetch the latest user_membership object for context rendering
    try:
        latest_user_membership = UserMembership.objects.get(user=user)
        if latest_user_membership.is_membership_active():
            is_member = True
            user_membership_status = _('Active')
            user_membership_plan = latest_user_membership.get_membership_type_display()
        else:
            is_member = False
            user_membership_status = _('Inactive / Expired')
            user_membership_plan = latest_user_membership.get_membership_type_display() # Still show the plan, even if inactive
    except UserMembership.DoesNotExist:
        pass # User has no membership record

    context['is_member'] = is_member
    context['user_membership_status'] = user_membership_status
    context['user_membership_plan'] = user_membership_plan
    
    return render(request, 'blog/order_detail.html', context)


@login_required
def simulate_pay(request, order_id):
    """
    模拟支付成功处理
    """
    try:
        order = Order.objects.get(order_id=order_id, user=request.user, is_paid=False)
    except Order.DoesNotExist:
        # 订单不存在或已支付
        return redirect('blog:membership_list') # 或者重定向到订单详情页并显示信息

    # 模拟支付成功的逻辑
    order.is_paid = True
    order.paid_time = timezone.now()
    order.save()

    # 更新用户会员状态
    user = request.user
    membership_type = order.membership_type

    # 计算会员到期时间
    from datetime import timedelta
    if hasattr(user, 'membership'):
        # 用户已有会员，更新到期时间
        # 如果当前会员未过期，从当前到期时间开始计算
        # 如果当前会员已过期，从现在开始计算
        start_time = user.membership.end_date if user.membership.is_membership_active() else timezone.now()
        end_time = start_time + timedelta(days=30 * membership_type.duration_months) # 简单按30天/月计算
        user.membership.membership_type = membership_type
        user.membership.start_date = start_time # 根据逻辑，这里可能需要调整
        user.membership.end_date = end_time
        user.membership.is_active = True
        user.membership.save()
    else:
        # 用户没有会员，创建新的会员记录
        start_time = timezone.now()
        end_time = start_time + timedelta(days=30 * membership_type.duration_months) # 简单按30天/月计算
        UserMembership.objects.create(
            user=user,
            membership_type=membership_type.type,
            start_date=start_time,
            end_date=end_time,
            is_active=True
        )

    # 重定向到订单详情页面，显示支付成功信息
    return redirect('blog:order_detail', order_id=order.order_id)


@csrf_exempt
def wasabi_file_list_json(request):
    """
    Custom view to browse files in Wasabi S3 bucket.
    Returns a JSON response with file URLs and names.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden("You are not authorized to access this page.")

    current_path = request.GET.get('path', '')
    # Ensure current_path ends with a slash if it's not empty, unless it's the root.
    if current_path and not current_path.endswith('/'):
        current_path += '/'

    files_data = []
    dirs_data = []
    try:
        s3_storage = S3Boto3Storage(
            bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            access_key=settings.AWS_ACCESS_KEY_ID,
            secret_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            querystring_auth=settings.AWS_QUERYSTRING_AUTH,
            location=settings.AWS_LOCATION
        )

        logger.info(f"DEBUG: Explicit s3_storage location: {s3_storage.location}")
        logger.info(f"DEBUG: listdir path: '{current_path}'")

        # listdir returns (dirs, files) relative to the location
        dirs, files = s3_storage.listdir(current_path)

        logger.info(f"DEBUG: s3_storage.listdir('{current_path}') returned: dirs={dirs}, files={files}")
        
        for f in files:
            file_url = s3_storage.url(os.path.join(current_path, f)) # Construct full URL including path
            file_name = f # File name is already just the name
            files_data.append({
                'name': file_name,
                'url': file_url
            })
        
        for d in dirs:
            # Append directories as-is, the frontend will handle navigation
            dirs_data.append(d + '/') # Add slash to denote directory
        
        return JsonResponse({'files': files_data, 'dirs': dirs_data, 'current_path': current_path})
    except Exception as e:
        logger.error(f"Error listing files from Wasabi: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def wasabi_file_browser(request):
    """
    View to display the Wasabi file browser HTML page.
    """
    return render(request, 'blog/wasabi_file_browser.html')
