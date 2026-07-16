from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
import django

class CategoriaProducto(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    estado = models.CharField(max_length=10, choices=[('ACTIVO', 'Activo'), ('INACTIVO', 'Inactivo')], default='ACTIVO')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Categoría de Producto'
        verbose_name_plural = 'Categorías de Producto'

    def __str__(self):
        return self.nombre


class UnidadMedida(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    abreviatura = models.CharField(max_length=10)

    class Meta:
        verbose_name = 'Unidad de Medida'
        verbose_name_plural = 'Unidades de Medida'

    def __str__(self):
        return f"{self.nombre} ({self.abreviatura})"


class Proveedor(models.Model):
    razon_social = models.CharField(max_length=200)
    documento_fiscal = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    correo = models.EmailField(blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    persona_contacto = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=10, choices=[('ACTIVO', 'Activo'), ('INACTIVO', 'Inactivo')], default='ACTIVO')
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'

    def __str__(self):
        return self.razon_social


class Producto(models.Model):
    TIPO_CHOICES = [
        ('PRODUCTO_STOCK', 'Producto con Stock'),
        ('SERVICIO_SIN_STOCK', 'Servicio sin Stock'),
        ('PRODUCTO_INTERNO', 'Producto de Uso Interno'),
    ]

    codigo_interno = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    categoria = models.ForeignKey(CategoriaProducto, on_delete=models.PROTECT, related_name='productos')
    tipo_elemento = models.CharField(max_length=25, choices=TIPO_CHOICES, default='PRODUCTO_STOCK')
    unidad_medida = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, related_name='productos')
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(Decimal('0.00'))])
    costo_referencial = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(Decimal('0.00'))])
    controla_stock = models.BooleanField(default=True)
    stock_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(Decimal('0.00'))])
    estado = models.CharField(max_length=10, choices=[('ACTIVO', 'Activo'), ('INACTIVO', 'Inactivo')], default='ACTIVO')
    es_vendible = models.BooleanField(default=True)
    es_uso_interno = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Producto/Servicio'
        verbose_name_plural = 'Productos y Servicios'

    def __str__(self):
        return f"{self.nombre} ({self.codigo_interno})"

    def clean(self):
        if self.precio_venta < 0:
            raise ValidationError("El precio de venta no puede ser negativo.")
        if self.costo_referencial < 0:
            raise ValidationError("El costo referencial no puede ser negativo.")
        if self.stock_minimo < 0:
            raise ValidationError("El stock mínimo no puede ser negativo.")
        if self.controla_stock and self.stock_actual < 0:
            raise ValidationError("La existencia actual no puede ser negativa para productos que controlan stock.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def estado_disponibilidad(self):
        if not self.controla_stock:
            return 'Disponible'
        if self.stock_actual <= 0:
            return 'Sin stock'
        if self.stock_actual <= self.stock_minimo:
            return 'Stock bajo'
        return 'Disponible'


class MovimientoInventario(models.Model):
    TIPO_MOVIMIENTO_CHOICES = [
        ('ENTRADA', 'Entrada'),
        ('SALIDA', 'Salida'),
        ('CONSUMO', 'Consumo'),
        ('DEVOLUCION', 'Devolución'),
        ('AJUSTE_POS', 'Ajuste Positivo'),
        ('AJUSTE_NEG', 'Ajuste Negativo'),
        ('ANULACION', 'Anulación'),
    ]

    fecha = models.DateTimeField(auto_now_add=True)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='movimientos')
    tipo_movimiento = models.CharField(max_length=15, choices=TIPO_MOVIMIENTO_CHOICES)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    existencia_anterior = models.DecimalField(max_digits=10, decimal_places=2)
    existencia_posterior = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.CharField(max_length=200)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos')
    costo_referencial = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    documento_referencia = models.CharField(max_length=100, blank=True, null=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos_inventario')
    estancia = models.ForeignKey('estancias.Estancia', on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos_inventario')
    observacion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Movimiento de Inventario'
        verbose_name_plural = 'Movimientos de Inventario'
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.tipo_movimiento} - {self.producto.nombre} ({self.cantidad})"


class ConteoFisico(models.Model):
    ESTADO_CHOICES = [
        ('BORRADOR', 'Borrador'),
        ('PROCESO', 'En Proceso'),
        ('PENDIENTE_REVISION', 'Pendiente de Revisión'),
        ('APROBADO', 'Aprobado'),
        ('CANCELADO', 'Cancelado'),
    ]

    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='BORRADOR')
    usuario_creador = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conteos_creados')
    usuario_aprobador = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='conteos_aprobados')
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Conteo Físico'
        verbose_name_plural = 'Conteos Físicos'
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f"Conteo #{self.id} ({self.estado})"


class DetalleConteoFisico(models.Model):
    conteo = models.ForeignKey(ConteoFisico, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='conteos_detalles')
    stock_sistema = models.DecimalField(max_digits=10, decimal_places=2)
    stock_fisico = models.DecimalField(max_digits=10, decimal_places=2)
    diferencia = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Detalle de Conteo Físico'
        verbose_name_plural = 'Detalles de Conteo Físico'

    def __str__(self):
        return f"Conteo #{self.conteo.id} - {self.producto.nombre}"
