from django import forms

MAX_BODY = 5000


class AnnouncementForm(forms.Form):
    title = forms.CharField(max_length=200)
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"required": "Write the announcement first."},
    )
    is_pinned = forms.BooleanField(required=False, label="Pin to top")

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if len(body) > MAX_BODY:
            raise forms.ValidationError("Keep the announcement under 5000 characters.")
        return body
