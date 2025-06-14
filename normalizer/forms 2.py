from django import forms
from .models import FOIAUpload
import os


class FileUploadForm(forms.ModelForm):
    class Meta:
        model = FOIAUpload
        fields = ['file', 'source', 'agency', 'time_period_start', 'time_period_end']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.csv,.xlsx,.xls',
                'id': 'file-input'
            }),
            'source': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter source URL or description (e.g., https://example.gov/foia-log or "Provided via email by J. Smith")'
            }),
            'agency': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., FBI, Federal or City of Portland, Oregon'
            }),
            'time_period_start': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'time_period_end': forms.DateInput(attrs={
                'class': 'form-control', 
                'type': 'date'
            })
        }
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Check file extension
            file_ext = os.path.splitext(file.name)[1].lower()
            allowed_extensions = ['.csv', '.xlsx', '.xls']
            
            if file_ext not in allowed_extensions:
                raise forms.ValidationError(
                    f'Invalid file format. Allowed formats: {", ".join(allowed_extensions)}'
                )
            
            # Check file size (50MB limit)
            if file.size > 50 * 1024 * 1024:
                raise forms.ValidationError('File too large. Maximum size is 50MB.')
        
        return file