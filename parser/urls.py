from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("run/", views.run, name="run"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/partial/", views.dashboard_partial, name="dashboard_partial"),
]
