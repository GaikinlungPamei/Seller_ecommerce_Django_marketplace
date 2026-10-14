
from django.urls import path
from django_App.orders.views import HomeView


urlpatterns = [
    path("", HomeView.as_view(), name="home"),
]