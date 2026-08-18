from django import forms

class JobFilterForm(forms.Form):
    search = forms.CharField(
        label="Search",
        widget=forms.TextInput(),
        required=False,
    )