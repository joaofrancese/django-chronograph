from .models import Job, Log
from django import forms
from django.conf.urls import patterns, url
from django.contrib import admin, messages
from django.core.urlresolvers import reverse
from django.db import models
from django.forms import Textarea
from django.http import HttpResponseRedirect, Http404
from django.template.defaultfilters import linebreaks
from django.utils import dateformat, formats
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.translation import ugettext_lazy as _
try:
    from django.forms.utils import flatatt  # Django >= 1.7
except ImportError:
    from django.forms.util import flatatt  # Django < 1.7


class HTMLWidget(forms.Widget):
    def __init__(self, rel=None, attrs=None):
        self.rel = rel
        super(HTMLWidget, self).__init__(attrs)

    def render(self, name, value, attrs=None):
        if self.rel is not None:
            key = self.rel.get_related_field().name
            obj = self.rel.to._default_manager.get(**{key: value})
            related_url = '../../../%s/%s/%d/' % (self.rel.to._meta.app_label, self.rel.to._meta.object_name.lower(), value)
            value = "<a href='%s'>%s</a>" % (related_url, escape(obj))
        else:
            value = escape(value)

        final_attrs = self.build_attrs(attrs, name=name)
        return mark_safe("<div%s>%s</div>" % (flatatt(final_attrs), linebreaks(value)))

class JobForm(forms.ModelForm):
    class Meta:
        widgets = {
            'command': Textarea(attrs={'cols': 80, 'rows': 6}),
            'shell_command': Textarea(attrs={'cols': 80, 'rows': 6}),
            'args': Textarea(attrs={'cols': 80, 'rows': 6}),
        }

    def clean_shell_command(self):
        if self.cleaned_data.get('command', '').strip() and \
                self.cleaned_data.get('shell_command', '').strip():
            raise forms.ValidationError(_("Can't specify a shell_command if "
                              "a django admin command is already specified"))
        return self.cleaned_data['shell_command']

    def clean(self):
        cleaned_data = super(JobForm, self).clean()
        if len(cleaned_data.get('command', '').strip()) and \
                len(cleaned_data.get('shell_command', '').strip()):
            raise forms.ValidationError(_("Must specify either command or "
                                        "shell command"))
        return cleaned_data

