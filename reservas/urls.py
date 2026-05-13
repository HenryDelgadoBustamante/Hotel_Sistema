from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReservaViewSet, TarifaViewSet

router = DefaultRouter()
router.register(r'reservas', ReservaViewSet)
router.register(r'tarifas', TarifaViewSet)

urlpatterns = [path('', include(router.urls))]
