from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EstanciaViewSet

router = DefaultRouter()
router.register(r'estancias', EstanciaViewSet)

urlpatterns = [path('', include(router.urls))]
