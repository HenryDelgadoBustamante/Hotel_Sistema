from django.db import migrations

def seed_unidades_medida(apps, schema_editor):
    UnidadMedida = apps.get_model('inventario', 'UnidadMedida')
    
    unidades = [
        ('Unidad', 'UND'),
        ('Kilogramo', 'KG'),
        ('Litro', 'L'),
        ('Caja', 'CJ'),
        ('Paquete', 'PQT'),
    ]
    
    for nombre, abreviatura in unidades:
        # Usamos get_or_create para evitar duplicados si ya existen algunos
        UnidadMedida.objects.get_or_create(
            abreviatura=abreviatura,
            defaults={'nombre': nombre}
        )

def revert_unidades_medida(apps, schema_editor):
    UnidadMedida = apps.get_model('inventario', 'UnidadMedida')
    UnidadMedida.objects.filter(abreviatura__in=['UND', 'KG', 'L', 'CJ', 'PQT']).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('inventario', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_unidades_medida, revert_unidades_medida),
    ]
