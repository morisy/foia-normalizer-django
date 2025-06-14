from django.contrib import admin
from .models import FOIAUpload, ColumnSynonym, StatusSynonym, ProcessingLog, ColumnMapping, StatusMapping, ContributorStats


@admin.register(FOIAUpload)
class FOIAUploadAdmin(admin.ModelAdmin):
    list_display = ['filename', 'uploaded_at', 'submission_status', 'submitter_username', 'uploaded_by', 'processed']
    list_filter = ['submission_status', 'processed', 'uploaded_at']
    search_fields = ['file', 'submitter_username', 'submitter_email', 'agency']
    readonly_fields = ['uploaded_at', 'reviewed_at']
    
    fieldsets = (
        ('Upload Information', {
            'fields': ('file', 'uploaded_at', 'uploaded_by')
        }),
        ('Submitter Attribution', {
            'fields': ('submitter_username', 'submitter_email')
        }),
        ('Submission Status', {
            'fields': ('submission_status', 'reviewed_by', 'reviewed_at', 'rejection_reason')
        }),
        ('FOIA Log Metadata', {
            'fields': ('source', 'agency', 'time_period_start', 'time_period_end')
        }),
        ('Processing', {
            'fields': ('processed', 'output_file')
        })
    )
    
    def filename(self, obj):
        return obj.filename
    filename.short_description = 'File Name'


@admin.register(ColumnSynonym)
class ColumnSynonymAdmin(admin.ModelAdmin):
    list_display = ['synonym', 'standard_name']
    list_filter = ['standard_name']
    search_fields = ['synonym', 'standard_name']
    ordering = ['standard_name', 'synonym']


@admin.register(StatusSynonym)
class StatusSynonymAdmin(admin.ModelAdmin):
    list_display = ['synonym', 'standard_status']
    list_filter = ['standard_status']
    search_fields = ['synonym', 'standard_status']
    ordering = ['standard_status', 'synonym']


@admin.register(ProcessingLog)
class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = ['upload', 'log_type', 'timestamp', 'message_preview']
    list_filter = ['log_type', 'timestamp']
    search_fields = ['message', 'upload__file']
    readonly_fields = ['timestamp']
    
    def message_preview(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message'


@admin.register(ColumnMapping)
class ColumnMappingAdmin(admin.ModelAdmin):
    list_display = ['upload', 'original_column', 'mapped_column', 'confidence', 'user_confirmed']
    list_filter = ['mapped_column', 'user_confirmed']
    search_fields = ['original_column', 'mapped_column', 'upload__file']


@admin.register(StatusMapping)
class StatusMappingAdmin(admin.ModelAdmin):
    list_display = ['upload', 'original_status', 'mapped_status', 'confidence', 'user_confirmed']
    list_filter = ['mapped_status', 'user_confirmed']
    search_fields = ['original_status', 'mapped_status', 'upload__file']


@admin.register(ContributorStats)
class ContributorStatsAdmin(admin.ModelAdmin):
    list_display = ['username', 'submissions_count', 'approved_count', 'rejected_count', 'last_submission']
    list_filter = ['last_submission']
    search_fields = ['username', 'email']
    ordering = ['-approved_count', '-submissions_count']
    readonly_fields = ['submissions_count', 'approved_count', 'rejected_count', 'last_submission']
