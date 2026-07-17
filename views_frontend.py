# Controladores de vistas web: autenticación, dashboard y gestión de usuarios
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from hotel.models import Habitacion, Hotel, TipoHabitacion
from huespedes.models import Huesped
from reservas.models import Reserva
from estancias.models import Estancia, CargoEstancia, Folio, Pago
from utils.auditoria import log_action
from reportes.models import registrar_auditoria
from config import roles
from config.views_shared import _es_admin, _es_recepcionista, _es_housekeeping, _solo_housekeeping, _acceso_denegado


def login_view(request):
    if request.user.is_authenticated:
        if _solo_housekeeping(request.user):
            return redirect('housekeeping')
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '')
        ip = request.META.get('REMOTE_ADDR', 'unknown')
        user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')[:200]
        
        from django.contrib.auth.models import User
        from reportes.models import LoginIntento
        
        user = authenticate(request, username=username, password=request.POST['password'])
        
        if user:
            intentos_fallidos = LoginIntento.contar_fallidos_recientes(user, minutos=15)
            if intentos_fallidos >= 5:
                if user.is_active:
                    user.is_active = False
                    user.save(update_fields=['is_active'])
                    log_action(
                        user=None,
                        accion="Bloqueo Automático",
                        registro_id=user.id,
                        tabla_afectada="auth_user",
                        estado_anterior="Activo",
                        estado_nuevo="Bloqueado",
                        observacion=f"Usuario '{username}' bloqueado tras 5 intentos fallidos. IP: {ip}"
                    )
                messages.error(request, 'Tu cuenta está bloqueada por múltiples intentos fallidos. Contacta al administrador.')
                return redirect('login')
            
            LoginIntento.registrar(usuario=user, ip=ip, user_agent=user_agent, exitoso=True)
            
            login(request, user)
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            log_action(
                user=user,
                accion="Login Exitoso",
                registro_id=user.id,
                tabla_afectada="auth_user",
                estado_nuevo=f"Sesión iniciada desde IP: {ip}",
                observacion=f"Device: {user_agent}"
            )
            
            if _solo_housekeeping(user):
                return redirect('housekeeping')
            return redirect('dashboard')
        else:
            LoginIntento.registrar(usuario=None, ip=ip, user_agent=user_agent, exitoso=False)
            log_action(
                user=None,
                accion="Intento Login Fallido",
                registro_id=None,
                tabla_afectada="auth_user",
                observacion=f"Usuario: '{username}', IP: {ip}, Device: {user_agent}"
            )
            messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'login.html')


