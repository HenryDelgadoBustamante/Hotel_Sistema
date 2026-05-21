from django.urls import path
from .views import OcupacionView, exportar_excel

urlpatterns = [
    path('reportes/ocupacion/', OcupacionView.as_view(), name='reporte-ocupacion'),
    path('reportes/exportar-excel/', exportar_excel, name='exportar_excel'),
]

