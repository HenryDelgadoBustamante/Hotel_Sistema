# Rutas para el registro de clientes
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HuespedViewSet

router = DefaultRouter()
router.register(r'huespedes', HuespedViewSet)

urlpatterns = [path('', include(router.urls))]
