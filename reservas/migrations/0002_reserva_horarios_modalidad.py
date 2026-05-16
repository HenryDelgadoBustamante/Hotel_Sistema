from datetime import datetime, time

from django.db import migrations, models
from django.utils import timezone


def backfill_reserva_horarios(apps, schema_editor):
    Reserva = apps.get_model('reservas', 'Reserva')
    for reserva in Reserva.objects.filter(fecha_hora_entrada__isnull=True):
        entrada = datetime.combine(reserva.fecha_entrada, time(15, 0))
        salida = datetime.combine(reserva.fecha_salida, time(12, 0))
        reserva.fecha_hora_entrada = timezone.make_aware(entrada)
        reserva.fecha_hora_salida = timezone.make_aware(salida)
        reserva.save(update_fields=['fecha_hora_entrada', 'fecha_hora_salida'])


class Migration(migrations.Migration):

    dependencies = [
        ('reservas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='fecha_hora_entrada',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='reserva',
            name='fecha_hora_salida',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='reserva',
            name='modalidad',
            field=models.CharField(choices=[('DIA', 'Por dia'), ('HORA', 'Por horas')], default='DIA', max_length=10),
        ),
        migrations.AddField(
            model_name='reserva',
            name='duracion_horas',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name='reserva',
            name='tolerancia_minutos',
            field=models.PositiveIntegerField(default=10),
        ),
        migrations.AddField(
            model_name='reserva',
            name='cargo_extra_desde_minutos',
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.RunPython(backfill_reserva_horarios, migrations.RunPython.noop),
    ]
