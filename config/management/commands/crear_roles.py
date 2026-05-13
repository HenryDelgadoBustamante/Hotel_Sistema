from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Crea los roles del sistema hotelero'

    def handle(self, *args, **kwargs):
        roles = ['admin', 'recepcionista', 'housekeeping']
        for rol in roles:
            group, created = Group.objects.get_or_create(name=rol)
            if created:
                self.stdout.write(f'✓ Rol creado: {rol}')
            else:
                self.stdout.write(f'  Rol ya existe: {rol}')

        usuarios_prueba = [
            {'username': 'recepcion1', 'password': 'recepcion123', 'email': 'recepcion@hotel.com', 'rol': 'recepcionista'},
            {'username': 'limpieza1', 'password': 'limpieza123', 'email': 'limpieza@hotel.com', 'rol': 'housekeeping'},
        ]

        for datos in usuarios_prueba:
            user, created = User.objects.get_or_create(
                username=datos['username'],
                defaults={'email': datos['email']}
            )
            if created:
                user.set_password(datos['password'])
                user.save()
                group = Group.objects.get(name=datos['rol'])
                user.groups.add(group)
                self.stdout.write(f'✓ Usuario creado: {datos["username"]} → rol: {datos["rol"]}')
            else:
                self.stdout.write(f'  Usuario ya existe: {datos["username"]}')

        self.stdout.write(self.style.SUCCESS('\\n✅ Roles y usuarios de prueba listos'))
