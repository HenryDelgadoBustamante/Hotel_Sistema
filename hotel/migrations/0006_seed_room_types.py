from django.db import migrations

def seed_room_types(apps, schema_editor):
    Hotel = apps.get_model('hotel', 'Hotel')
    TipoHabitacion = apps.get_model('hotel', 'TipoHabitacion')
    Habitacion = apps.get_model('hotel', 'Habitacion')

    room_types_data = [
        {"nombre": "VIP", "capacidad": 2, "precio_base": 150.00, "amenidades": ["Jacuzzi", "Mini-bar", "Desayuno buffet", "Cama King-size"]},
        {"nombre": "Suite", "capacidad": 4, "precio_base": 250.00, "amenidades": ["Sala de estar", "Cocina equipada", "Smart TV 65''", "Terraza"]},
        {"nombre": "Matrimonial", "capacidad": 2, "precio_base": 120.00, "amenidades": ["Cama Queen-size", "Baño privado", "Wi-Fi de alta velocidad"]},
        {"nombre": "Airbnb", "capacidad": 3, "precio_base": 90.00, "amenidades": ["Kitchinete", "Entrada independiente", "Acceso a lavandería"]}
    ]

    for hotel in Hotel.objects.all():
        for item in room_types_data:
            # We look for a name match case-insensitively or exactly.
            tipo, created = TipoHabitacion.objects.get_or_create(
                hotel=hotel,
                nombre__iexact=item["nombre"],
                defaults={
                    "nombre": item["nombre"],
                    "capacidad": item["capacidad"],
                    "precio_base": item["precio_base"],
                    "amenidades": item["amenidades"]
                }
            )
            # If it already existed but had different capacity or price, we can optionally leave it.
            # Let's also create at least one physical room of each category if the hotel has no rooms of that category.
            if created or not Habitacion.objects.filter(hotel=hotel, tipo=tipo).exists():
                prefix = {
                    "VIP": "90",
                    "Suite": "80",
                    "Matrimonial": "70",
                    "Airbnb": "60"
                }.get(tipo.nombre, "50")
                
                # Check for existing room numbers to avoid conflicts
                for room_idx in range(1, 10):
                    num = f"{prefix}{room_idx}"
                    if not Habitacion.objects.filter(hotel=hotel, numero=num).exists():
                        Habitacion.objects.create(
                            hotel=hotel,
                            tipo=tipo,
                            numero=num,
                            piso=int(prefix[0]),
                            estado="DISPONIBLE"
                        )
                        break

def rollback_room_types(apps, schema_editor):
    TipoHabitacion = apps.get_model('hotel', 'TipoHabitacion')
    # Filter case-insensitive match for the seeded names
    TipoHabitacion.objects.filter(nombre__in=["VIP", "Suite", "Matrimonial", "Airbnb"]).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('hotel', '0005_add_alerta_checkout_minutos'),
    ]

    operations = [
        migrations.RunPython(seed_room_types, reverse_code=rollback_room_types),
    ]
