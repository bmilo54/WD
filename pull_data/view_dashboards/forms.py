from django import forms
from django.contrib.auth.forms import AuthenticationForm

class DashboardLoginForm(AuthenticationForm):
    username = forms.CharField(label="Username")

    def __init__(self, *args, **kwargs):
        super(DashboardLoginForm, self).__init__(*args, **kwargs)

        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
    
        self.fields['username'].widget.attrs['placeholder'] = 'Your Username'
        self.fields['password'].widget.attrs['placeholder'] = 'Your Password'