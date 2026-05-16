<div align="center">

# 🏨 HotelSystem

**Sistema de Gestión Hotelera desarrollado con Django**

[![Django](https://img.shields.io/badge/Django-6.0-092E20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.17-red?style=flat-square&logo=django)](https://www.django-rest-framework.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

*Gestión completa de habitaciones, reservas, huéspedes, estancias y reportes en una sola plataforma.*

</div>

---

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
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

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
python manage.py runserver
```

---

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
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

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
```

---

## 🔄 Flujo principal del sistema

```
Registrar huésped → Crear reserva → Check-in → Folio de cargos → Check-out
       ↓                  ↓              ↓              ↓               ↓
  Búsqueda por       Calendario      Asignar         Agregar        Generar
  documento o        de ocupación    habitación      cargos extra   comprobante
  nombre                             disponible      (restaurante,  con IGV
                                                     lavandería…)
```

---

## 🧪 Tests

```bash
# Correr todos los tests
pytest

# Con cobertura
pytest --cov=. --cov-report=html

# Ver reporte de cobertura
open htmlcov/index.html
```

---

## ⚙️ Variables de entorno

Crea un archivo `.env` en la raíz con las siguientes variables:

```env
SECRET_KEY=tu_clave_secreta_aqui
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

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
</div>