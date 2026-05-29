from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'monsters'

urlpatterns = [
    path('',            views.home,     name='home'),
    path('load/',       views.load,     name='load'),
    path('catalogue/',  views.catalogue, name='catalogue'),
    path('search/',           RedirectView.as_view(pattern_name='monsters:catalogue'), name='search'),
    path('suggest/',          views.suggest,            name='suggest'),
    path('suggest/autocomplete/', views.suggest_autocomplete, name='suggest_autocomplete'),
    path('monster/<int:pk>/', views.detail,  name='detail'),
    path('build-index/', views.build_index_view, name='build_index'),
]
