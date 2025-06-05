from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_file, name='upload_file'),
    path('files/', views.file_list, name='file_list'),
    path('files/<int:upload_id>/', views.file_detail, name='file_detail'),
    path('files/<int:upload_id>/review/', views.manual_review, name='manual_review'),
    path('files/<int:upload_id>/download/', views.download_file, name='download_file'),
]