from django import forms

class FacebookAccountFilterForm(forms.Form):
    search = forms.CharField(
        label="Search",
        widget=forms.TextInput(),
        required=False,
    )