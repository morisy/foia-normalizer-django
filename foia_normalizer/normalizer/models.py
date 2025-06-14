from django.db import models
from django.contrib.auth.models import User
import os


class FOIAUpload(models.Model):
    SUBMISSION_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    file = models.FileField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    
    # Submitter attribution fields
    submitter_username = models.CharField(max_length=100, blank=True, help_text="Optional username for attribution")
    submitter_email = models.EmailField(blank=True, help_text="Optional email (kept private)")
    
    # Submission queue fields
    submission_status = models.CharField(
        max_length=20,
        choices=SUBMISSION_STATUS_CHOICES,
        default='pending'
    )
    reviewed_by = models.ForeignKey(
        User, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='reviewed_uploads'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    processed = models.BooleanField(default=False)
    output_file = models.FileField(upload_to='outputs/', null=True, blank=True)
    
    # SFLF Uploader metadata fields
    source = models.TextField(blank=True, help_text="Where the FOIA log was obtained (URL or description)")
    agency = models.CharField(max_length=255, blank=True, help_text="Associated federal, state or local agency")
    time_period_start = models.DateField(null=True, blank=True, help_text="Start date of log period")
    time_period_end = models.DateField(null=True, blank=True, help_text="End date of log period")
    
    def __str__(self):
        return f"{self.file.name} - {self.uploaded_at}"
    
    @property
    def filename(self):
        return os.path.basename(self.file.name)


class ColumnSynonym(models.Model):
    standard_name = models.CharField(max_length=255, help_text="Standard SFLF column name")
    synonym = models.CharField(max_length=255, help_text="Alternative column name")
    
    class Meta:
        unique_together = ('standard_name', 'synonym')
    
    def __str__(self):
        return f"{self.synonym} -> {self.standard_name}"


class StatusSynonym(models.Model):
    standard_status = models.CharField(max_length=255, help_text="Standard SFLF status")
    synonym = models.CharField(max_length=255, help_text="Alternative status name")
    
    class Meta:
        unique_together = ('standard_status', 'synonym')
    
    def __str__(self):
        return f"{self.synonym} -> {self.standard_status}"


class ProcessingLog(models.Model):
    upload = models.ForeignKey(FOIAUpload, on_delete=models.CASCADE, related_name='logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    log_type = models.CharField(
        max_length=20,
        choices=[
            ('info', 'Info'),
            ('warning', 'Warning'),
            ('error', 'Error'),
            ('openai', 'OpenAI Request')
        ]
    )
    message = models.TextField()
    
    def __str__(self):
        return f"{self.upload.filename} - {self.log_type}: {self.message[:50]}"


class ColumnMapping(models.Model):
    upload = models.ForeignKey(FOIAUpload, on_delete=models.CASCADE, related_name='column_mappings')
    original_column = models.CharField(max_length=255)
    mapped_column = models.CharField(max_length=255)
    confidence = models.FloatField(null=True, blank=True, help_text="AI confidence score")
    user_confirmed = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('upload', 'original_column')
    
    def __str__(self):
        return f"{self.original_column} -> {self.mapped_column}"


class StatusMapping(models.Model):
    upload = models.ForeignKey(FOIAUpload, on_delete=models.CASCADE, related_name='status_mappings')
    original_status = models.CharField(max_length=255)
    mapped_status = models.CharField(max_length=255)
    confidence = models.FloatField(null=True, blank=True, help_text="AI confidence score")
    user_confirmed = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('upload', 'original_status')
    
    def __str__(self):
        return f"{self.original_status} -> {self.mapped_status}"


class ContributorStats(models.Model):
    """Track contributor statistics for the leaderboard"""
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(blank=True)  # Private, for internal tracking
    submissions_count = models.IntegerField(default=0)
    approved_count = models.IntegerField(default=0)
    rejected_count = models.IntegerField(default=0)
    last_submission = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-approved_count', '-submissions_count']
    
    def __str__(self):
        return f"{self.username} - {self.approved_count} approved"
