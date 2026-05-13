from django.urls import path
from .views import OcupacionView

urlpatterns = [
    path('reportes/ocupacion/', OcupacionView.as_view(), name='reporte-ocupacion'),
]
