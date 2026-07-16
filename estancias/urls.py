# Mapeo de rutas operativas de estancias
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EstanciaViewSet, PagoViewSet, ReembolsoViewSet

router = DefaultRouter()
router.register(r'estancias', EstanciaViewSet)
router.register(r'pagos', PagoViewSet)
router.register(r'reembolsos', ReembolsoViewSet)

urlpatterns = [path('', include(router.urls))]
