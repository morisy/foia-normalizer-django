from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_file, name='upload_file'),
    path('files/', views.file_list, name='file_list'),
    path('files/<int:upload_id>/', views.file_detail, name='file_detail'),
    path('files/<int:upload_id>/review/', views.manual_review, name='manual_review'),
    path('files/<int:upload_id>/download/', views.download_file, name='download_file'),
    path('files/<int:upload_id>/status/', views.submission_status, name='submission_status'),
    
    # Admin/moderation URLs
    path('queue/', views.submission_queue, name='submission_queue'),
    path('queue/<int:upload_id>/approve/', views.approve_submission, name='approve_submission'),
    
    # Auth URLs
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Leaderboard
    path('leaderboard/', views.leaderboard, name='leaderboard'),
]