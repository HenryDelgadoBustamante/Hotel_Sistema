<div align="center">

<<<<<<< HEAD
# 🏨 HotelSystem

**Sistema de Gestión Hotelera desarrollado con Django**

[![Django](https://img.shields.io/badge/Django-6.0-092E20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.17-red?style=flat-square&logo=django)](https://www.django-rest-framework.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

*Gestión completa de habitaciones, reservas, huéspedes, estancias y reportes en una sola plataforma.*
=======
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
>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33

</div>

---

<<<<<<< HEAD
## ✨ Características principales

| Módulo | Funcionalidades |
|--------|-----------------|
| 🏠 **Habitaciones** | Plano visual interactivo, estados en tiempo real, galería de imágenes por habitación |
| 📅 **Reservas** | Calendario de ocupación, reservas por día/hora, check-in express |
| 👤 **Huéspedes** | Registro por documento, búsqueda rápida, historial de estancias |
| 🚪 **Estancias** | Folio de cargos, cargos por servicio (restaurante, lavandería, etc.), check-out con IGV |
| 🧹 **Housekeeping** | Panel de estado de limpieza por habitación con actualización en un clic |
| 📊 **Reportes** | KPIs de ocupación, revenue por tipo, estancias activas, gráfico de barras |
| 🔐 **API REST** | Endpoints JWT para integración con apps externas (documentado con Swagger/ReDoc) |

---

## 🖼️ Capturas de pantalla

<details>
<summary>Ver capturas del sistema</summary>

> **Dashboard** — Plano de habitaciones con estados en tiempo real  
> **Reportes** — KPI strip con 8 métricas y gráfico de ocupación  
> **Folio** — Detalle de cargos con subtotal, IGV y total  
> **Formularios** — Layout de 2 columnas con vista previa de galería en vivo

</details>

---

## 🛠️ Stack tecnológico

```
Backend       Django 6.0 + Django REST Framework 3.17
Auth          djangorestframework-simplejwt (JWT)
API Docs      drf-yasg (Swagger + ReDoc)
Frontend      Bootstrap 5.3 · Bootstrap Icons · Chart.js · Inter (Google Fonts)
Base de datos SQLite (dev) — configurable para PostgreSQL
Contenerización Docker + docker-compose
Testing       pytest + pytest-django + coverage
```

---

## 🚀 Inicio rápido

### Con Docker (recomendado)

```bash
# 1. Clonar el repositorio
git clone https://github.com/HenryDelgadoBustamante/Hotel_Sistema.git
cd Hotel_Sistema

# 2. Crear el archivo de entorno
cp .env.example .env    # editar las variables necesarias

# 3. Levantar el contenedor
docker compose up

# 4. Crear tablas y superusuario (en otra terminal)
=======
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
>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

<<<<<<< HEAD
El sistema estará disponible en **http://localhost:8000** 🎉

---

### Sin Docker (entorno local)

```bash
# 1. Crear entorno virtual
python -m venv venv
source venv/bin/activate        # Linux / macOS
.\activate_env.ps1              # Windows PowerShell

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar entorno
cp .env.example .env

# 4. Migraciones y superusuario
python manage.py migrate
python manage.py createsuperuser

# 5. Correr el servidor
=======
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
>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33
python manage.py runserver
```

---

<<<<<<< HEAD
## 📁 Estructura del proyecto

```
Hotel_Sistema/
├── config/                  # Configuración principal de Django (settings, urls)
├── hotel/                   # App: Hoteles y Habitaciones
├── huespedes/               # App: Huéspedes
├── reservas/                # App: Reservas y Check-in
├── estancias/               # App: Estancias, Folios y Cargos
├── reportes/                # App: Reportes y estadísticas
├── templates/               # Templates HTML (base, módulos, login)
│   ├── base.html            # Layout principal (sidebar + topbar)
│   ├── dashboard.html       # Plano de habitaciones
│   ├── habitaciones/        # Formularios y listas de habitaciones
│   ├── huespedes/           # Formularios y lista de huéspedes
│   ├── reservas/            # Lista, calendario, check-in
│   ├── estancias/           # Folio de estancia
│   └── reportes/            # Dashboard de reportes
├── static/                  # Archivos estáticos
├── views_frontend.py        # Vistas del frontend (monolítico)
=======
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
>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

<<<<<<< HEAD
## 🔌 API REST

La API está disponible bajo el prefijo `/api/` y documentada automáticamente:

| Endpoint | Descripción |
|----------|-------------|
| `GET /api/swagger/` | Documentación interactiva Swagger UI |
| `GET /api/redoc/` | Documentación ReDoc |
| `POST /api/token/` | Obtener token JWT |
| `POST /api/token/refresh/` | Refrescar token JWT |

**Autenticación:** Bearer Token (JWT)

```bash
# Ejemplo: obtener token
curl -X POST http://localhost:8000/api/token/ \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "tu_password"}'
=======
## 🔄 Flujo de trabajo

```
  [Huésped] ──→ [Reserva] ──→ [Check-in] ──→ [Folio] ──→ [Check-out]
      │               │              │             │              │
  Buscar por      Por día o      Asignar       Cargos         Cierre
  documento       por hora      habitación     extra          + IGV
>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33
```

---

<<<<<<< HEAD
## 🔄 Flujo principal del sistema

```
Registrar huésped → Crear reserva → Check-in → Folio de cargos → Check-out
       ↓                  ↓              ↓              ↓               ↓
  Búsqueda por       Calendario      Asignar         Agregar        Generar
  documento o        de ocupación    habitación      cargos extra   comprobante
  nombre                             disponible      (restaurante,  con IGV
                                                     lavandería…)
=======
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
>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33
```

---

## 🧪 Tests

```bash
<<<<<<< HEAD
# Correr todos los tests
pytest

# Con cobertura
pytest --cov=. --cov-report=html

# Ver reporte de cobertura
open htmlcov/index.html
=======
pytest                              # Todos los tests
pytest --cov=. --cov-report=html    # Con reporte de cobertura
>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33
```

---

## ⚙️ Variables de entorno

<<<<<<< HEAD
Crea un archivo `.env` en la raíz con las siguientes variables:

```env
SECRET_KEY=tu_clave_secreta_aqui
=======
```env
SECRET_KEY=clave-secreta-larga-y-aleatoria
>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

<<<<<<< HEAD
## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor sigue este flujo:

1. Haz fork del repositorio
2. Crea tu rama: `git checkout -b feature/nueva-funcionalidad`
3. Commitea tus cambios: `git commit -m "feat: descripción"`
4. Haz push: `git push origin feature/nueva-funcionalidad`
5. Abre un Pull Request

---

## 👨‍💻 Autor

Desarrollado por **Henry Delgado Bustamante**

---

<div align="center">
<sub>Hecho con ❤️ y Django · 2026</sub>
=======
<div align="center">

**HotelSystem** · Django 6.0 · 2026

>>>>>>> 60ef68e5b6597fd1e0fb827d605ab6ba4d56fe33
</div>