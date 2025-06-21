from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.core.paginator import Paginator
from django.urls import reverse
from .models import FOIAUpload, ColumnMapping, StatusMapping, ProcessingLog
from .forms import FileUploadForm
from .utils import FOIANormalizer
import json
import os


def home(request):
    """Home page with upload interface"""
    form = FileUploadForm()
    recent_uploads = FOIAUpload.objects.order_by('-uploaded_at')[:10]
    return render(request, 'normalizer/home.html', {
        'form': form,
        'recent_uploads': recent_uploads
    })


def upload_file(request):
    """Handle file upload via AJAX"""
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            upload = form.save(commit=False)
            if request.user.is_authenticated:
                upload.uploaded_by = request.user
            upload.processing_mode = request.POST.get('mode', 'manual')
            upload.save()
            
            # For AI Assist mode, process immediately
            if upload.processing_mode == 'ai_assist':
                try:
                    process_upload(upload)
                    # Refresh the upload object to ensure it's up to date
                    upload.refresh_from_db()
                    return JsonResponse({
                        'success': True,
                        'upload_id': upload.id,
                        'redirect_url': reverse('file_detail', args=[upload.id])
                    })
                except Exception as e:
                    # Log the error for debugging
                    from .models import ProcessingLog
                    ProcessingLog.objects.create(
                        upload=upload,
                        log_type='error',
                        message=f'AI Assist processing failed: {str(e)}'
                    )
                    return JsonResponse({
                        'success': False,
                        'error': f'Processing failed: {str(e)}'
                    })
            else:
                # Manual mode - redirect to review page
                return JsonResponse({
                    'success': True,
                    'upload_id': upload.id,
                    'redirect_url': reverse('manual_review', args=[upload.id])
                })
        
        return JsonResponse({
            'success': False,
            'errors': form.errors
        })
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


def manual_review(request, upload_id):
    """Manual review interface for column and status mappings"""
    upload = get_object_or_404(FOIAUpload, id=upload_id)
    
    if request.method == 'POST':
        # Process the manual mappings
        try:
            # Update column mappings based on form data
            for key, value in request.POST.items():
                if key.startswith('column_'):
                    original_col = key.replace('column_', '').replace('_', ' ')
                    mapping = ColumnMapping.objects.filter(
                        upload=upload, 
                        original_column=original_col
                    ).first()
                    if mapping:
                        mapping.mapped_column = value
                        mapping.user_confirmed = True
                        mapping.save()
                
                elif key.startswith('status_'):
                    original_status = key.replace('status_', '').replace('_', ' ')
                    mapping = StatusMapping.objects.filter(
                        upload=upload,
                        original_status=original_status
                    ).first()
                    if mapping:
                        mapping.mapped_status = value
                        mapping.user_confirmed = True
                        mapping.save()
            
            # Process the file with confirmed mappings
            process_upload(upload)
            messages.success(request, 'File processed successfully!')
            return redirect('file_detail', upload_id=upload.id)
        
        except Exception as e:
            messages.error(request, f'Error processing file: {str(e)}')
    
    # Initial processing to get mappings and preview data
    preview_data = None
    if not upload.column_mappings.exists():
        try:
            normalizer = FOIANormalizer(upload)
            df = normalizer.load_file()
            column_mappings = normalizer.map_columns(df)
            
            # Generate preview data for the UI
            preview_data = normalizer.generate_preview_data(df, column_mappings)
            
            # Find status column and map statuses
            status_col = None
            for mapping in upload.column_mappings.all():
                if mapping.mapped_column == 'status':
                    status_col = mapping.original_column
                    break
            
            if status_col:
                normalizer.map_statuses(df, status_col)
        
        except Exception as e:
            messages.error(request, f'Error analyzing file: {str(e)}')
    else:
        # Generate preview data from existing mappings
        try:
            normalizer = FOIANormalizer(upload)
            df = normalizer.load_file()
            column_mappings = {}
            for mapping in upload.column_mappings.all():
                column_mappings[mapping.original_column] = mapping.mapped_column
            preview_data = normalizer.generate_preview_data(df, column_mappings)
        except Exception as e:
            messages.warning(request, f'Could not generate preview: {str(e)}')
    
    column_mappings = upload.column_mappings.all()
    status_mappings = upload.status_mappings.all()
    
    # Available SFLF columns and statuses for dropdowns
    sflf_columns = [
        'request id', 'requester', 'requester organization', 'subject',
        'date requested', 'date perfected', 'date completed', 'status',
        'exemptions cited', 'fee category', 'fee waiver', 'fees charged',
        'processed under privacy act'
    ]
    
    sflf_statuses = [
        'processed', 'appealing', 'fix', 'payment', 'lawsuit',
        'rejected', 'no_docs', 'done', 'partial', 'abandoned', ''
    ]
    
    return render(request, 'normalizer/manual_review.html', {
        'upload': upload,
        'column_mappings': column_mappings,
        'status_mappings': status_mappings,
        'sflf_columns': sflf_columns,
        'sflf_statuses': sflf_statuses,
        'preview_data': preview_data,
    })


