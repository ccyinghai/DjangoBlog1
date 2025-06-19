from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UsernameField
from django.utils.translation import gettext_lazy as _
from django.contrib import admin
from django.utils.timezone import now
from datetime import timedelta
from django.contrib.admin import SimpleListFilter
from django.db.models import Q
from django.contrib import messages
import random
import string
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
import logging

# Register your models here.
from .models import BlogUser, RedemptionCode, UserMembership
from blog.models import MembershipType

logger = logging.getLogger(__name__)


class BlogUserCreationForm(forms.ModelForm):
    password = forms.CharField(label=_('password'), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_('Enter password again'), widget=forms.PasswordInput)

    class Meta:
        model = BlogUser
        fields = ('username', 'email', 'nickname', 'source',)

    def clean_password2(self):
        # Check that the two password entries match
        password = self.cleaned_data.get("password")
        password2 = self.cleaned_data.get("password2")
        if password and password2 and password != password2:
            raise forms.ValidationError(_("passwords do not match"))
        return password2

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.source = 'adminsite'
            user.save()
        return user


class BlogUserChangeForm(UserChangeForm):
    class Meta:
        model = BlogUser
        fields = '__all__'
        field_classes = {'username': UsernameField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# Custom ModelForm for UserMembership
class UserMembershipAdminForm(forms.ModelForm):
    class Meta:
        model = UserMembership
        fields = '__all__' # Or specify fields explicitly if needed


class MembershipInline(admin.StackedInline):
    model = UserMembership
    can_delete = False
    verbose_name_plural = 'Membership'
    # Use the custom form for this inline
    form = UserMembershipAdminForm
    fields = ('membership_type', 'start_date', 'end_date', 'is_active')
    extra = 0  # Don't show extra blank forms


# Custom filter for Membership Status
class MembershipStatusFilter(SimpleListFilter):
    title = _('membership status') # filter title
    parameter_name = 'membership_status' # URL query parameter name

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each tuple is the coded value
        for the option that will appear in the URL query. The second element is the
        human-readable name for the option that will appear in the right sidebar.
        """
        return [
            ('active', _('Active')),
            ('expired', _('Expired')),
            ('none', _('None')), # Users with no Membership record
            ('inactive_manual', _('Inactive (Manual')), # Users with Membership but not active
            ('has_membership', _('Has Membership (Any Status)')), # Optional: filter for any user with a Membership record
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value() == 'active':
            # Filter for users with an active membership (is_active=True and end_date >= now)
            # Use __isnull=False to filter for users *with* a related Membership object first
            return queryset.filter(membership__isnull=False, membership__is_active=True, membership__end_date__gte=now())
        if self.value() == 'expired':
            # Filter for users with an expired active membership (is_active=True and end_date < now)
             return queryset.filter(membership__isnull=False, membership__is_active=True, membership__end_date__lt=now())
        if self.value() == 'inactive_manual':
            # Filter for users with a Membership record, but explicitly marked inactive
             return queryset.filter(membership__isnull=False, membership__is_active=False)
        if self.value() == 'none':
            # Filter for users who do NOT have a Membership record
            return queryset.filter(membership__isnull=True)
        if self.value() == 'has_membership':
             # Filter for users who have ANY Membership record (active or not, expired or not)
             return queryset.filter(membership__isnull=False)


class BlogUserAdmin(UserAdmin):
    form = BlogUserChangeForm
    add_form = BlogUserCreationForm

    # Custom fieldsets for the change user form
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("nickname", "email", "source")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    # Custom add_fieldsets for the add user form
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "nickname", "source", "password", "password2"),
        }),
    )

    list_display = (
        'id',
        'nickname',
        'username',
        'email',
        'last_login',
        'date_joined',
        'source',
        'membership_status',
        'membership_plan',
    )
    list_display_links = ('id', 'username')
    ordering = ('-id',)
    inlines = (MembershipInline,)
    list_filter = (
        'is_staff',
        'is_superuser',
        'is_active',
        'date_joined',
        MembershipStatusFilter,
    )

    def membership_status(self, obj):
        # Check if the user has an active membership
        logger.debug(f"Checking membership status for user: {obj.username}")
        try:
            # Access the related UserMembership object (OneToOneField)
            membership = obj.usermembership
            logger.debug(f"UserMembership found for {obj.username}: is_active={membership.is_active}, end_date={membership.end_date}, now={now()}")
            if membership.is_active and membership.end_date and membership.end_date >= now(): # Check if end_date is not None
                 return _('Active')
            elif membership.is_active and membership.end_date and membership.end_date < now(): # Check if end_date is not None
                 return _('Expired')
            else:
                 return _('Inactive (Manual)') # More specific status
        except UserMembership.DoesNotExist:
            logger.debug(f"User {obj.username} has no UserMembership record.")
            return _('None') # No membership record
        except Exception as e:
            logger.error(f"Error in membership_status for user {obj.username}: {e}")
            return _('Error')
    membership_status.short_description = _('Membership Status') # Column header

    def membership_plan(self, obj):
        # Display the active membership plan for the user
        logger.debug(f"Checking membership plan for user: {obj.username}")
        try:
            # Access the related UserMembership object
            membership = obj.usermembership
            logger.debug(f"UserMembership found for {obj.username} (plan): is_active={membership.is_active}, end_date={membership.end_date}, type={membership.membership_type}")
            if membership.is_active and membership.end_date and membership.end_date >= now(): # Check if end_date is not None
                return membership.get_membership_type_display()
        except UserMembership.DoesNotExist:
            logger.debug(f"User {obj.username} has no UserMembership record (plan).")
            pass # No membership, return default below
        except Exception as e:
            logger.error(f"Error in membership_plan for user {obj.username}: {e}")

        return _('None') # No active membership plan
    membership_plan.short_description = _('Membership Plan') # Column header


# @admin.register(RedemptionCode)
class RedemptionCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'membership_type', 'is_used', 'used_by', 'used_time', 'created_time')
    list_filter = ('membership_type', 'is_used')
    search_fields = ('code', 'used_by__username')

    def get_form(self, request, obj=None, **kwargs):
        # Dynamically set the used_by field to read-only in the admin, if already set
        form = super().get_form(request, obj, **kwargs)
        is_used_field = form.base_fields.get('is_used')
        if is_used_field and obj and obj.is_used:
            form.base_fields['is_used'].disabled = True
            form.base_fields['used_by'].disabled = True
            form.base_fields['used_time'].disabled = True
        return form

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['generate_url'] = reverse('admin:accounts_redemptioncode_generate')
        return super().changelist_view(request, extra_context=extra_context)


def generate_redemption_codes_view(request):
    if request.method == 'POST':
        count = int(request.POST.get('_count', 10))
        membership_type = request.POST.get('_membership_type')

        if not membership_type:
            messages.error(request, _("Please select a membership type."))
            return render(request, 'admin/generate_redemption_codes.html', {
                'membership_types': RedemptionCode.MEMBERSHIP_CHOICES,
                'title': _('Generate Redemption Codes'),
                'errors': [_(f"Please select a membership type.")]
            })

        generated_codes = []
        for i in range(count):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            RedemptionCode.objects.create(code=code, membership_type=membership_type)
            generated_codes.append(code)

        messages.success(request, _(f"Successfully generated {count} {membership_type} redemption codes."))
        messages.info(request, _(f"Codes: {', '.join(generated_codes)}"))
        return HttpResponseRedirect(reverse('admin:accounts_redemptioncode_changelist'))

    membership_types = RedemptionCode.MEMBERSHIP_CHOICES
    context = {
        'membership_types': membership_types,
        'title': _('Generate Redemption Codes'),
    }
    return render(request, 'accounts/admin/generate_redemption_codes.html', context)
