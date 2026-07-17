"""ModelForms for the CRM front office (Milestone 1 + 2).

`tenant` is never a form field — the view stamps it on save so every record
stays correctly scoped to its white-label instance. Widget classes follow the
bm-design-system Slate token palette (page/surface/hairline/ink-*, accent).
"""

from django import forms

from .models import Account, Activity, Contact, Lead

INPUT = (
    "w-full rounded-xl bg-[var(--surface)] border border-[var(--hairline)] "
    "px-3 py-2 text-sm text-[var(--ink-display)] placeholder:text-[var(--ink-muted)] "
    "focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/30 outline-none"
)


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = [
            "first_name", "last_name", "email", "phone",
            "date_of_birth", "personal_notes", "account",
            "lifecycle", "territory",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT}),
            "last_name": forms.TextInput(attrs={"class": INPUT}),
            "email": forms.EmailInput(attrs={"class": INPUT}),
            "phone": forms.TextInput(attrs={"class": INPUT}),
            "date_of_birth": forms.DateInput(attrs={"class": INPUT, "type": "date"}),
            "personal_notes": forms.Textarea(attrs={"class": INPUT + " h-24 resize-none"}),
            "account": forms.Select(attrs={"class": INPUT}),
            "lifecycle": forms.Select(attrs={"class": INPUT}),
            "territory": forms.TextInput(attrs={"class": INPUT, "placeholder": "e.g. Nairobi"}),
        }


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "industry", "website", "phone", "billing_address", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "industry": forms.TextInput(attrs={"class": INPUT}),
            "website": forms.URLInput(attrs={"class": INPUT}),
            "phone": forms.TextInput(attrs={"class": INPUT}),
            "billing_address": forms.Textarea(attrs={"class": INPUT + " h-20 resize-none"}),
            "notes": forms.Textarea(attrs={"class": INPUT + " h-24 resize-none"}),
        }


class ActivityForm(forms.ModelForm):
    """Quick-log an activity against a contact (Milestone 2)."""

    class Meta:
        model = Activity
        fields = ["type", "subject", "notes", "due_at", "done"]
        widgets = {
            "type": forms.Select(attrs={"class": INPUT}),
            "subject": forms.TextInput(attrs={"class": INPUT, "placeholder": "e.g. Follow-up call"}),
            "notes": forms.Textarea(attrs={"class": INPUT + " h-20 resize-none", "placeholder": "Notes (optional)"}),
            "due_at": forms.DateTimeInput(attrs={"class": INPUT, "type": "datetime-local"}),
            "done": forms.CheckboxInput(attrs={"class": "accent-[var(--accent)] w-4 h-4"}),
        }


# BANT is scored from friendly qualifying questions (PRD excludes a manual BANT
# entry UI). Each choice value 1-3 maps directly to the underlying BANT field.
_BANT_CHOICES = {
    "budget": [
        (3, "Yes, budget is approved"),
        (2, "Exploring / budget being planned"),
        (1, "Just researching for now"),
    ],
    "authority": [
        (3, "I make the decision"),
        (2, "I influence the decision"),
        (1, "I'm gathering info for someone else"),
    ],
    "need": [
        (3, "Urgent problem to solve now"),
        (2, "A clear need, not urgent"),
        (1, "Curious / nice to have"),
    ],
    "timeline": [
        (3, "Within a month"),
        (2, "This quarter"),
        (1, "No specific timeline"),
    ],
}

SELECT = INPUT  # same Slate styling for selects


class PublicLeadForm(forms.ModelForm):
    """Public web-intake form. Friendly qualifying questions feed BANT scoring;
    the view runs services.intake_lead() to score + route + auto-respond."""

    bant_budget = forms.TypedChoiceField(
        label="Do you have budget allocated?", coerce=int,
        choices=_BANT_CHOICES["budget"], widget=forms.Select(attrs={"class": SELECT}),
    )
    bant_authority = forms.TypedChoiceField(
        label="What's your role in the decision?", coerce=int,
        choices=_BANT_CHOICES["authority"], widget=forms.Select(attrs={"class": SELECT}),
    )
    bant_need = forms.TypedChoiceField(
        label="How pressing is the need?", coerce=int,
        choices=_BANT_CHOICES["need"], widget=forms.Select(attrs={"class": SELECT}),
    )
    bant_timeline = forms.TypedChoiceField(
        label="When are you looking to start?", coerce=int,
        choices=_BANT_CHOICES["timeline"], widget=forms.Select(attrs={"class": SELECT}),
    )

    class Meta:
        model = Lead
        fields = [
            "first_name", "last_name", "email", "phone", "company",
            "territory", "source", "message",
            "bant_budget", "bant_authority", "bant_need", "bant_timeline",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT, "placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"class": INPUT, "placeholder": "Last name"}),
            "email": forms.EmailInput(attrs={"class": INPUT, "placeholder": "you@company.co.ke"}),
            "phone": forms.TextInput(attrs={"class": INPUT, "placeholder": "07xx xxx xxx"}),
            "company": forms.TextInput(attrs={"class": INPUT, "placeholder": "Business name"}),
            "territory": forms.TextInput(attrs={"class": INPUT, "placeholder": "County / town (e.g. Nairobi)"}),
            "source": forms.Select(attrs={"class": INPUT}),
            "message": forms.Textarea(attrs={"class": INPUT + " h-24 resize-none", "placeholder": "Tell us what you need…"}),
        }
