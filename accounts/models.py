from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from djangoblog.utils import get_current_site
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import F
import datetime
import random
import string
import logging

logger = logging.getLogger(__name__)


# Create your models here.

class BlogUser(AbstractUser):
    nickname = models.CharField(_('nick name'), max_length=100, blank=True)
    creation_time = models.DateTimeField(_('creation time'), default=now)
    last_modify_time = models.DateTimeField(_('last modify time'), default=now)
    source = models.CharField(_('create source'), max_length=100, blank=True)

    def get_absolute_url(self):
        return reverse(
            'blog:author_detail', kwargs={
                'author_name': self.username})

    def __str__(self):
        return self.email

    def get_full_url(self):
        from django.contrib.sites.models import Site
        site = Site.objects.get_current().domain
        url = "https://{site}{path}".format(site=site,
                                            path=self.get_absolute_url())
        return url

    class Meta:
        ordering = ['-id']
        verbose_name = _('user')
        verbose_name_plural = verbose_name
        get_latest_by = 'id'


class OauthExg(models.Model):
    user = models.ForeignKey(BlogUser, on_delete=models.CASCADE)
    openid = models.CharField(max_length=64, db_index=True)
    realname = models.CharField(max_length=64, null=True, blank=True)
    nickname = models.CharField(max_length=64, null=True, blank=True)
    gender = models.CharField(max_length=16, null=True, blank=True)
    city = models.CharField(max_length=64, null=True, blank=True)
    province = models.CharField(max_length=64, null=True, blank=True)
    country = models.CharField(max_length=64, null=True, blank=True)
    figureurl = models.CharField(max_length=256, null=True, blank=True)
    is_bind_user = models.BooleanField(default=False)
    type = models.CharField(max_length=64, null=True, blank=True)

    created_time = models.DateTimeField(default=now)
    last_mod_time = models.DateTimeField(default=now)

    def __str__(self):
        return self.user.username

    class Meta:
        verbose_name = _('Oauth Login Info')
        verbose_name_plural = _('Oauth Login Info')
        ordering = ['-created_time']


class ReadingRecord(models.Model):
    user = models.ForeignKey(BlogUser, on_delete=models.CASCADE)
    article = models.ForeignKey(
        'blog.Article',
        on_delete=models.CASCADE,
        verbose_name=_('Article')
    )
    is_read = models.BooleanField(default=False)
    created_time = models.DateTimeField(default=now)
    last_mod_time = models.DateTimeField(default=now)

    def __str__(self):
        return self.user.username

    class Meta:
        verbose_name = _('Reading Record')
        verbose_name_plural = _('Reading Record')
        ordering = ['-created_time']


class UserMembership(models.Model):
    MEMBERSHIP_CHOICES = (
        ('month', _('Monthly Membership')),
        ('quarter', _('Quarterly Membership')),
        ('lifetime', _('Lifetime Membership')),
    )

    user = models.OneToOneField(BlogUser, on_delete=models.CASCADE, verbose_name=_('User'))
    membership_type = models.CharField(max_length=20, choices=MEMBERSHIP_CHOICES, default='month', verbose_name=_('Membership Type'))
    start_date = models.DateTimeField(default=now, verbose_name=_('Start Date'))
    end_date = models.DateTimeField(blank=True, null=True, verbose_name=_('End Date'))
    is_active = models.BooleanField(default=False, verbose_name=_('Is Active'))
    created_time = models.DateTimeField(default=now)
    last_mod_time = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.user.username} - {self.get_membership_type_display()}"

    def is_membership_active(self):
        # Checks if the membership is active and not expired
        from django.utils import timezone
        return self.is_active and self.end_date and self.end_date >= timezone.now()

    def save(self, *args, **kwargs):
        logger.debug(f"UserMembership save called for user {self.user.username}. Initial is_active: {self.is_active}, start_date: {self.start_date}, end_date: {self.end_date}")

        if self.is_active:
            # The start_date should be set by the view before calling save, or defaults to now().
            # This save method will now only calculate end_date based on the provided start_date.
            if not self.start_date:
                self.start_date = now() # Default to now if not explicitly set (e.g., for new objects)

            # Calculate end_date based on membership_type relative to start_date
            if self.membership_type == 'month':
                self.end_date = self.start_date + datetime.timedelta(days=30)
            elif self.membership_type == 'quarter':
                self.end_date = self.start_date + datetime.timedelta(days=90)
            elif self.membership_type == 'lifetime':
                self.end_date = datetime.datetime(2099, 12, 31, 23, 59, 59)
        # Removed else branch that set start_date and end_date to None when is_active is False
        # This prevents 'Column cannot be null' error for start_date.

        super().save(*args, **kwargs)
        logger.debug(f"UserMembership save completed for user {self.user.username}. Final is_active: {self.is_active}, start_date: {self.start_date}, end_date: {self.end_date}")

    class Meta:
        verbose_name = _('User Membership')
        verbose_name_plural = _('User Memberships')
        ordering = ['-created_time']


class RedemptionCode(models.Model):
    MEMBERSHIP_CHOICES = (
        ('month', _('Monthly Membership')),
        ('quarter', _('Quarterly Membership')),
        ('lifetime', _('Lifetime Membership')),
    )
    code = models.CharField(max_length=20, unique=True, verbose_name=_('Redemption Code'))
    membership_type = models.CharField(max_length=20, choices=MEMBERSHIP_CHOICES, verbose_name=_('Membership Type'))
    is_used = models.BooleanField(default=False, verbose_name=_('Is Used'))
    used_by = models.ForeignKey(BlogUser, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('Used By'))
    used_time = models.DateTimeField(null=True, blank=True, verbose_name=_('Used Time'))
    created_time = models.DateTimeField(default=now, verbose_name=_('Created Time'))

    def __str__(self):
        return self.code

    class Meta:
        verbose_name = _('Redemption Code')
        verbose_name_plural = _('Redemption Codes')
        ordering = ['-created_time']