class JobAdmin(admin.ModelAdmin):
    actions = ['disable_jobs', 'enable_jobs', 'reset_jobs']
    form = JobForm
    list_display = (
        'job_success', '_enabled', 'name', 'last_run_with_link', 'next_run_', 'get_timeuntil',
        'frequency', 'started_on', 'is_running', 'run_button', 'view_logs_button',
    )
    list_display_links = ('name',)
    list_filter = ('last_run_successful', 'frequency', 'disabled')
    search_fields = ('name',)
    ordering = ('last_run',)
    filter_horizontal = ('subscribers', 'info_subscribers')

    fieldsets = (
        (_('Job Details'), {
            'classes': ('wide',),
            'fields': ('name', 'disabled', 'command', 'shell_command', 'run_in_shell', 'args', 'atomic',)
        }),
        (_('E-mail subscriptions'), {
            'classes': ('wide',),
            'fields': ('info_subscribers', 'subscribers',)
        }),
        (_('Frequency options'), {
            'classes': ('wide',),
            'fields': ('frequency', 'next_run', 'params',)
        }),
    )

    def enable_jobs(self, request, queryset):
        return queryset.update(disabled=False)

    def disable_jobs(self, request, queryset):
        return queryset.update(disabled=True)

    def reset_jobs(self, request, queryset):
        return queryset.update(is_running=False, started_on=None)

    def _enabled(self, obj):
        return not obj.disabled
    _enabled.short_description = _('Enabled')
    _enabled.admin_order_field = 'disabled'
    _enabled.boolean = True

    def last_run_with_link(self, obj):
        if not obj.last_run:
            return None
        format_ = formats.get_format('DATETIME_FORMAT')
        value = capfirst(dateformat.format(obj.last_run, format_))

        log_id = obj.log_set.latest('run_date').id

        try:
            # Old way
            reversed_url = reverse('chronograph_log_change', args=(log_id,))
        except:
            # New way
            reversed_url = reverse('admin:chronograph_log_change', args=(log_id,))

        return '<a href="%s">%s</a>' % (reversed_url, value)
    last_run_with_link.allow_tags = True
    last_run_with_link.short_description = _('Last run')
    last_run_with_link.admin_order_field = 'last_run'

    def next_run_(self, obj):
        if obj.adhoc_run:
            return 'Immediate run scheduled'
        elif not obj.next_run:
            return 'Not scheduled'
        else:
            format_ = formats.get_format('DATETIME_FORMAT')
            return capfirst(dateformat.format(obj.next_run, format_))
    next_run_.short_description = _('Next run')
    next_run_.admin_order_field = 'next_run'



    def job_success(self, obj):
        return obj.last_run_successful
    job_success.short_description = _(u'OK')
    job_success.boolean = True

    def run_button(self, obj):
        disabled = 'disabled="disabled" ' if obj.adhoc_run else ''
        on_click = "window.location='%d/run/?inline=1';" % obj.id
        return '<input type="button" onclick="%s" value="Run" %s/>' % (on_click, disabled)
    run_button.allow_tags = True
    run_button.short_description = _('Run')

    def view_logs_button(self, obj):
        on_click = "window.location='../log/?job=%d';" % obj.id
        return '<input type="button" onclick="%s" value="View Logs" />' % on_click
    view_logs_button.allow_tags = True
    view_logs_button.short_description = _('Logs')

    def run_job_view(self, request, pk):
        """
        Runs the specified job.
        """
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            raise Http404
        job.adhoc_run = True
        job.save()
        messages.success(request, 'The job "%(job)s" has been queued for running' % {'job': job.name})

        if 'inline' in request.GET:
            redirect = request.path + '../../'
        else:
            redirect = request.REQUEST.get('next', request.path + "../")

        return HttpResponseRedirect(redirect)

    def get_urls(self):
        urls = super(JobAdmin, self).get_urls()
        my_urls = patterns('',
            url(r'^(.+)/run/$', self.admin_site.admin_view(self.run_job_view), name="chronograph_job_run"),
        )
        return my_urls + urls

class LogAdmin(admin.ModelAdmin):
    list_display = ('job_name', 'run_date', 'end_date', 'job_duration', 'job_success', 'output', 'errors',)
    list_filter = ('job', 'run_date', 'end_date', 'success')
    search_fields = ('stdout', 'stderr', 'job__name', 'job__command')
    date_hierarchy = 'run_date'
    fieldsets = (
        (None, {
            'fields': ('job',)
        }),
        (_('Output'), {
            'fields': ('stdout', 'stderr',)
        }),
    )

    def job_duration(self, obj):
        return "%s" % (obj.get_duration())
    job_duration.short_description = _(u'Duration')

    def job_name(self, obj):
        return obj.job.name
    job_name.short_description = _(u'Name')

    def job_success(self, obj):
        return obj.success
    job_success.short_description = _(u'OK')
    job_success.boolean = True

    def output(self, obj):
        result = obj.stdout or ''
        if len(result) > 40:
            result = result[:40] + '...'

        return result or _('(No output)')

    def errors(self, obj):
        result = obj.stderr or ''
        if len(result) > 40:
            result = result[:40] + '...'

        return result or _('(No errors)')

    def has_add_permission(self, request):
        return False

    def formfield_for_dbfield(self, db_field, **kwargs):
        request = kwargs.pop("request", None)

        if isinstance(db_field, models.TextField):
            kwargs['widget'] = HTMLWidget()
            return db_field.formfield(**kwargs)

        if isinstance(db_field, models.ForeignKey):
            kwargs['widget'] = HTMLWidget(db_field.rel)
            return db_field.formfield(**kwargs)

        return super(LogAdmin, self).formfield_for_dbfield(db_field, **kwargs)

admin.site.register(Job, JobAdmin)
admin.site.register(Log, LogAdmin)