def logout_view(request):
    if request.user.is_authenticated:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
        log_action(
            user=request.user,
            accion="Logout",
            tabla_afectada="auth_user",
            observacion=f"Sesión cerrada. IP: {ip}"
        )
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    if _solo_housekeeping(request.user):
        return redirect('housekeeping')

    habitaciones = Habitacion.objects.select_related('tipo', 'hotel').all().order_by('piso', 'numero')
    hoy = timezone.now().date()
    ahora = timezone.now()
    
    total = habitaciones.count()
    ocupadas = habitaciones.filter(estado='OCUPADA').count()
    stats = {
        'disponibles': habitaciones.filter(estado='DISPONIBLE').count(),
        'ocupadas': ocupadas,
        'reservas_hoy': 0,
        'tasa_ocupacion': round(ocupadas / total * 100) if total else 0,
    }
    
    from datetime import datetime, time
    checkin_time = timezone.make_aware(datetime.combine(hoy, time(14, 0)))
    reservas_hoy = Reserva.objects.filter(
        fecha_entrada=hoy, estado__in=['PENDIENTE', 'CONFIRMADA']
    ).select_related('habitacion')
    reservas_dict = {r.habitacion_id: r for r in reservas_hoy if r.habitacion_id}
    
    for hab in habitaciones:
        hab.estado_visual = hab.estado
        if hab.estado == 'OCUPADA':
            for e in hab.estancias.all():
                if e.estado == 'ACTIVA' and e.reserva.fecha_salida < hoy:
                    hab.estado_visual = 'VENCIDA'
                    break
        elif hab.estado == 'DISPONIBLE':
            r = reservas_dict.get(hab.id)
            if r:
                hab.reserva_hoy = r
                if ahora > checkin_time:
                    hab.estado_visual = 'RETRASO'
                else:
                    hab.estado_visual = 'RESERVADA'
    
    stats['reservas_hoy'] = sum(1 for hab in habitaciones if getattr(hab, 'estado_visual', '') in ['RESERVADA', 'RETRASO'])

    llegadas_hoy = Reserva.objects.filter(
        fecha_entrada=hoy,
        estado__in=['PENDIENTE', 'CONFIRMADA']
    ).select_related('huesped', 'habitacion')[:15]

    en_casa = Estancia.objects.filter(
        estado='ACTIVA'
    ).select_related('reserva__huesped', 'habitacion')[:15]

    salidas_hoy = Estancia.objects.filter(
        estado='ACTIVA',
        reserva__fecha_salida=hoy
    ).select_related('reserva__huesped', 'habitacion')[:15]

    from estancias.models import CargoEstancia, Folio
    from atencion.models import TicketServicio
    from decimal import Decimal

    early_checkins_hoy = CargoEstancia.objects.filter(
        concepto__icontains="Early Check-In",
        estancia__fecha_checkin__date=hoy
    ).count()

    late_checkouts_hoy = CargoEstancia.objects.filter(
        concepto__icontains="Salida Tardía",
        fecha__date=hoy
    ).count()

    reservas_vencer_hoy = Reserva.objects.filter(
        fecha_entrada=hoy,
        estado__in=['PENDIENTE', 'CONFIRMADA']
    ).count()

    tickets_pendientes = TicketServicio.objects.filter(
        estado__in=['ABIERTA', 'PROCESO', 'PENDIENTE']
    ).count()

    active_folios = Folio.objects.filter(estancia__estado='ACTIVA')
    saldos_activos = sum(f.saldo_pendiente for f in active_folios)

    mostrar_financiero = _es_admin(request.user)

    return render(request, 'dashboard.html', {
        'habitaciones': habitaciones,
        'stats': stats,
        'llegadas_hoy': llegadas_hoy,
        'en_casa': en_casa,
        'salidas_hoy': salidas_hoy,
        'early_checkins_hoy': early_checkins_hoy,
        'late_checkouts_hoy': late_checkouts_hoy,
        'reservas_vencer_hoy': reservas_vencer_hoy,
        'tickets_pendientes': tickets_pendientes,
        'saldos_activos': saldos_activos,
        'mostrar_financiero': mostrar_financiero,
    })


@login_required
def usuarios_lista(request):
    from django.contrib.auth.models import User, Group
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para acceder a la gestión de usuarios.')
        return redirect('dashboard')
    
    query = request.GET.get('q', '')
    usuarios = User.objects.prefetch_related('groups').all().order_by('-date_joined')
    if query:
        usuarios = usuarios.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )
    
    return render(request, 'usuarios/lista.html', {'usuarios': usuarios, 'query': query})


def error_403(request, exception=None):
    return render(request, '403.html', {'mensaje_error': 'La página denegó el acceso por falta de permisos.'}, status=403)

def error_404(request, exception=None):
    return render(request, '404.html', status=404)


