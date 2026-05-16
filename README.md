<div align="center">

<img src="https://img.shields.io/badge/-%F0%9F%8F%A8%20HotelSystem-0f172a?style=for-the-badge&labelColor=0f172a" alt="HotelSystem" height="42"/>

### Sistema de Gestión Hotelera — Full Stack con Django

[![Django](https://img.shields.io/badge/Django-6.0-092E20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/REST_Framework-3.17-c00?style=flat-square&logo=django&logoColor=white)](https://www.django-rest-framework.org/)
[![JWT](https://img.shields.io/badge/Auth-JWT-black?style=flat-square&logo=jsonwebtokens)](https://django-rest-framework-simplejwt.readthedocs.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Pytest](https://img.shields.io/badge/Tests-pytest-0a9edc?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org/)

<br/>

> *Plataforma web para administrar habitaciones, reservas, huéspedes, estancias y reportes de ocupación en tiempo real.*

</div>

---

## 🗂️ Módulos del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│  🏠 Habitaciones   📅 Reservas    👤 Huéspedes   🚪 Estancias  │
│  📊 Reportes       🧹 Housekeep   🔐 API REST    📆 Calendario │
└─────────────────────────────────────────────────────────────────┘
```

| Módulo | Descripción |
|--------|-------------|
| 🏠 **Habitaciones** | Plano visual interactivo con estado en tiempo real. Galería de imágenes por habitación con vista previa en vivo. |
| 📅 **Reservas** | Creación de reservas por día o por hora. Calendario de ocupación. Check-in express desde la lista. |
| 👤 **Huéspedes** | Registro y búsqueda por documento. Formulario de dos columnas. Historial de estancias por huésped. |
| 🚪 **Estancias** | Folio de cargos con subtotal e IGV. Cargos extra por restaurante, lavandería, etc. Check-out con resumen. |
| 🧹 **Housekeeping** | Panel de control de limpieza. Cambio de estado por habitación en un solo clic. |
| 📊 **Reportes** | KPI strip con 8 métricas en tiempo real. Gráfico de barras por tipo. Revenue activo. Tabla de estancias. |
| 🔐 **API REST** | CRUD completo con autenticación JWT. Documentación automática con Swagger y ReDoc. |

---

## ⚡ Inicio rápido

### 🐳 Con Docker (recomendado)

```bash
# 1. Clonar
git clone https://github.com/HenryDelgadoBustamante/Hotel_Sistema.git
cd Hotel_Sistema

# 2. Variables de entorno
cp .env.example .env

# 3. Levantar
docker compose up

# 4. Migrations + superusuario (otra terminal)
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

> Sistema disponible en → **http://localhost:8000** 🚀

---

### 💻 Sin Docker

```bash
# Entorno virtual
python -m venv venv
.\activate_env.ps1          # Windows
source venv/bin/activate    # Linux / macOS

# Dependencias
pip install -r requirements.txt

# Base de datos
python manage.py migrate
python manage.py createsuperuser

# Servidor
python manage.py runserver
```

---

## 🛠️ Stack

<table>
<tr>
<td><b>Backend</b></td>
<td>Django 6.0 · Django REST Framework 3.17 · SimpleJWT</td>
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
<td>SQLite (dev) — conectable a PostgreSQL / MySQL</td>
</tr>
<tr>
<td><b>Infra</b></td>
<td>Docker + docker-compose</td>
</tr>
<tr>
<td><b>Testing</b></td>
<td>pytest · pytest-django · coverage</td>
</tr>
</table>

---

## 📁 Estructura

```
Hotel_Sistema/
│
├── config/               # Settings, URLs, WSGI
├── hotel/                # Modelos: Hotel, Habitación, TipoHabitación
├── huespedes/            # Modelos: Huésped
├── reservas/             # Modelos: Reserva
├── estancias/            # Modelos: Estancia, Folio, CargoEstancia
├── reportes/             # Vistas de estadísticas
│
├── templates/
│   ├── base.html         # Layout global (sidebar + topbar + design system)
│   ├── dashboard.html    # Plano de habitaciones en tiempo real
│   ├── login.html        # Auth con diseño glassmorphism
│   ├── habitaciones/     # Formulario con galería en vivo
│   ├── huespedes/        # Form de 2 columnas
│   ├── reservas/         # Lista, calendario, check-in
│   ├── estancias/        # Folio de cargos
│   └── reportes/         # Dashboard con KPI strip y gráficos
│
├── views_frontend.py     # Todas las vistas de la interfaz web
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 🔄 Flujo de trabajo

```
  [Huésped] ──→ [Reserva] ──→ [Check-in] ──→ [Folio] ──→ [Check-out]
      │               │              │             │              │
  Buscar por      Por día o      Asignar       Cargos         Cierre
  documento       por hora      habitación     extra          + IGV
```

---

## 🔌 API REST

```
GET  /api/swagger/         → Documentación Swagger
GET  /api/redoc/           → Documentación ReDoc
POST /api/token/           → Obtener token JWT
POST /api/token/refresh/   → Renovar token JWT
```

**Ejemplo de autenticación:**

```bash
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# Usar token en requests
curl http://localhost:8000/api/habitaciones/ \
  -H "Authorization: Bearer <token>"
```

---

## 🧪 Tests

```bash
pytest                              # Todos los tests
pytest --cov=. --cov-report=html    # Con reporte de cobertura
```

---

## ⚙️ Variables de entorno

```env
SECRET_KEY=clave-secreta-larga-y-aleatoria
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

<div align="center">

**HotelSystem** · Django 6.0 · 2026

</div>