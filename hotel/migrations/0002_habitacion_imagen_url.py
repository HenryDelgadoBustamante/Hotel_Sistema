from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hotel', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='habitacion',
            name='imagen_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
