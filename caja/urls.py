from django.urls import path
from . import views

urlpatterns = [
    path('caja/', views.caja_dashboard, name='caja_dashboard'),
    path('caja/aperturar/', views.caja_aperturar, name='caja_aperturar'),
    path('caja/arqueo/', views.caja_arqueo, name='caja_arqueo'),
    path('caja/cerrar/', views.caja_cerrar, name='caja_cerrar'),
    path('caja/movimiento/nuevo/', views.caja_movimiento_registrar, name='caja_movimiento_registrar'),
    path('caja/historial/', views.caja_historial, name='caja_historial'),
    path('caja/movimientos/', views.caja_movimientos_lista, name='caja_movimientos_lista'),
    path('caja/anomalias/', views.caja_anomalias_lista, name='caja_anomalias'),
    path('caja/anomalia/<int:pk>/resolver/', views.caja_anomalia_resolver, name='caja_anomalia_resolver'),
    path('caja/<int:pk>/imprimir/', views.caja_imprimir_acta, name='caja_imprimir_acta'),
]
