# Manual básico de puesta en marcha del proyecto;
<div align="center">

<img src="https://img.shields.io/badge/-%F0%9F%8F%A8%20HotelSystem-0f172a?style=for-the-badge&labelColor=0f172a" alt="HotelSystem" height="42"/>

### Sistema de Gestión Hotelera — Full Stack con Django

[![Django](https://img.shields.io/badge/Django-6.0-092E20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/REST_Framework-3.17-red?style=flat-square&logo=django&logoColor=white)](https://www.django-rest-framework.org/)
[![JWT](https://img.shields.io/badge/Auth-JWT-black?style=flat-square&logo=jsonwebtokens)](https://django-rest-framework-simplejwt.readthedocs.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Pytest](https://img.shields.io/badge/Tests-pytest-0a9edc?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

<br/>

> *Plataforma web para administrar habitaciones, reservas, huéspedes, estancias y reportes de ocupación en tiempo real.*

</div>

---

## Características principales

| Módulo | Funcionalidades |
|--------|-----------------|
|  **Habitaciones** | Plano visual interactivo, estados en tiempo real, galería de imágenes por habitación. |
|  **Reservas** | Calendario de ocupación mensual (Gantt), reservas por día/hora, check-in express. |
| **Huéspedes** | Registro por documento, búsqueda rápida, historial de estancias. |
| **Estancias** | Folio de cargos, cargos por servicio (restaurante, lavandería, etc.), check-out con IGV. |
|  **Housekeeping** | Panel de estado de limpieza por habitación con actualización en un clic. |
|  **Reportes** | KPIs de ocupación, revenue por tipo, estancias activas, gráficos interactivos. |
|  **API REST** | Endpoints JWT para integración con apps externas (documentado con Swagger/ReDoc). |

---

##  Capturas de pantalla

<details>
<summary>Ver detalles de la interfaz</summary>

> **Dashboard** — Plano de habitaciones con estados en tiempo real  
> **Reportes** — KPI strip con 8 métricas y gráfico de ocupación  
> **Folio** — Detalle de cargos con subtotal, IGV y total  
> **Formularios** — Layout de 2 columnas con vista previa de galería en vivo

</details>

---

##  Stack tecnológico

<table>
<tr>
<td><b>Backend</b></td>
<td>Django 6.0 · Django REST Framework 3.17 · SimpleJWT (JWT)</td>
</tr>
<tr>
<td><b>Frontend</b></td>
<td>Bootstrap 5.3 · Bootstrap Icons · Chart.js · Google Fonts (Inter)</td>
</tr>
<tr>
<td><b>API Docs</b></td>
<td>drf-yasg → Swagger UI + ReDoc</td>
</tr>
<tr>
<td><b>Base de datos</b></td>
<td>SQLite (Desarrollo) · PostgreSQL (Producción en Docker)</td>
</tr>
<tr>
<td><b>Infraestructura</b></td>
<td>Docker · docker-compose</td>
</tr>
<tr>
<td><b>Testing</b></td>
<td>pytest · pytest-django · coverage</td>
</tr>
</table>

---

##  Estructura del proyecto

```
hotel_system/
├── config/                  # Configuración principal de Django (settings, urls)
├── hotel/                   # App: Hoteles y Habitaciones
├── huespedes/               # App: Registro de clientes
├── reservas/                # App: Gestión de reservas y calendario Gantt
├── estancias/               # App: Check-in, check-out y folios de consumo
├── reportes/                # App: Estadísticas y dashboard analítico
├── finanzas/                # App: Control financiero (en desarrollo)
├── templates/               # Estructura de vistas HTML por módulo
│   ├── base.html            # Layout global principal
│   ├── dashboard.html       # Plano de habitaciones en tiempo real
│   ├── login.html           # Login con diseño Glassmorphism
│   ├── habitaciones/
│   ├── huespedes/
│   ├── reservas/
│   ├── estancias/
│   └── reportes/
├── static/                  # Archivos CSS y JavaScript estáticos
└── views_frontend.py        # Controlador unificado para renderizado frontend
```

---

##  Flujo principal del sistema

```
[Huésped] ──→ [Reserva] ──→ [Check-in] ──→ [Folio] ──→ [Check-out]
    │               │              │             │              │
Buscar por      Por día o      Asignar       Cargos         Cierre
documento       por hora      habitación     extra          + IGV
```

---

##  Inicio rápido

### Con Docker (Recomendado)

```bash
# 1. Clonar el repositorio
git clone https://github.com/HenryDelgadoBustamante/Hotel_Sistema.git
cd Hotel_Sistema

# 2. Configurar variables de entorno
cp .env.example .env

# 3. Levantar los contenedores (App + PostgreSQL)
docker compose up -d

# 4. Correr migraciones y crear superusuario
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```
El sistema estará disponible en **http://localhost:8000** 🚀

---

###  Sin Docker (Entorno local)

```bash
# 1. Crear y activar entorno virtual
python -m venv venv
# En Windows:
.\activate_env.ps1
# En Linux/macOS:
source venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar entorno
cp .env.example .env

# 4. Ejecutar migraciones e inicializar base de datos
python manage.py migrate
python manage.py createsuperuser

# 5. Iniciar servidor de desarrollo
python manage.py runserver
```
El sistema estará disponible en **http://localhost:8000** 🚀

---

##  API REST

La API está disponible bajo el prefijo `/api/` y cuenta con especificación interactiva:

*   **Swagger UI:** `http://localhost:8000/api/swagger/`
*   **ReDoc:** `http://localhost:8000/api/redoc/`

**Autenticación:** Bearer Token (JWT)

```bash
# 1. Obtener token
curl -X POST http://localhost:8000/api/token/ \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "tu_password"}'

# 2. Consumir endpoints protegidos
curl http://localhost:8000/api/habitaciones/ \
     -H "Authorization: Bearer <tu_token_aqui>"
```

---

##  Pruebas unitarias (Tests)

```bash
# Ejecutar la suite de pruebas completa
pytest

# Ejecutar con reporte de cobertura
pytest --cov=. --cov-report=html
```

---

## Variables de entorno (`.env`)

Crea un archivo `.env` en la raíz del proyecto configurando lo siguiente:

```env
SECRET_KEY=clave-secreta-larga-y-aleatoria
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

##  Contribuciones

Las contribuciones son bienvenidas. Por favor sigue este flujo:

1. Realiza un Fork del repositorio.
2. Crea tu rama de características: `git checkout -b feature/nueva-funcionalidad`.
3. Confirma tus cambios: `git commit -m "feat: descripción del cambio"`.
4. Sube la rama: `git push origin feature/nueva-funcionalidad`.
5. Abre un Pull Request.

---

## Autor

Desarrollado por **Henry Delgado Bustamante, Estela Alvarado Robert Anthony, Goicochea Flores Euler Ivan, Tantalean Inga Nilver**

<div align="center">

**HotelSystem** · Hecho con esfuerzo y Django · 2026

</div>