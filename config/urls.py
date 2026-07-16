# Enrutador principal de URLs del sistema (APIs y Web)
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from views_frontend import (
    login_view, logout_view, dashboard, reservas_lista, reserva_nueva,
    reserva_detalle, checkin_directo, reserva_checkin, folio_view, agregar_cargo, registrar_pago, checkout_view,
    housekeeping_view, housekeeping_estado, reportes_view,
    huespedes_lista, huesped_nuevo, huesped_editar, exportar_huespedes_excel,
    habitaciones_lista, habitacion_nueva, habitacion_editar,
    estancias_lista, reservas_calendario, consultar_disponibilidad,
    reserva_imprimir_ficha, folio_imprimir,
    usuarios_lista, usuario_editar, usuario_nuevo, usuario_eliminar,
    api_habitaciones_disponibles, api_consulta_dni, api_buscar_huesped,
    reserva_editar, reserva_cancelar, registrar_pago_anticipo,
    solicitar_reembolso, aprobar_reembolso, cambiar_habitacion,
    cancelar_estancia_sin_pago,
    tickets_lista, ticket_nuevo, ticket_detalle, ticket_iniciar,
    ticket_resolver, ticket_cerrar, ticket_reabrir, ticket_seguimiento,
    ticket_agregar_cargo, reembolsos_lista_admin,
    api_ocupacion_habitaciones, api_habitaciones_housekeeping_recientes,
    mi_perfil, cambiar_password,
    recuperar_contrasena, reset_confirmar, desbloquear_usuario,
    sesiones_activas, cerrar_sesion, actualizar_estado_habitacion, hotel_configuracion
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
    path('', include('inventario.urls')),
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
    path('reservas/<int:reserva_id>/editar/', reserva_editar, name='reserva_editar'),
    path('reservas/<int:reserva_id>/cancelar/', reserva_cancelar, name='reserva_cancelar'),
    path('reservas/<int:reserva_id>/pago-anticipo/', registrar_pago_anticipo, name='registrar_pago_anticipo'),
    path('pagos/<int:pago_id>/reembolso/', solicitar_reembolso, name='solicitar_reembolso'),
    path('reembolsos/<int:reembolso_id>/resolver/', aprobar_reembolso, name='aprobar_reembolso'),
    path('reservas/calendario/', reservas_calendario, name='reservas_calendario'),
    path('reservas/disponibilidad/', consultar_disponibilidad, name='consultar_disponibilidad'),
    path('reservas/nueva/', reserva_nueva, name='reserva_nueva'),
    path('reservas/<int:reserva_id>/checkin/', reserva_checkin, name='reserva_checkin'),
    path('checkin-directo/', checkin_directo, name='checkin_directo'),
    path('checkin-directo/<int:huesped_id>/', checkin_directo, name='checkin_directo_huesped'),
    path('api/habitaciones-disponibles/', api_habitaciones_disponibles, name='api_habitaciones_disponibles'),
    path('api/dni/', api_consulta_dni, name='api_consulta_dni'),
    path('api/buscar-huesped/', api_buscar_huesped, name='api_buscar_huesped'),
    path('estancias/<int:estancia_id>/folio/', folio_view, name='folio'),
    path('estancias/<int:estancia_id>/imprimir-folio/', folio_imprimir, name='folio_imprimir'),
    path('estancias/<int:estancia_id>/cargo/', agregar_cargo, name='agregar_cargo'),
    path('reservas/<int:reserva_id>/imprimir-ficha/', reserva_imprimir_ficha, name='reserva_imprimir_ficha'),
    path('estancias/<int:estancia_id>/pago/', registrar_pago, name='registrar_pago'),
    path('estancias/<int:estancia_id>/checkout/', checkout_view, name='checkout'),
    path('estancias/<int:estancia_id>/cambiar-habitacion/', cambiar_habitacion, name='cambiar_habitacion'),
    path('estancias/<int:estancia_id>/cancelar-sin-pago/', cancelar_estancia_sin_pago, name='cancelar_estancia_sin_pago'),
    path('api/ocupacion/', api_ocupacion_habitaciones, name='api_ocupacion'),
    path('api/housekeeping-recientes/', api_habitaciones_housekeeping_recientes, name='api_housekeeping_recientes'),
    path('housekeeping/', housekeeping_view, name='housekeeping'),
    path('tickets/', tickets_lista, name='tickets_lista'),
    path('tickets/nuevo/', ticket_nuevo, name='ticket_nuevo'),
    path('tickets/<int:ticket_id>/', ticket_detalle, name='ticket_detalle'),
    path('tickets/<int:ticket_id>/iniciar/', ticket_iniciar, name='ticket_iniciar'),
    path('tickets/<int:ticket_id>/resolver/', ticket_resolver, name='ticket_resolver'),
    path('tickets/<int:ticket_id>/cerrar/', ticket_cerrar, name='ticket_cerrar'),
    path('tickets/<int:ticket_id>/reabrir/', ticket_reabrir, name='ticket_reabrir'),
    path('tickets/<int:ticket_id>/seguimiento/', ticket_seguimiento, name='ticket_seguimiento'),
    path('tickets/<int:ticket_id>/cargo/', ticket_agregar_cargo, name='ticket_agregar_cargo'),
    path('reembolsos/', reembolsos_lista_admin, name='reembolsos_lista_admin'),
    path('housekeeping/<int:hab_id>/estado/', housekeeping_estado, name='housekeeping_estado'),
    path('habitaciones/<int:hab_id>/estado/', actualizar_estado_habitacion, name='actualizar_estado_habitacion'),
    path('reportes/', reportes_view, name='reportes'),
    path('usuarios/', usuarios_lista, name='usuarios_lista'),
    path('usuarios/nuevo/', usuario_nuevo, name='usuario_nuevo'),
    path('usuarios/<int:user_id>/editar/', usuario_editar, name='usuario_editar'),
    path('usuarios/<int:user_id>/eliminar/', usuario_eliminar, name='usuario_eliminar'),
    path('mi-perfil/', mi_perfil, name='mi_perfil'),
    path('mi-contrasena/', cambiar_password, name='cambiar_password'),
    path('recuperar-contrasena/', recuperar_contrasena, name='recuperar_contrasena'),
    path('reset/<uuid:token>/', reset_confirmar, name='reset_confirmar'),
    path('usuarios/<int:user_id>/desbloquear/', desbloquear_usuario, name='desbloquear_usuario'),
    path('sesiones/', sesiones_activas, name='sesiones_activas'),
    path('sesiones/<session_key>/cerrar/', cerrar_sesion, name='cerrar_sesion'),
    path('configuracion/', hotel_configuracion, name='configuracion_hotel'),
    path('', lambda request: redirect('dashboard'), name='home'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = 'views_frontend.error_403'
handler404 = 'views_frontend.error_404'