def file_detail(request, upload_id):
    """Display file details and processing logs"""
    upload = get_object_or_404(FOIAUpload, id=upload_id)
    logs = upload.logs.order_by('-timestamp')
    
    # Pagination for logs
    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page')
    page_logs = paginator.get_page(page_number)
    
    return render(request, 'normalizer/file_detail.html', {
        'upload': upload,
        'logs': page_logs,
    })


def file_list(request):
    """List all uploaded files"""
    uploads = FOIAUpload.objects.order_by('-uploaded_at')
    
    # Pagination
    paginator = Paginator(uploads, 20)
    page_number = request.GET.get('page')
    page_uploads = paginator.get_page(page_number)
    
    return render(request, 'normalizer/file_list.html', {
        'uploads': page_uploads,
    })


def download_file(request, upload_id):
    """Download processed file"""
    try:
        upload = get_object_or_404(FOIAUpload, id=upload_id)
        
        if not upload.processed or not upload.output_file:
            messages.error(request, 'File has not been processed yet.')
            return redirect('file_detail', upload_id=upload.id)
        
        try:
            response = FileResponse(
                upload.output_file.open('rb'),
                as_attachment=True,
                filename=os.path.basename(upload.output_file.name)
            )
            return response
        except FileNotFoundError:
            messages.error(request, 'Processed file not found.')
            return redirect('file_detail', upload_id=upload.id)
    except Exception as e:
        messages.error(request, f'Error accessing file: {str(e)}')
        return redirect('file_list')


def process_upload(upload):
    """Process an upload (used by both manual and AI assist modes)"""
    from .models import ProcessingLog
    
    try:
        ProcessingLog.objects.create(
            upload=upload,
            log_type='info',
            message=f'Starting processing in {upload.processing_mode} mode'
        )
        
        normalizer = FOIANormalizer(upload)
        
        # Load the file
        df = normalizer.load_file()
        
        # If no mappings exist yet, generate them
        if not upload.column_mappings.exists():
            ProcessingLog.objects.create(
                upload=upload,
                log_type='info',
                message='Generating column mappings...'
            )
            
            column_mappings = normalizer.map_columns(df)
            
            # Find status column and map statuses
            status_col = None
            for original_col, mapped_col in column_mappings.items():
                if mapped_col == 'status':
                    status_col = original_col
                    break
            
            if status_col:
                ProcessingLog.objects.create(
                    upload=upload,
                    log_type='info',
                    message=f'Mapping status values from column: {status_col}'
                )
                normalizer.map_statuses(df, status_col)
        
        # Get confirmed mappings from database
        column_mappings = {}
        for mapping in upload.column_mappings.all():
            column_mappings[mapping.original_column] = mapping.mapped_column
        
        status_mappings = {}
        for mapping in upload.status_mappings.all():
            status_mappings[mapping.original_status] = mapping.mapped_status
        
        ProcessingLog.objects.create(
            upload=upload,
            log_type='info',
            message=f'Normalizing data with {len(column_mappings)} column mappings and {len(status_mappings)} status mappings'
        )
        
        # Normalize the dataframe
        df_normalized = normalizer.normalize_dataframe(df, column_mappings, status_mappings)
        
        # Save the normalized file
        normalizer.save_normalized_file(df_normalized)
        
        ProcessingLog.objects.create(
            upload=upload,
            log_type='info',
            message=f'Processing completed successfully. Output: {len(df_normalized)} rows, {len(df_normalized.columns)} columns'
        )
        
        return upload
        
    except Exception as e:
        ProcessingLog.objects.create(
            upload=upload,
            log_type='error',
            message=f'Processing failed at step: {str(e)}'
        )
        raise
