from django.urls import path
from . import views

urlpatterns = [
    path('inventario/', views.inventario_dashboard, name='inventario_dashboard'),
    path('inventario/producto/nuevo/', views.producto_crear, name='producto_crear'),
    path('inventario/producto/<int:pk>/editar/', views.producto_editar, name='producto_editar'),
    path('inventario/movimiento/registrar/', views.registrar_movimiento, name='registrar_movimiento'),
    path('inventario/movimiento/historial/', views.historial_movimientos, name='historial_movimientos'),
    path('inventario/categorias/', views.categorias_lista, name='categorias_lista'),
    path('inventario/proveedores/', views.proveedores_lista, name='proveedores_lista'),
    path('inventario/conteo/', views.conteo_fisico_lista, name='conteo_fisico_lista'),
    path('inventario/conteo/nuevo/', views.conteo_fisico_crear, name='conteo_fisico_crear'),
    path('inventario/conteo/<int:pk>/', views.conteo_fisico_detalle, name='conteo_fisico_detalle'),
    path('inventario/conteo/<int:pk>/aprobar/', views.conteo_fisico_aprobar, name='conteo_fisico_aprobar'),
]