@login_required
def usuario_editar(request, user_id):
    from django.contrib.auth.models import User, Group
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para editar usuarios.')
        return redirect('dashboard')
        
    usuario_edit = get_object_or_404(User, id=user_id)
    grupos_disponibles = Group.objects.all()
    
    if request.method == 'POST':
        try:
            cambios = []
            if usuario_edit.first_name != request.POST.get('nombres', usuario_edit.first_name):
                cambios.append(f"Nombre: {usuario_edit.first_name} → {request.POST.get('nombres')}")
            if usuario_edit.last_name != request.POST.get('apellidos', usuario_edit.last_name):
                cambios.append(f"Apellido: {usuario_edit.last_name} → {request.POST.get('apellidos')}")
            if usuario_edit.email != request.POST.get('email', usuario_edit.email):
                cambios.append(f"Email: {usuario_edit.email} → {request.POST.get('email')}")
            
            usuario_edit.first_name = request.POST.get('nombres', usuario_edit.first_name)
            usuario_edit.last_name = request.POST.get('apellidos', usuario_edit.last_name)
            usuario_edit.email = request.POST.get('email', usuario_edit.email)
            usuario_edit.is_active = request.POST.get('is_active') == 'on'
            
            rol_id = request.POST.get('rol')
            usuario_edit.groups.clear()
            if rol_id:
                grupo = Group.objects.get(id=rol_id)
                usuario_edit.groups.add(grupo)
                cambios.append(f"Rol asignado: {grupo.name}")
                
            usuario_edit.save()
            
            registrar_auditoria(
                usuario=request.user,
                accion="Usuario Editado",
                registro_id=usuario_edit.id,
                tabla_afectada="auth_user",
                estado_nuevo=f"Usuario '{usuario_edit.username}' actualizado",
                observacion=f"Campos modificados: {', '.join(cambios)}" if cambios else "Sin cambios significativos"
            )
            
            messages.success(request, f'Usuario {usuario_edit.username} actualizado correctamente.')
            return redirect('usuarios_lista')
        except Exception as e:
            messages.error(request, f'Error al actualizar: {str(e)}')
            
    rol_actual = usuario_edit.groups.first()
    
    return render(request, 'usuarios/form.html', {
        'usuario_edit': usuario_edit,
        'grupos_disponibles': grupos_disponibles,
        'rol_actual': rol_actual,
    })


@login_required
def usuario_nuevo(request):
    from django.contrib.auth.models import User, Group
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para crear usuarios.')
        return redirect('dashboard')
        
    grupos_disponibles = Group.objects.all()
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            password = request.POST.get('password')
            
            if User.objects.filter(username=username).exists():
                raise Exception('Ese nombre de usuario ya está en uso.')
                
            nuevo_user = User.objects.create_user(
                username=username,
                password=password,
                first_name=request.POST.get('nombres', ''),
                last_name=request.POST.get('apellidos', ''),
                email=request.POST.get('email', ''),
            )
            nuevo_user.is_active = request.POST.get('is_active') == 'on'
            
            rol_id = request.POST.get('rol')
            if rol_id:
                grupo = Group.objects.get(id=rol_id)
                nuevo_user.groups.add(grupo)
                
            nuevo_user.save()
            
            registrar_auditoria(
                usuario=request.user,
                accion="Usuario Creado",
                registro_id=nuevo_user.id,
                tabla_afectada="auth_user",
                estado_nuevo=f"Usuario '{username}' creado. Rol: {rol_id}",
                observacion=f"Email: {nuevo_user.email}, Activo: {nuevo_user.is_active}"
            )
            
            messages.success(request, f'Usuario {nuevo_user.username} creado correctamente.')
            return redirect('usuarios_lista')
        except Exception as e:
            messages.error(request, f'Error al crear: {str(e)}')
            
    return render(request, 'usuarios/nuevo.html', {
        'grupos_disponibles': grupos_disponibles,
    })


@login_required
def usuario_eliminar(request, user_id):
    from django.contrib.auth.models import User
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos para eliminar usuarios.')
        return redirect('dashboard')
        
    usuario = get_object_or_404(User, id=user_id)
    if usuario == request.user:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('usuarios_lista')
        
    if request.method == 'POST':
        try:
            username = usuario.username
            usuario.is_active = False
            usuario.save()
            
            registrar_auditoria(
                usuario=request.user,
                accion="Usuario Desactivado",
                registro_id=usuario.id,
                tabla_afectada="auth_user",
                estado_anterior="Activo",
                estado_nuevo="Inactivo",
                observacion=f"Usuario '{username}' desactivado (soft delete)"
            )
            messages.success(request, f'Usuario {username} desactivado correctamente.')
        except Exception as e:
            messages.error(request, f'Error al desactivar: {str(e)}')
            
    return redirect('usuarios_lista')


