# Documentación Completa del Sistema Hotel_Sistema

## Índice

1. [Visión General](#visión-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Stack Tecnológico](#stack-tecnológico)
4. [Estructura del Proyecto](#estructura-del-proyecto)
5. [Módulos del Sistema](#módulos-del-sistema)
   - [Hotel](#1-módulo-hotel)
   - [Huéspedes](#2-módulo-huéspedes)
   - [Reservas](#3-módulo-reservas)
   - [Estancias](#4-módulo-estancias)
   - [Caja](#5-módulo-caja)
   - [Inventario](#6-módulo-inventario)
   - [Atención (Tickets)](#7-módulo-atención-tickets)
   - [Reportes](#8-módulo-reportes)
6. [Modelo de Datos Completo](#modelo-de-datos-completo)
7. [Flujo de Trabajo Principal](#flujo-de-trabajo-principal)
8. [Sistema de Autenticación y Roles](#sistema-de-autenticación-y-roles)
9. [API REST](#api-rest)
10. [Configuración del Sistema](#configuración-del-sistema)
11. [Base de Datos](#base-de-datos)
12. [Frontend](#frontend)
13. [Seguridad](#seguridad)
14. [Testing](#testing)
15. [Docker y Despliegue](#docker-y-despliegue)

---

## Visión General

**Hotel_Sistema** es un sistema completo de gestión hotelera desarrollado con Django 5.x. Permite administrar todas las operaciones de un hotel: desde la gestión de habitaciones y reservas, hasta el control de caja, inventario y reportes en tiempo real.

El sistema opera con dos modalidades de reserva:
- **Por día**: Reservas tradicionales nocturnas
- **Por hora**: Reservas de corta duración (bloques de 3 horas)

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Templates)                      │
│  Bootstrap 5 + Chart.js + Google Fonts (Inter)              │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   BACKEND (Django)                           │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │  Hotel   │ │Huéspedes │ │ Reservas │ │Estancias │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │   Caja   │ │Inventario│ │Atención  │ │ Reportes │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │         API REST (Django REST Framework)         │       │
│  │         Autenticación: JWT (SimpleJWT)           │       │
│  └──────────────────────────────────────────────────┘       │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  BASE DE DATOS                               │
│          PostgreSQL (Prod) / SQLite (Dev)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Stack Tecnológico

| Capa | Tecnología |
|------|------------|
| **Backend** | Django 5.x, Django REST Framework 3.15+ |
| **Autenticación** | SimpleJWT (JWT: access 8h, refresh 1 día) |
| **Frontend** | Bootstrap 5.3, Bootstrap Icons, Chart.js, Google Fonts (Inter) |
| **API Docs** | drf-yasg (Swagger UI + ReDoc) |
| **Base de Datos** | PostgreSQL (producción), SQLite (desarrollo/tests) |
| **Infraestructura** | Docker, docker-compose |
| **Testing** | pytest, pytest-django, coverage |
| **Forms** | django-crispy-forms + crispy-bootstrap5 |
| **Filtros API** | django-filter |
| **CORS** | django-cors-headers |
| **Email** | SMTP (configurable) |
| **Excel** | openpyxl |

---

## Estructura del Proyecto

```
Hotel_Sistema/
├── config/                    # Configuración principal de Django
│   ├── settings.py            # Ajustes globales (DB, Auth, DRF, JWT, etc.)
│   ├── urls.py                # Enrutador principal (APIs y Web)
│   ├── roles.py               # Definición de roles y permisos
│   ├── permissions.py         # Permisos personalizados
│   ├── wsgi.py / asgi.py      # Configuración de servidor
│   └── management/            # Comandos personalizados
│
├── hotel/                     # App: Hoteles y Habitaciones
│   ├── models.py              # Hotel, TipoHabitacion, Habitacion
│   ├── views.py               # API Views (DRF)
│   ├── serializers.py         # Serializadores DRF
│   ├── urls.py                # Rutas API
│   └── admin.py               # Configuración del admin
│
├── huespedes/                 # App: Registro de clientes
│   ├── models.py              # Huesped
│   ├── views.py               # API Views
│   ├── serializers.py         # Serializadores
│   ├── urls.py                # Rutas API
│   └── admin.py
│
├── reservas/                  # App: Gestión de reservas
│   ├── models.py              # Tarifa, Reserva
│   ├── views.py               # API Views
│   ├── serializers.py         # Serializadores
│   ├── urls.py                # Rutas API
│   └── admin.py
│
├── estancias/                 # App: Check-in, check-out y folios
│   ├── models.py              # Estancia, CargoEstancia, Folio, Pago, Reembolso, HistorialHabitacionEstancia
│   ├── views.py               # API Views
│   ├── serializers.py         # Serializadores
│   ├── services.py            # Lógica de negocio
│   ├── urls.py                # Rutas API
│   └── admin.py
│
├── caja/                      # App: Control de caja
│   ├── models.py              # Caja, MovimientoCaja, AnomaliaCaja
│   ├── views.py               # API Views
│   ├── services.py            # Servicios de caja
│   ├── urls.py                # Rutas API
│   └── admin.py
│
├── inventario/                # App: Gestión de inventario
│   ├── models.py              # CategoriaProducto, UnidadMedida, Proveedor, Producto, MovimientoInventario, ConteoFisico, DetalleConteoFisico
│   ├── views.py               # API Views
│   ├── urls.py                # Rutas API
│   └── admin.py
│
├── atencion/                  # App: Tickets de atención
│   ├── models.py              # Modelos de tickets
│   ├── views.py               # API Views
│   ├── urls.py                # Rutas API
│   └── admin.py
│
├── reportes/                  # App: Estadísticas y auditoría
│   ├── models.py              # Auditoria, LoginIntento, PasswordResetToken
│   ├── views.py               # API Views
│   ├── signals.py             # Señales Django
│   ├── urls.py                # Rutas API
│   └── admin.py
│
├── utils/                     # Utilidades compartidas
│   └── auditoria.py           # Funciones de auditoría
│
├── views_frontend.py          # Controlador unificado para renderizado frontend
│
├── templates/                 # Plantillas HTML por módulo
│   ├── base.html              # Layout global principal
│   ├── dashboard.html         # Plano de habitaciones
│   ├── login.html             # Login Glassmorphism
│   ├── habitaciones/
│   ├── huespedes/
│   ├── reservas/
│   ├── estancias/
│   ├── reportes/
│   └── ...
│
├── static/                    # Archivos CSS y JS
├── fixtures/                  # Datos de demostración
├── manage.py                  # Script de gestión Django
├── requirements.txt           # Dependencias Python
├── docker-compose.yml         # Configuración Docker
├── Dockerfile                 # Imagen Docker
└── .env / .env.example        # Variables de entorno
```

---

## Módulos del Sistema

### 1. Módulo Hotel

Gestiona la configuración del hotel y las habitaciones.

#### Modelos

**Hotel**
- Configuración general: nombre, razón social, RUC, dirección, estrellas, teléfono, correo
- Horarios estándar: check-in (15:00), check-out (12:00)
- **Early Check-In**: configuración de tolerancia, tipo de cargo (fijo/porcentaje), monto, rol para exonerar
- **Late Check-Out**: hora máxima (18:00), tolerancia, tipo de cargo, horas bloque, rol para exonerar
- **Alertas**: minutos antes del checkout para alertar al recepcionista (15/30/60 min)

**TipoHabitacion**
- Nombre, capacidad, precio base, amenidades (JSON)
- Relacionado con un Hotel (ForeignKey)

**Habitacion**
- Número, piso, estado, imágenes (URL + JSON de galería)
- **Estados**: `DISPONIBLE`, `OCUPADA`, `LIMPIEZA`, `MANTENIMIENTO`
- Relacionada con Hotel y TipoHabitacion
- Único: combinación hotel + número

---

### 2. Módulo Huéspedes

Control de fichas de clientes del hotel.

#### Modelo: Huesped

- **Tipo documento**: DNI, Pasaporte, Carné de Extranjería
- Número de documento (único)
- Nombres, apellidos, email, teléfono, nacionalidad
- Propiedad `nombre_completo`: concatena nombres + apellidos

---

### 3. Módulo Reservas

Gestión completa de reservas con lógica tarifaria.

#### Modelos

**Tarifa**
- Tipo de habitación, nombre, precio por noche
- Vigencia: fecha_inicio, fecha_fin

**Reserva**
- **Modalidad**: Por día (`DIA`) o Por hora (`HORA`)
- **Estado**: `PENDIENTE`, `CONFIRMADA`, `CHECKIN`, `CHECKOUT`, `CANCELADA`, `REEMBOLSADO`
- **Origen**: Directo, Web, Agencia
- Fechas: entrada/salida (date), entrada/salida (datetime)
- Para modalidad por hora: duración_horas, tolerancia_minutos, cargo_extra_desde_minutos
- Número de adultos (validado contra capacidad de habitación)
- Precio total calculado automáticamente
- Observaciones y motivo de cancelación

##### Lógica de Precios

**Por hora**:
- Bloques de 3 horas
- Cada bloque = 35% del precio base del tipo de habitación
- Ejemplo: precio_base = 100, 3 horas = 35, 6 horas = 70

**Por día**:
- Busca tarifa vigente en el rango de fechas
- Si no existe, usa precio_base del tipo de habitación
- Total = precio_noche × número de noches

##### Validaciones
- No reservar habitación en mantenimiento
- No superar capacidad de la habitación
- No solapar reservas activas en la misma habitación
- Fecha de salida debe ser posterior a la entrada

##### Propiedades
- `observaciones_limpias`: retorna observaciones sin datos JSON de productos
- `total_pagado`: suma de todos los pagos asociados
- `saldo_pendiente`: precio_total - total_pagado (mínimo 0)

---

### 4. Módulo Estancias

Gestión del hospedaje activo: check-in, cargos, folios, pagos y check-out.

#### Modelos

**Estancia**
- Creada al hacer check-in de una reserva (OneToOne con Reserva)
- Habitación asignada, fecha check-in, fecha checkout
- Precio final, estado (`ACTIVA`, `FINALIZADA`)
- `registrado_por`: usuario que hizo el check-in

**Método `hacer_checkout()`**:
1. Cierra el folio asociado
2. Valida que no haya saldo pendiente
3. Registra fecha de checkout
4. Cambia habitación a estado `LIMPIEZA`
5. Cambia reserva a estado `CHECKOUT`

**CargoEstancia**
- **Tipo**: Habitación, Restaurante, Lavandería, Otro
- Concepto, monto, fecha
- Integración con inventario: producto y cantidad
- **Exoneración**: campos exonerado, motivo_exoneracion, exonerado_por
- Validación: monto debe ser positivo

**Folio**
- OneToOne con Estancia
- Subtotal, IGV (18%), Total
- Estado: `ABIERTO`, `CERRADO`
- `calcular_totales()`: calcula subtotal = total/1.18, igv = total - subtotal
- `total_pagado`: suma de pagos
- `saldo_pendiente`: total - total_pagado (mínimo 0)

**Pago**
- **Método**: Efectivo, Tarjeta, Transferencia, Yape/Plin
- Puede estar vinculado a un Folio o a una Reserva (anticipos)
- Monto, fecha, ID de transacción
- Propiedad `reembolsado`: verifica si los reembolsos aprobados cubren el monto

**Reembolso**
- Vinculado a un Pago
- **Estado**: `SOLICITADO`, `APROBADO`, `RECHAZADO`
- Monto, motivo, observación
- `solicitado_por`, `aprobado_por` (usuarios)
- Fecha de solicitud y resolución

**HistorialHabitacionEstancia**
- Registra cambios de habitación durante una estancia
- Habitación anterior, habitación nueva, motivo
- Usuario que realizó el cambio, diferencia tarifaria

---

### 5. Módulo Caja

Control financiero de caja: aperturas, cierres, movimientos y anomalías.

#### Modelos

**Caja**
- Usuario responsable, fecha apertura/cierre
- Monto inicial, ingresos, egresos, esperado, real, diferencia
- Estado: `ABIERTA`, `CERRADA`
- Observaciones de apertura y cierre
- Arqueo: fecha y estado

**Método `recalcular_totales()`**:
- Suma ingresos y egresos de MovimientoCaja
- Calcula: esperado = inicial + ingresos - egresos
- Calcula: diferencia = real - esperado

**MovimientoCaja**
- **Tipo**: Ingreso, Egreso
- **Concepto**: Pago Reserva, Pago Hospedaje, Pago Consumos, Reembolso, Ajuste Manual, Otros
- **Método de pago**: Efectivo, Tarjeta Débito, Tarjeta Crédito, Transferencia, Yape, Plin
- Descripción, usuario, referencia
- Vinculación opcional: pago_origen, reembolso_origen
- Validaciones: monto > 0, caja debe estar abierta
- Al guardar, recalcula totales de la caja

**AnomaliaCaja**
- **Tipo**: Faltante, Sobrante, Billete Falso, Comprobante Duplicado, Pago Rechazado, Otro
- Monto, observación
- Estado: resuelta/no resuelta
- `resuelta_por`, `fecha_resolucion`

---

### 6. Módulo Inventario

Gestión de productos, servicios, stock y proveedores.

#### Modelos

**CategoriaProducto**
- Nombre (único), estado (Activo/Inactivo)

**UnidadMedida**
- Nombre, abreviatura (ej: "Unidad" → "UND")

**Proveedor**
- Razón social, documento fiscal (único)
- Teléfono, correo, dirección, persona de contacto
- Estado, observaciones

**Producto**
- **Tipo**: Producto con Stock, Servicio sin Stock, Producto de Uso Interno
- Código interno (único), nombre, descripción
- Categoría, tipo, unidad de medida
- Precio de venta, costo referencial
- Controla stock, stock actual, stock mínimo
- Estado, vendible, uso interno
- Propiedad `estado_disponibilidad`: "Disponible", "Sin stock", "Stock bajo"

**MovimientoInventario**
- **Tipo**: Entrada, Salida, Consumo, Devolución, Ajuste Positivo, Ajuste Negativo, Anulación
- Producto, cantidad, existencia anterior/posterior
- Motivo, proveedor, costo referencial
- Documento de referencia, usuario
- Vinculación opcional con estancia
- Observación

**ConteoFisico**
- Fecha inicio/fin, estado (Borrador, En Proceso, Pendiente Revisión, Aprobado, Cancelado)
- Usuario creador, usuario aprobador
- Observaciones

**DetalleConteoFisico**
- Conteo, producto
- Stock sistema, stock físico, diferencia

---

### 7. Módulo Atención (Tickets)

Sistema de tickets para gestión de incidencias y solicitudes.

#### Funcionalidades (según URLs)
- Lista de tickets
- Crear ticket nuevo
- Ver detalle de ticket
- Iniciar ticket
- Resolver ticket
- Cerrar ticket
- Reabrir ticket
- Agregar seguimiento
- Agregar cargo a ticket
- Lista de reembolsos (admin)

---

### 8. Módulo Reportes

Estadísticas, auditoría y seguridad.

#### Modelos

**Auditoria**
- Usuario, acción, fecha
- Registro ID, tabla afectada
- Estado anterior, estado nuevo
- Observación

**Función `registrar_auditoria()`**:
- Crea registros de auditoría con estado anterior y nuevo

**LoginIntento**
- Usuario, IP, user agent
- Exitoso/fallido, fecha
- Método `contar_fallidos_recientes()`: cuenta intentos fallidos en últimos N minutos
- Método `registrar()`: crea un registro de intento

**PasswordResetToken**
- Usuario, token (UUID), creado, usado
- Expiración (1 hora por defecto)
- Método `esta_valido()`: verifica que no esté usado y no haya expirado

---

## Modelo de Datos Completo

```
┌─────────────┐       ┌──────────────────┐       ┌─────────────┐
│   Hotel     │──1:N──│ TipoHabitacion   │──1:N──│  Tarifa     │
│             │       └────────┬─────────┘       └─────────────┘
│ nombre      │                │
│ ruc         │                │ 1:N
│ direccion   │                │
│ estrellas   │                ▼
│ horarios    │       ┌──────────────────┐
│ early/late  │       │   Habitacion     │
└─────────────┘       │ estado           │
                      │ numero, piso     │
                      │ imagenes         │
                      └────────┬─────────┘
                               │
                    ┌──────────┼──────────┐
                    │          │          │
                    ▼          ▼          ▼
              ┌─────────┐ ┌────────┐ ┌──────────┐
              │Reserva  │ │Estancia│ │Historial  │
              │         │ │        │ │CambioHab  │
              │modalidad│ │folio   │ │           │
              │estado   │ │cargos  │ │           │
              │precios  │ │checkout│ │           │
              └────┬────┘ └───┬────┘ └──────────┘
                   │          │
                   │          │ 1:1
                   │          ▼
                   │    ┌──────────┐
                   │    │  Folio   │
                   │    │subtotal  │
                   │    │igv/total │
                   │    │estado    │
                   │    └────┬─────┘
                   │         │
                   │         │ 1:N
                   │         ▼
                   │    ┌──────────┐
                   │    │  Pago    │
                   │    │metodo    │
                   │    │monto     │
                   │    └────┬─────┘
                   │         │
                   │         │ 1:N
                   │         ▼
                   │    ┌──────────┐
                   │    │Reembolso │
                   │    │estado    │
                   │    │monto     │
                   │    └──────────┘
                   │
                   ▼
              ┌──────────┐
              │ Huesped  │
              │tipo_doc  │
              │num_doc   │
              │nombres   │
              │apellidos │
              └──────────┘

┌──────────┐       ┌──────────────────┐       ┌─────────────┐
│  Caja    │──1:N──│ MovimientoCaja   │       │  Producto   │
│usuario   │       │tipo/concepto     │       │codigo/nombre│
│estado    │       │monto/metodo      │       │stock/precio │
│montos    │       │pago_origen       │       │categoria    │
└──────────┘       └──────────────────┘       └──────┬──────┘
                                                     │ 1:N
                                               ┌─────▼──────┐
                                               │Movimiento  │
                                               │Inventario  │
                                               │tipo/cantidad│
                                               └────────────┘

┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ConteoFisico  │──1:N│DetalleConteo    │    │  Auditoria       │
│estado        │    │stock_sistema     │    │  accion/fecha    │
│fechas        │    │stock_fisico      │    │  tabla/registro  │
└──────────────┘    │diferencia        │    └──────────────────┘
                    └──────────────────┘
                    ┌──────────────────┐
                    │  LoginIntento    │
                    │  usuario/ip      │
                    │  exitoso/fecha   │
                    └──────────────────┘
                    ┌──────────────────┐
                    │PasswordResetToken│
                    │token/expiracion  │
                    │usado             │
                    └──────────────────┘
```

---

## Flujo de Trabajo Principal

### Flujo Completo de Hospedaje

```
1. REGISTRO DE HUÉSPED
   └─> Se crea ficha con documento (DNI/Pasaporte/CE)

2. CONSULTA DE DISPONIBILIDAD
   └─> Se verifica habitaciones disponibles por fecha/tipo

3. CREACIÓN DE RESERVA
   ├─> Por día: fecha entrada → fecha salida
   └─> Por hora: fecha/hora entrada + duración (bloques de 3h)
   └─> Se calcula precio automáticamente

4. PAGO DE ANTICIPO (opcional)
   └─> Se registra pago vinculado a la reserva

5. CHECK-IN
   ├─> Se asigna habitación específica
   ├─> Se crea Estancia (OneToOne con Reserva)
   ├─> Se crea Folio (abierto)
   ├─> Se registra usuario que hizo check-in
   └─> Habitación cambia a OCUPADA

6. ESTANCIA ACTIVA
   ├─> Se pueden agregar cargos extra:
   │   ├─> Restaurante
   │   ├─> Lavandería
   │   ├─> Otros servicios
   │   └─> Productos del inventario
   ├─> Se pueden exonerar cargos (con autorización)
   ├─> Se puede cambiar de habitación
   └─> Se pueden hacer pagos parciales

7. CHECK-OUT
   ├─> Se valida que el folio no tenga saldo pendiente
   ├─> Se cierra el folio
   ├─> Habitación cambia a LIMPIEZA
   ├─> Reserva cambia a CHECKOUT
   └─> Estancia cambia a FINALIZADA

8. POST-CHECKOUT
   ├─> Se pueden solicitar reembolsos
   ├─> Los reembolsos requieren aprobación
   └─> Los movimientos se registran en caja
```

### Flujo de Caja

```
1. APERTURA DE CAJA
   └─> Usuario abre caja con monto inicial

2. REGISTRO DE MOVIMIENTOS
   ├─> Ingresos: pagos de huéspedes, anticipos, consumos
   └─> Egresos: reembolsos, ajustes

3. CIERRE DE CAJA
   ├─> Se ingresa monto real contado
   ├─> Se calcula diferencia (real - esperado)
   └─> Se registran anomalías si existen

4. ARQUEO
   └─> Verificación de consistencia
```

### Flujo de Inventario

```
1. CONFIGURACIÓN
   ├─> Crear categorías
   ├─> Crear unidades de medida
   └─> Registrar proveedores

2. GESTIÓN DE PRODUCTOS
   ├─> Productos con stock (controla inventario)
   ├─> Servicios sin stock
   └─> Productos de uso interno

3. MOVIMIENTOS
   ├─> Entradas (compras)
   ├─> Salidas (consumos)
   ├─> Ajustes
   └─> Devoluciones

4. CONTEO FÍSICO
   ├─> Crear conteo
   ├─> Registrar stock físico
   ├─> Comparar con stock del sistema
   └─> Aprobar y ajustar diferencias
```

---

## Sistema de Autenticación y Roles

### Roles del Sistema

| Rol | Descripción | Permisos |
|-----|-------------|----------|
| **admin** | Administrador del sistema | Acceso total, gestión de usuarios, aprobación de reembolsos, exoneraciones |
| **recepcionista** | Personal de recepción | Reservas, check-in/out, cargos, pagos, gestión de huéspedes |
| **housekeeping** | Personal de limpieza | Estado de habitaciones, panel de housekeeping |

### Jerarquía de Permisos

```
admin (superusuario o grupo admin)
  └─> Incluye permisos de recepcionista
       └─> Incluye permisos básicos
            └─> housekeeping (solo lectura de habitaciones)
```

### Autenticación

- **JWT (SimpleJWT)**: Access token 8 horas, Refresh token 1 día
- **Session-based** para el frontend web
- **Login**: con registro de intentos (exitosos y fallidos)
- **Bloqueo**: por intentos fallidos consecutivos
- **Recuperación de contraseña**: token UUID con expiración de 1 hora
- **Sesiones activas**: listado y cierre de sesiones

### Endpoints de Autenticación

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/token/` | POST | Obtener JWT (access + refresh) |
| `/api/token/refresh/` | POST | Renovar access token |
| `/api/perfil/` | GET | Datos del usuario autenticado |
| `/login/` | GET/POST | Login web |
| `/logout/` | POST | Logout web |
| `/recuperar-contrasena/` | GET/POST | Solicitar reset de password |
| `/reset/<token>/` | GET/POST | Confirmar reset de password |
| `/sesiones/` | GET | Ver sesiones activas |
| `/sesiones/<key>/cerrar/` | POST | Cerrar sesión específica |

---

## API REST

### Configuración

- **Autenticación por defecto**: JWT (IsAuthenticated)
- **Filtros**: DjangoFilterBackend
- **Documentación**: Swagger UI (`/api/docs/`) y ReDoc (`/api/redoc/`)

### Endpoints por Módulo

#### Hotel (`/api/`)
- Habitaciones (CRUD)
- Tipos de habitación
- Configuración del hotel
- Habitaciones disponibles (API)

#### Huéspedes (`/api/`)
- Huéspedes (CRUD)
- Búsqueda por documento
- Consulta DNI (API externa)
- Exportar a Excel

#### Reservas (`/api/`)
- Reservas (CRUD)
- Calendario de reservas
- Cancelar reserva
- Registrar pago de anticipo

#### Estancias (`/api/`)
- Estancias (CRUD)
- Folios
- Cargos
- Pagos
- Checkout
- Cambio de habitación
- Reembolsos

#### Caja (`/api/`)
- Cajas (apertura/cierre)
- Movimientos
- Anomalías

#### Inventario (`/api/`)
- Productos (CRUD)
- Categorías
- Proveedores
- Movimientos de inventario
- Conteos físicos

#### Reportes (`/api/`)
- Ocupación
- Housekeeping recientes
- Dashboard KPIs

### Autenticación API

```bash
# 1. Obtener token
curl -X POST http://localhost:8000/api/token/ \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "admin"}'

# Respuesta:
# {
#   "access": "eyJ...",
#   "refresh": "eyJ..."
# }

# 2. Usar token
curl http://localhost:8000/api/habitaciones/ \
     -H "Authorization: Bearer <access_token>"

# 3. Renovar token
curl -X POST http://localhost:8000/api/token/refresh/ \
     -H "Content-Type: application/json" \
     -d '{"refresh": "<refresh_token>"}'
```

---

## Configuración del Sistema

### Variables de Entorno (`.env`)

| Variable | Descripción | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Clave secreta de Django | (requerida) |
| `DEBUG` | Modo debug | `True` |
| `DB_NAME` | Nombre de la base de datos | `hotel_db` |
| `DB_USER` | Usuario de la BD | `postgres` |
| `DB_PASSWORD` | Contraseña de la BD | `postgres` |
| `DB_HOST` | Host de la BD | `db` |
| `DB_PORT` | Puerto de la BD | `5432` |
| `EMAIL_HOST` | Servidor SMTP | `smtp.gmail.com` |
| `EMAIL_PORT` | Puerto SMTP | `587` |
| `EMAIL_USE_TLS` | Usar TLS | `True` |
| `EMAIL_HOST_USER` | Usuario de email | (vacío) |
| `EMAIL_HOST_PASSWORD` | Contraseña de email | (vacío) |
| `DEFAULT_FROM_EMAIL` | Remitente por defecto | `noreply@hotelsystem.com` |

### Settings Clave

```python
# Idioma y zona horaria
LANGUAGE_CODE = 'es-pe'
TIME_ZONE = 'America/Lima'

# JWT
ACCESS_TOKEN_LIFETIME = 8 horas
REFRESH_TOKEN_LIFETIME = 1 día

# CORS
CORS_ALLOW_ALL_ORIGINS = True

# Archivos
STATIC_URL = '/static/'
MEDIA_URL = '/media/'
```

---

## Base de Datos

### Desarrollo
- **Motor**: SQLite
- **Archivo**: `db.sqlite3`

### Producción (Docker)
- **Motor**: PostgreSQL
- **Configuración**: variables de entorno

### Testing
- **Motor**: SQLite (automático al ejecutar pytest)

### Migraciones

Cada app tiene su propio conjunto de migraciones:

| App | Migraciones | Descripción |
|-----|-------------|-------------|
| hotel | 0001-0007 | Habitaciones, tipos, configuraciones hotel |
| huespedes | 0001 | Modelo de huésped |
| reservas | 0001-0004 | Reservas, tarifas, modalidades |
| estancias | 0001-0007 | Estancias, folios, cargos, pagos, reembolsos |
| caja | 0001 | Cajas, movimientos, anomalías |
| inventario | 0001-0002 | Productos, unidades de medida |
| reportes | 0001-0003 | Auditoría, login intentos, tokens |

---

## Frontend

### Templates

El sistema usa templates Django con Bootstrap 5:

| Template | Descripción |
|----------|-------------|
| `base.html` | Layout global con sidebar, navbar |
| `login.html` | Login con diseño Glassmorphism |
| `dashboard.html` | Plano visual de habitaciones |
| `huespedes/lista.html` | Lista de huéspedes |
| `reservas/lista.html` | Lista de reservas |
| `reservas/calendario.html` | Calendario Gantt mensual |
| `reservas/nueva.html` | Formulario nueva reserva |
| `estancias/lista.html` | Lista de estancias activas |
| `estancias/folio.html` | Folio de cargos |
| `housekeeping.html` | Panel de limpieza |
| `reportes.html` | Dashboard con KPIs y gráficos |

### Vistas Frontend (`views_frontend.py`)

Todas las vistas web están centralizadas en este archivo:

- **Autenticación**: `login_view`, `logout_view`
- **Dashboard**: `dashboard`
- **Huéspedes**: `huespedes_lista`, `huesped_nuevo`, `huesped_editar`, `exportar_huespedes_excel`
- **Habitaciones**: `habitaciones_lista`, `habitacion_nueva`, `habitacion_editar`
- **Reservas**: `reservas_lista`, `reserva_nueva`, `reserva_detalle`, `reserva_editar`, `reserva_cancelar`, `reservas_calendario`, `consultar_disponibilidad`
- **Check-in**: `checkin_directo`, `reserva_checkin`
- **Estancias**: `estancias_lista`, `folio_view`, `agregar_cargo`, `registrar_pago`, `checkout_view`, `cambiar_habitacion`
- **Housekeeping**: `housekeeping_view`, `housekeeping_estado`, `actualizar_estado_habitacion`
- **Tickets**: `tickets_lista`, `ticket_nuevo`, `ticket_detalle`, `ticket_iniciar`, `ticket_resolver`, `ticket_cerrar`, `ticket_reabrir`
- **Usuarios**: `usuarios_lista`, `usuario_nuevo`, `usuario_editar`, `usuario_eliminar`
- **Perfil**: `mi_perfil`, `cambiar_password`
- **Recuperación**: `recuperar_contrasena`, `reset_confirmar`, `desbloquear_usuario`
- **Sesiones**: `sesiones_activas`, `cerrar_sesion`
- **Configuración**: `hotel_configuracion`
- **APIs AJAX**: `api_habitaciones_disponibles`, `api_consulta_dni`, `api_buscar_huesped`, `api_ocupacion_habitaciones`, `api_habitaciones_housekeeping_recientes`

### APIs AJAX

Endpoints que retornan JSON para consumo desde el frontend:

| Endpoint | Descripción |
|----------|-------------|
| `/api/habitaciones-disponibles/` | Habitaciones disponibles por fecha |
| `/api/dni/` | Consulta de DNI (API externa RENIEC) |
| `/api/buscar-huesped/` | Búsqueda de huéspedes |
| `/api/ocupacion/` | Datos de ocupación para gráficos |
| `/api/housekeeping-recientes/` | Habitaciones recientes para housekeeping |

---

## Seguridad

### Autenticación
- JWT con expiración (8h access, 1d refresh)
- Registro de todos los intentos de login
- Bloqueo por intentos fallidos consecutivos
- Tokens de recuperación de contraseña con expiración (1h)

### Autorización
- Roles: admin, recepcionista, housekeeping
- Permisos por vista y por API
- DRF permissions: IsAuthenticated por defecto

### Auditoría
- Registro de todas las acciones importantes
- Estado anterior y nuevo de los registros
- Tabla afectada y usuario responsable

### Protección
- CSRF protection (Django)
- XSS protection (Django)
- Clickjacking protection (Django)
- CORS configurable

### Gestión de Sesiones
- Listado de sesiones activas
- Cierre individual de sesiones
- Cierre de sesión al cambiar contraseña

---

## Testing

### Configuración

```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = tests.py test_*.py *_tests.py
```

### Ejecución

```bash
# Suite completa
pytest

# Con cobertura
pytest --cov=. --cov-report=html

# Tests específicos
pytest hotel/tests.py
pytest reservas/tests.py
```

### Base de Datos en Tests
- Usa SQLite automáticamente cuando `sys.argv` contiene 'test' o 'pytest'

---

## Docker y Despliegue

### docker-compose.yml

Servicios:
- **db**: PostgreSQL
- **web**: Aplicación Django

### Dockerfile

- Basado en Python
- Instala dependencias de `requirements.txt`
- Ejecuta `entrypoint.sh`

### entrypoint.sh

1. Espera a que PostgreSQL esté disponible
2. Aplica migraciones (`migrate`)
3. Carga datos de demostración (fixtures)
4. Inicia el servidor Django

### Inicio con Docker

```bash
# Copiar variables de entorno
copy .env.example .env

# Construir y levantar
docker compose up --build

# Acceder en http://localhost:8000
```

### Credenciales por Defecto

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| `admin` | `admin` | Administrador |
| `Recepcionista` | (ver backup) | Recepcionista |
| `Limpieza` | (ver backup) | Housekeeping |

---

## Flujo de Datos entre Módulos

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FLUJO DE DATOS                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  HUESPED ──crea──→ RESERVA ──calcula──→ TARIFA                      │
│     │                    │                                          │
│     │                    │ check-in                                 │
│     │                    ▼                                          │
│     │              ESTANCIA ──crea──→ FOLIO                         │
│     │                    │              │                            │
│     │                    │ agrega       │ calcula                    │
│     │                    ▼              ▼                            │
│     │            CARGOESTANCIA      PAGO                             │
│     │                    │              │                            │
│     │                    │ vincula      │ registra                   │
│     │                    ▼              ▼                            │
│     │             PRODUCTO ◄──── MOVIMIENTOCAJA                     │
│     │             (inventario)         │                             │
│     │                                │ cierra                       │
│     │                                ▼                              │
│     │                              CAJA                             │
│     │                                │                              │
│     │                                │ registra                     │
│     │                                ▼                              │
│     │                          AUDITORIA                            │
│     │                                                             │
│     └──────────────────► REPORTES ◄───────────────────────────────┘
│                           (KPIs, gráficos, estadísticas)           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Resumen de Funcionalidades por Rol

### Administrador
- [x] Gestión completa de usuarios
- [x] Configuración del hotel (horarios, cargos early/late)
- [x] Aprobación de reembolsos
- [x] Exoneración de cargos
- [x] Arqueo de caja
- [x] Conteo físico de inventario
- [x] Reportes completos
- [x] Auditoría
- [x] Gestión de sesiones activas
- [x] Desbloqueo de usuarios

### Recepcionista
- [x] Registro de huéspedes
- [x] Creación y gestión de reservas
- [x] Check-in / Check-out
- [x] Asignación de habitaciones
- [x] Cargos extra (restaurante, lavandería, etc.)
- [x] Registro de pagos
- [x] Cambio de habitación
- [x] Solicitud de reembolsos
- [x] Consulta de disponibilidad
- [x] Calendario de reservas
- [x] Impresión de folios y fichas
- [x] Exportar huéspedes a Excel

### Housekeeping
- [x] Panel de estado de habitaciones
- [x] Actualización de estado (limpieza)
- [x] Vista de habitaciones recientes

---

## Glosario de Términos

| Término | Definición |
|---------|------------|
| **Check-In** | Proceso de registro de entrada del huésped |
| **Check-Out** | Proceso de salida y cierre de cuenta |
| **Early Check-In** | Entrada antes del horario estándar (puede tener cargo) |
| **Late Check-Out** | Salida después del horario estándar (puede tener cargo) |
| **Folio** | Cuenta detallada de cargos durante una estancia |
| **Cargo** | Imputación económica (habitación, restaurante, etc.) |
| **Exoneración** | Anulación de un cargo con autorización |
| **Reembolso** | Devolución de un pago realizado |
| **Modalidad por Hora** | Reserva de corta duración en bloques de 3 horas |
| **Modalidad por Día** | Reserva tradicional nocturna |
| **Housekeeping** | Servicio de limpieza y mantenimiento de habitaciones |
| **Arqueo** | Verificación de consistencia de caja |
| **Conteo Físico** | Verificación manual de existencias de inventario |
| **IGV** | Impuesto General a las Ventas (18% en Perú) |

---

## Notas Importantes

1. **Zona horaria**: El sistema usa `America/Lima` (UTC-5)
2. **Moneda**: Soles peruanos (S/.)
3. **IGV**: 18% (calculado como total/1.18 para subtotal)
4. **Documento de identidad**: DNI (8 dígitos), Pasaporte, Carné de Extranjería
5. **RUC**: 11 dígitos (Registro Único de Contribuyente del Perú)
6. **Métodos de pago locales**: Yape, Plin (billeteras digitales peruanas)
7. **Early/Late Check-Out**: Configurables por el administrador con roles de exoneración
8. **Alertas de checkout**: Configurables (15, 30 o 60 minutos antes)
