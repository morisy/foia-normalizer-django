from django.contrib import admin
from .models import FOIAUpload, ColumnSynonym, StatusSynonym, ProcessingLog, ColumnMapping, StatusMapping


@admin.register(FOIAUpload)
class FOIAUploadAdmin(admin.ModelAdmin):
    list_display = ['filename', 'uploaded_at', 'uploaded_by', 'processed', 'processing_mode']
    list_filter = ['processed', 'processing_mode', 'uploaded_at']
    search_fields = ['file']
    readonly_fields = ['uploaded_at']
    
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
