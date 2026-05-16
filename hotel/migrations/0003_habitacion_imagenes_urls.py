from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hotel', '0002_habitacion_imagen_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='habitacion',
            name='imagenes_urls',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
