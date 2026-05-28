from django.urls import path
from . import views

app_name = 'monsters'

urlpatterns = [
    path('',            views.home,     name='home'),
    path('load/',       views.load,     name='load'),
    path('catalogue/',  views.catalogue, name='catalogue'),
    path('search/',     views.search,   name='search'),
    path('suggest/',    views.suggest,  name='suggest'),
    path('monster/<int:pk>/', views.detail,  name='detail'),
    path('build-index/', views.build_index_view, name='build_index'),
]
