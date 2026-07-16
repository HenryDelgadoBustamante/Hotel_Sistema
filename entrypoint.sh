#!/bin/sh
# Script de arranque del contenedor web

set -e

echo "==> Aplicando migraciones..."
python manage.py migrate --noinput

echo "==> Recopilando archivos estáticos..."
python manage.py collectstatic --noinput

# Cargar datos iniciales solo si la BD está vacía (primera vez)
HOTEL_COUNT=$(python manage.py shell -c "from hotel.models import Hotel; print(Hotel.objects.count())" 2>/dev/null | tail -1 || echo "0")

if [ "$HOTEL_COUNT" = "0" ]; then
    echo "==> BD vacía detectada. Cargando datos iniciales..."
    python manage.py loaddata fixtures/initial_data.json
    echo "==> Datos cargados correctamente."
else
    echo "==> BD ya tiene datos ($HOTEL_COUNT hotel/es). Saltando carga de fixture."
fi

echo "==> Iniciando servidor Django en 0.0.0.0:8000..."
exec python manage.py runserver 0.0.0.0:8000
