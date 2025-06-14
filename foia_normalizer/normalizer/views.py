from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q, Count, F
from .models import FOIAUpload, ColumnMapping, StatusMapping, ProcessingLog, ContributorStats
from .forms import FileUploadForm, ApprovalForm
from .utils import FOIANormalizer
import json
import os


def home(request):
    """Home page with upload interface"""
    form = FileUploadForm()
    recent_uploads = FOIAUpload.objects.filter(
        submission_status='approved'
    ).order_by('-uploaded_at')[:10]
    
    # Get stats for display
    stats = {
        'total_submissions': FOIAUpload.objects.count(),
        'approved_submissions': FOIAUpload.objects.filter(submission_status='approved').count(),
        'pending_submissions': FOIAUpload.objects.filter(submission_status='pending').count(),
        'top_contributors': ContributorStats.objects.filter(approved_count__gt=0)[:5]
    }
    
    return render(request, 'normalizer/home.html', {
        'form': form,
        'recent_uploads': recent_uploads,
        'stats': stats
    })


def upload_file(request):
    """Handle file upload via AJAX - always goes to AI-assisted manual review"""
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            upload = form.save(commit=False)
            if request.user.is_authenticated:
                upload.uploaded_by = request.user
            upload.save()
            
            # Update contributor stats if username provided
            if upload.submitter_username:
                contributor, created = ContributorStats.objects.get_or_create(
                    username=upload.submitter_username,
                    defaults={'email': upload.submitter_email}
                )
                contributor.submissions_count = F('submissions_count') + 1
                contributor.last_submission = timezone.now()
                if upload.submitter_email and not contributor.email:
                    contributor.email = upload.submitter_email
                contributor.save()
            
            # Always redirect to AI-assisted manual review
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
    """AI-assisted manual review interface for column and status mappings"""
    upload = get_object_or_404(FOIAUpload, id=upload_id)
    
    if request.method == 'POST':
        # Process the manual mappings and submit for approval
        try:
            # Handle manual status column selection
            manual_status_column = request.POST.get('manual_status_column')
            if manual_status_column:
                # Update column mapping to mark this as the status column
                mapping, created = ColumnMapping.objects.update_or_create(
                    upload=upload,
                    original_column=manual_status_column,
                    defaults={
                        'mapped_column': 'status',
                        'confidence': 1.0,
                        'user_confirmed': True
                    }
                )
                
                # Process dynamic status mappings
                normalizer = FOIANormalizer(upload)
                df = normalizer.load_file()
                if manual_status_column in df.columns:
                    normalizer.map_statuses(df, manual_status_column)
            
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
                
                elif key.startswith('dynamic_status_'):
                    # Handle dynamic status mappings from manual selection
                    original_status = key.replace('dynamic_status_', '').replace('_', ' ')
                    mapping, created = StatusMapping.objects.update_or_create(
                        upload=upload,
                        original_status=original_status,
                        defaults={
                            'mapped_status': value,
                            'confidence': 1.0,
                            'user_confirmed': True
                        }
                    )
            
            # Process the file and set to pending approval
            process_upload(upload)
            upload.submission_status = 'pending'
            upload.save()
            
            messages.success(request, 'Your submission has been processed and submitted for approval!')
            return redirect('submission_status', upload_id=upload.id)
        
        except Exception as e:
            messages.error(request, f'Error processing file: {str(e)}')
    
    # Initial AI-assisted processing to get mappings and preview data
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
    
    # Get all unique status values from potential status columns
    potential_status_values = {}
    try:
        normalizer = FOIANormalizer(upload)
        df = normalizer.load_file()
        
        # Look for columns that might contain status values
        status_keywords = ['status', 'state', 'disposition', 'outcome', 'result']
        for col in df.columns:
            col_lower = str(col).lower()
            if any(keyword in col_lower for keyword in status_keywords):
                # Get unique values from this column
                unique_values = df[col].dropna().unique()
                if len(unique_values) > 0 and len(unique_values) < 50:  # Reasonable number of statuses
                    potential_status_values[col] = list(unique_values)
    except Exception as e:
        # Continue without status value detection
        pass
    
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
        'potential_status_values': potential_status_values,
    })


