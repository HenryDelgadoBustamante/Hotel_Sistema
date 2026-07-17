# Helpers compartidos para vistas frontend del sistema hotelero
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from config import roles


def _es_admin(user):
    return roles.es_admin(user)

def _es_recepcionista(user):
    return roles.es_recepcionista(user)

def _es_housekeeping(user):
    return roles.es_housekeeping(user)

def _solo_housekeeping(user):
    """True si el usuario es SOLO housekeeping (sin admin ni recepcionista)."""
    return roles.solo_housekeeping(user)

def _acceso_denegado(request, msg='No tienes permisos para acceder a esta sección.'):
    return render(request, '403.html', {'mensaje_error': msg}, status=403)


def parse_room_gallery(raw_urls, main_url=''):
    urls = []
    for raw_url in (main_url, *raw_urls.splitlines()):
        url = raw_url.strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def parse_datetime_local(value):
    if not value:
        return None
    parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M')
    return timezone.make_aware(parsed)


def parse_date_local(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f'Fecha inválida: {value}')


def calcular_cargo_salida_tardia(estancia):
    from estancias.services import detectar_late_checkout
    hotel = estancia.habitacion.hotel
    now_local = timezone.localtime(timezone.now())
    es_late, late_monto, minutos_tarde = detectar_late_checkout(estancia, hotel, now_local)
    return late_monto, minutos_tarde