@login_required
def mi_perfil(request):
    from django.contrib.auth.models import Group
    
    if request.method == 'POST':
        try:
            request.user.first_name = request.POST.get('nombres', request.user.first_name)
            request.user.last_name = request.POST.get('apellidos', request.user.last_name)
            request.user.email = request.POST.get('email', request.user.email)
            request.user.save()
            
            log_action(
                user=request.user,
                accion="Perfil Actualizado",
                registro_id=request.user.id,
                tabla_afectada="auth_user",
                estado_nuevo="Datos de perfil actualizados"
            )
            
            messages.success(request, 'Perfil actualizado correctamente.')
            return redirect('mi_perfil')
        except Exception as e:
            messages.error(request, f'Error al actualizar: {str(e)}')
    
    roles = list(request.user.groups.values_list('name', flat=True))
    
    return render(request, 'mi_perfil.html', {
        'user': request.user,
        'roles': roles,
    })


@login_required
def cambiar_password(request):
    if request.method == 'POST':
        password_actual = request.POST.get('password_actual')
        nueva_password = request.POST.get('nueva_password')
        confirmar_password = request.POST.get('confirmar_password')
        
        if not request.user.check_password(password_actual):
            messages.error(request, 'La contraseña actual es incorrecta.')
            return redirect('cambiar_password')
        
        if nueva_password != confirmar_password:
            messages.error(request, 'Las contraseñas nuevas no coinciden.')
            return redirect('cambiar_password')
        
        if len(nueva_password) < 8:
            messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')
            return redirect('cambiar_password')
        
        if not any(c.isupper() for c in nueva_password):
            messages.error(request, 'La contraseña debe contener al menos una letra mayúscula.')
            return redirect('cambiar_password')
        
        if not any(c.isdigit() for c in nueva_password):
            messages.error(request, 'La contraseña debe contener al menos un número.')
            return redirect('cambiar_password')
        
        request.user.set_password(nueva_password)
        request.user.save()
        
        registrar_auditoria(
            usuario=request.user,
            accion="Contraseña Cambiada",
            registro_id=request.user.id,
            tabla_afectada="auth_user",
            estado_nuevo="Contraseña actualizada exitosamente"
        )
        
        messages.success(request, 'Contraseña cambiada correctamente. Inicia sesión nuevamente.')
        return redirect('login')
    
    return render(request, 'cambiar_password.html')