@login_required
def submission_queue(request):
    """Queue of pending submissions for authenticated users to review"""
    if not request.user.is_authenticated:
        messages.error(request, 'You must be logged in to access the submission queue.')
        return redirect('home')
    
    pending_uploads = FOIAUpload.objects.filter(
        submission_status='pending'
    ).order_by('-uploaded_at')
    
    # Pagination
    paginator = Paginator(pending_uploads, 10)
    page_number = request.GET.get('page')
    page_uploads = paginator.get_page(page_number)
    
    return render(request, 'normalizer/submission_queue.html', {
        'uploads': page_uploads,
    })


@login_required
def approve_submission(request, upload_id):
    """Approve or reject a submission"""
    if not request.user.is_authenticated:
        messages.error(request, 'You must be logged in to approve submissions.')
        return redirect('home')
    
    upload = get_object_or_404(FOIAUpload, id=upload_id, submission_status='pending')
    
    if request.method == 'POST':
        form = ApprovalForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            rejection_reason = form.cleaned_data.get('rejection_reason', '')
            
            upload.reviewed_by = request.user
            upload.reviewed_at = timezone.now()
            
            if action == 'approve':
                upload.submission_status = 'approved'
                messages.success(request, 'Submission approved successfully!')
                
                # Update contributor stats
                if upload.submitter_username:
                    contributor, created = ContributorStats.objects.get_or_create(
                        username=upload.submitter_username,
                        defaults={'email': upload.submitter_email}
                    )
                    contributor.approved_count = F('approved_count') + 1
                    contributor.save()
                    
            else:  # reject
                upload.submission_status = 'rejected'
                upload.rejection_reason = rejection_reason
                messages.info(request, 'Submission rejected.')
                
                # Update contributor stats
                if upload.submitter_username:
                    contributor, created = ContributorStats.objects.get_or_create(
                        username=upload.submitter_username,
                        defaults={'email': upload.submitter_email}
                    )
                    contributor.rejected_count = F('rejected_count') + 1
                    contributor.save()
            
            upload.save()
            return redirect('submission_queue')
    else:
        form = ApprovalForm()
    
    # Get file details and logs for review
    logs = upload.logs.order_by('-timestamp')
    column_mappings = upload.column_mappings.all()
    status_mappings = upload.status_mappings.all()
    
    return render(request, 'normalizer/approve_submission.html', {
        'upload': upload,
        'form': form,
        'logs': logs,
        'column_mappings': column_mappings,
        'status_mappings': status_mappings,
    })


def submission_status(request, upload_id):
    """Show submission status to submitter"""
    upload = get_object_or_404(FOIAUpload, id=upload_id)
    
    return render(request, 'normalizer/submission_status.html', {
        'upload': upload,
    })


def leaderboard(request):
    """Show leaderboard of top contributors"""
    contributors = ContributorStats.objects.filter(
        approved_count__gt=0
    ).order_by('-approved_count', '-submissions_count')[:50]
    
    return render(request, 'normalizer/leaderboard.html', {
        'contributors': contributors,
    })


def file_detail(request, upload_id):
    """Display file details and processing logs"""
    upload = get_object_or_404(FOIAUpload, id=upload_id)
    
    # Only show approved submissions or submissions by the current user
    if upload.submission_status != 'approved' and upload.uploaded_by != request.user:
        messages.error(request, 'File not found or not yet approved.')
        return redirect('home')
    
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
    """List all approved uploaded files"""
    uploads = FOIAUpload.objects.filter(
        submission_status='approved'
    ).order_by('-uploaded_at')
    
    # Pagination
    paginator = Paginator(uploads, 20)
    page_number = request.GET.get('page')
    page_uploads = paginator.get_page(page_number)
    
    return render(request, 'normalizer/file_list.html', {
        'uploads': page_uploads,
    })


def download_file(request, upload_id):
    """Download processed file (only approved submissions)"""
    try:
        upload = get_object_or_404(
            FOIAUpload, 
            id=upload_id, 
            submission_status='approved'
        )
        
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
    """Process an upload using AI-assisted mappings"""
    from .models import ProcessingLog
    
    try:
        ProcessingLog.objects.create(
            upload=upload,
            log_type='info',
            message='Starting AI-assisted processing'
        )
        
        normalizer = FOIANormalizer(upload)
        
        # Load the file
        df = normalizer.load_file()
        
        # If no mappings exist yet, generate them
        if not upload.column_mappings.exists():
            ProcessingLog.objects.create(
                upload=upload,
                log_type='info',
                message='Generating AI-assisted column mappings...'
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
            message=f'Processing failed: {str(e)}'
        )
        raise