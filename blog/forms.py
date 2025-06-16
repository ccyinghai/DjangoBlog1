import logging

from django import forms
from haystack.forms import SearchForm

from .models import Video

logger = logging.getLogger(__name__)


class BlogSearchForm(SearchForm):
    querydata = forms.CharField(required=True)

    def search(self):
        datas = super(BlogSearchForm, self).search()
        if not self.is_valid():
            return self.no_query_found()

        if self.cleaned_data['querydata']:
            logger.info(self.cleaned_data['querydata'])
        return datas


class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ['title', 'video_file']
