import logging
import os

from django.db import models
from django.conf import settings
from django import forms
from django.core.exceptions import FieldDoesNotExist
from django.forms import ClearableFileInput
from django.forms.widgets import CheckboxSelectMultiple, SelectMultiple
from django.template import loader
from multiselectfield import MultiSelectField as MSField
from PIL import Image
from sorl.thumbnail.shortcuts import get_thumbnail
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy
from collections import defaultdict
from .utils import get_img_extension

logger = logging.getLogger(__name__)

class MultiSelectField(MSField):
    def _get_flatchoices(self):
        flat_choices = super(models.CharField, self).flatchoices

        class MSFFlatchoices(list):
            def __bool__(self):
                return False

            __nonzero__ = __bool__

        return MSFFlatchoices(flat_choices)

    flatchoices = property(_get_flatchoices)

class CoreImageRender(object):
    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs)

        if value and hasattr(value, 'url'):
            try:
                Image.open(value)
            except OSError:
                context['thumb_img'] = None
                context['filename'] = os.path.basename(value.name)
            else:
                ext = get_img_extension(value)

                try:
                    mini = get_thumbnail(value, settings.ADMIN_THUMB_SIZE, upscale=False, format=ext)
                except Exception as e:
                    logger.warning("Unable to get the thumbnail", exc_info=e)
                else:
                    context['thumbnail_img'] = mini
                    context['filename'] = os.path.basename(value.name)
        
        template = loader.get_template(self.template_name).render(context)
        return mark_safe(template)

class CoreAdminImageWidget(CoreImageRender, ClearableFileInput):
    """Override on FileInput widget for Django admin to show
    a thumbnail image as well as a link to the current one if it has one.
    """

    template_name = 'django/forms/widgets/clearable_file_input.html'


class CoreImageWidget(CoreImageRender, ClearableFileInput):
    """Override on FileInput widget for CoreForm and CoreModelForm to show
    a thumbnail image as well as a link to the current one if it has one.
    """

    clear_checkbox_label = gettext_lazy("Remove this file")
    template_name = 'cores/widgets/clearable_file_input.html'

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Pass is_required to template (defaults to True if not set)
        context['widget']['is_required'] = getattr(self, 'is_required', True)
        return context


class CoreGroupCheckboxSelectMultiple(CheckboxSelectMultiple):
    """Override on CheckboxSelectMultiple widget for Django admin to show grouped checkbox."""

    template_name = 'cores/widgets/checkbox_select.html'

    class Media:
        js = ('cores/js/group.checkbox.js',)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['choices'] = self.choices
        return context


class CoreSlider(forms.NumberInput):
    input_type = "range"

    def __init__(self, min_value=0, max_value=10, step=1, attrs=None):
        base_attrs = {
            "min": str(min_value),
            "max": str(max_value),
            "step": str(step),
            "oninput": "this.nextElementSibling.value = this.value"
        }
        if attrs:
            base_attrs.update(attrs)
        super().__init__(attrs=base_attrs)

    def render(self, name, value, attrs=None, renderer=None):
        slider_html = super().render(name, value, attrs, renderer)
        number_html = f"<output style='padding-left: 10px; align-content: center;'>{value or 0}</output>"
        return mark_safe(f"{slider_html} {number_html}")


# MultiSelect with grouped parent - MPTT (when choice model has a parent FK)
class GroupedSelectMultiple(SelectMultiple):
    def optgroups(self, name, value, attrs=None):
        """Group options by parent when the queryset model defines a parent FK; otherwise flat."""
        grouped_choices = defaultdict(list)

        if hasattr(self.choices, 'queryset'):
            model = self.choices.queryset.model
            try:
                model._meta.get_field('parent')
            except FieldDoesNotExist:
                return super().optgroups(name, value, attrs)

            exhibits = self.choices.queryset.select_related('parent')
            exhibit_dict = {str(e.pk): e for e in exhibits}

            for option_value, option_label in self.choices:
                if option_value:  # Skip empty choice
                    exhibit = exhibit_dict.get(str(option_value))
                    if exhibit and exhibit.parent:  # Only include items with a parent
                        grouped_choices[exhibit.parent.name].append((option_value, option_label))
        else:
            # Fallback for non-queryset choices
            for option_value, option_label in self.choices:
                if option_value:
                    grouped_choices["Other"].append((option_value, option_label))

        groups = []

        # Ensure value is a set of strings for comparison
        if value is None:
            value = set()
        else:
            value = set(str(v) for v in value)
        
        # Create optgroups
        index = 0
        for group_label, options in grouped_choices.items():
            subgroup = []
            for option_value, option_label in options:
                selected = str(option_value) in value
                subgroup.append(self.create_option(
                    name, option_value, option_label, selected, index=index
                ))
                index += 1
            groups.append((group_label, subgroup, index))
        
        return groups

