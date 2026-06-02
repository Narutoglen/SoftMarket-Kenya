from django import forms

from .models import DeveloperApplication, ProjectRequest


class ProjectRequestForm(forms.Form):
    name = forms.CharField(max_length=160)
    phone = forms.CharField(max_length=40)
    email = forms.EmailField()
    service = forms.CharField(max_length=140)
    budget = forms.CharField(max_length=80)
    timeline = forms.CharField(max_length=80)
    details = forms.CharField()
    utm_source = forms.CharField(required=False, max_length=120)
    utm_medium = forms.CharField(required=False, max_length=120)
    utm_campaign = forms.CharField(required=False, max_length=120)

    def save(self):
        return ProjectRequest.objects.create(
            name=self.cleaned_data["name"],
            phone=self.cleaned_data["phone"],
            email=self.cleaned_data["email"],
            service_label=self.cleaned_data["service"],
            budget=self.cleaned_data["budget"],
            timeline=self.cleaned_data["timeline"],
            details=self.cleaned_data["details"],
            utm_source=self.cleaned_data.get("utm_source", ""),
            utm_medium=self.cleaned_data.get("utm_medium", ""),
            utm_campaign=self.cleaned_data.get("utm_campaign", ""),
        )


class DeveloperApplicationForm(forms.Form):
    developerName = forms.CharField(max_length=160)
    stack = forms.CharField(max_length=260)
    portfolio = forms.URLField()

    def save(self):
        return DeveloperApplication.objects.create(
            name=self.cleaned_data["developerName"],
            stack=self.cleaned_data["stack"],
            portfolio_url=self.cleaned_data["portfolio"],
        )
