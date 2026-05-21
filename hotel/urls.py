# Mapeo de rutas REST de habitaciones
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HotelViewSet, TipoHabitacionViewSet, HabitacionViewSet

router = DefaultRouter()
router.register(r'hoteles', HotelViewSet)
router.register(r'tipos-habitacion', TipoHabitacionViewSet)
router.register(r'habitaciones', HabitacionViewSet)

urlpatterns = [path('', include(router.urls))]
