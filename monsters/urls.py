from django.urls import path
from . import views

app_name = 'monsters'

urlpatterns = [
    path('',            views.home,     name='home'),
    path('load/',       views.load,     name='load'),
    path('catalogue/',  views.catalogue, name='catalogue'),
    path('search/',     views.search,   name='search'),
    path('suggest/',    views.suggest,  name='suggest'),
]
