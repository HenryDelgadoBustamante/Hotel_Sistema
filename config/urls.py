from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from views_frontend import (
    login_view, logout_view, dashboard, reservas_lista, reserva_nueva,
    reserva_detalle, reserva_checkin, folio_view, agregar_cargo, registrar_pago, checkout_view,
    housekeeping_view, housekeeping_estado, reportes_view,
    huespedes_lista, huesped_nuevo, huesped_editar, exportar_huespedes_excel,
    habitaciones_lista, habitacion_nueva, habitacion_editar,
    estancias_lista, reservas_calendario
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def perfil_usuario(request):
    user = request.user
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'es_admin': user.is_superuser,
        'roles': list(user.groups.values_list('name', flat=True)),
    })

schema_view = get_schema_view(
    openapi.Info(
        title="Hotel System API",
        default_version='v1',
        description="API para Sistema de Gestión Hotelera",
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/perfil/', perfil_usuario, name='perfil-usuario'),
    path('api/', include('hotel.urls')),
    path('api/', include('huespedes.urls')),
    path('api/', include('reservas.urls')),
    path('api/', include('estancias.urls')),
    path('api/', include('reportes.urls')),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    path('huespedes/', huespedes_lista, name='huespedes_lista'),
    path('huespedes/nuevo/', huesped_nuevo, name='huesped_nuevo'),
    path('huespedes/<int:huesped_id>/editar/', huesped_editar, name='huesped_editar'),
    path('huespedes/exportar-excel/', exportar_huespedes_excel, name='exportar_huespedes_excel'),
    path('habitaciones/', habitaciones_lista, name='habitaciones_lista'),
    path('habitaciones/nueva/', habitacion_nueva, name='habitacion_nueva'),
    path('habitaciones/<int:hab_id>/editar/', habitacion_editar, name='habitacion_editar'),
    path('estancias/', estancias_lista, name='estancias_lista'),
    path('reservas/', reservas_lista, name='reservas_lista'),
    path('reservas/<int:reserva_id>/', reserva_detalle, name='reserva_detalle'),
    path('reservas/calendario/', reservas_calendario, name='reservas_calendario'),
    path('reservas/nueva/', reserva_nueva, name='reserva_nueva'),
    path('reservas/<int:reserva_id>/checkin/', reserva_checkin, name='reserva_checkin'),
    path('estancias/<int:estancia_id>/folio/', folio_view, name='folio'),
    path('estancias/<int:estancia_id>/cargo/', agregar_cargo, name='agregar_cargo'),
    path('estancias/<int:estancia_id>/pago/', registrar_pago, name='registrar_pago'),
    path('estancias/<int:estancia_id>/checkout/', checkout_view, name='checkout'),
    path('housekeeping/', housekeeping_view, name='housekeeping'),
    path('housekeeping/<int:hab_id>/estado/', housekeeping_estado, name='housekeeping_estado'),
    path('reportes/', reportes_view, name='reportes'),
    path('', lambda request: redirect('dashboard'), name='home'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