@login_required
def recuperar_contrasena(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if not email:
            messages.error(request, 'Debes ingresar un correo electrónico.')
            return redirect('recuperar_contrasena')
        
        from django.contrib.auth.models import User
        from reportes.models import PasswordResetToken
        from django.core.mail import send_mail
        from django.conf import settings
        
        usuarios = User.objects.filter(email=email, is_active=True)
        if usuarios.exists():
            usuario = usuarios.first()
            token = PasswordResetToken.objects.create(usuario=usuario)
            
            reset_url = request.build_absolute_uri(f'/reset/{token.token}/')
            
            try:
                send_mail(
                    subject='Recuperar Contraseña - HotelSystem',
                    message=f'Hola {usuario.username},\n\nHaz clic en el siguiente enlace para restablecer tu contraseña:\n\n{reset_url}\n\nEste enlace expira en 1 hora.\n\nSi no solicitaste este cambio, ignora este mensaje.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                messages.success(request, f'Se envió un enlace de recuperación a {email}')
            except Exception as e:
                messages.error(request, f'Error al enviar el email: {str(e)}')
        else:
            messages.info(request, 'Si el correo existe en nuestro sistema, recibirás un enlace de recuperación.')
        
        registrar_auditoria(
            usuario=None,
            accion="Solicitud Recuperación Contraseña",
            registro_id=None,
            tabla_afectada="auth_user",
            observacion=f"Email: {email}"
        )
        
        return redirect('login')
    
    return render(request, 'recuperar_contrasena.html')


@login_required
def reset_confirmar(request, token):
    from reportes.models import PasswordResetToken
    from django.contrib.auth.models import User
    
    try:
        token_obj = PasswordResetToken.objects.get(token=token)
    except PasswordResetToken.DoesNotExist:
        messages.error(request, 'Token de recuperación inválido.')
        return redirect('login')
    
    if not token_obj.esta_valido():
        messages.error(request, 'El enlace de recuperación ha expirado o ya fue usado.')
        return redirect('login')
    
    if request.method == 'POST':
        nueva_password = request.POST.get('nueva_password')
        confirmar_password = request.POST.get('confirmar_password')
        
        if nueva_password != confirmar_password:
            messages.error(request, 'Las contraseñas no coinciden.')
            return redirect('reset_confirmar', token=token)
        
        if len(nueva_password) < 8:
            messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')
            return redirect('reset_confirmar', token=token)
        
        if not any(c.isupper() for c in nueva_password):
            messages.error(request, 'La contraseña debe contener al menos una letra mayúscula.')
            return redirect('reset_confirmar', token=token)
        
        if not any(c.isdigit() for c in nueva_password):
            messages.error(request, 'La contraseña debe contener al menos un número.')
            return redirect('reset_confirmar', token=token)
        
        usuario = token_obj.usuario
        usuario.set_password(nueva_password)
        usuario.save()
        
        token_obj.usado = True
        token_obj.save()
        
        registrar_auditoria(
            usuario=usuario,
            accion="Contraseña Restablecida",
            registro_id=usuario.id,
            tabla_afectada="auth_user",
            estado_nuevo="Contraseña restablecida mediante token"
        )
        
        messages.success(request, 'Contraseña restablecida correctamente. Inicia sesión.')
        return redirect('login')
    
    return render(request, 'reset_confirmar.html', {'token': token})


@login_required
def desbloquear_usuario(request, user_id):
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos.')
        return redirect('dashboard')
    
    from django.contrib.auth.models import User
    usuario = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        usuario.is_active = True
        usuario.save()
        
        registrar_auditoria(
            usuario=request.user,
            accion="Usuario Desbloqueado",
            registro_id=usuario.id,
            tabla_afectada="auth_user",
            estado_anterior="Bloqueado",
            estado_nuevo="Activo",
            observacion=f"Usuario '{usuario.username}' desbloqueado por {request.user.username}"
        )
        
        messages.success(request, f'Usuario {usuario.username} desbloqueado correctamente.')
    
    return redirect('usuarios_lista')


@login_required
def sesiones_activas(request):
    from django.contrib.sessions.models import Session
    from django.contrib.auth.models import User
    
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos.')
        return redirect('dashboard')
    
    sesiones = []
    for s in Session.objects.all():
        datos = s.get_decoded()
        user_id = datos.get('_auth_user_id')
        if user_id:
            try:
                usuario = User.objects.get(id=user_id)
                sesiones.append({
                    'session_key': s.session_key,
                    'usuario': usuario,
                    'ultima_actividad': s.expire_date,
                    'ip': datos.get('ip', 'unknown'),
                })
            except User.DoesNotExist:
                pass
    
    return render(request, 'sesiones/lista.html', {'sesiones': sesiones})


@login_required
def cerrar_sesion(request, session_key):
    from django.contrib.sessions.models import Session
    
    if not request.user.is_superuser and not request.user.groups.filter(name='admin').exists():
        messages.error(request, 'No tienes permisos.')
        return redirect('dashboard')
    
    try:
        sesion = Session.objects.get(session_key=session_key)
        datos = sesion.get_decoded()
        user_id = datos.get('_auth_user_id')
        
        if user_id:
            from django.contrib.auth.models import User
            usuario = User.objects.get(id=user_id)
            
            sesion.delete()
            
            registrar_auditoria(
                usuario=request.user,
                accion="Sesión Cerrada Remotamente",
                registro_id=usuario.id,
                tabla_afectada="auth_user",
                observacion=f"Sesión de '{usuario.username}' cerrada por {request.user.username}"
            )
            
            messages.success(request, f'Sesión de {usuario.username} cerrada correctamente.')
    except Exception as e:
        messages.error(request, f'Error al cerrar sesión: {str(e)}')
    
    return redirect('sesiones_activas')
