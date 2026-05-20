from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission

class Command(BaseCommand):
    help = 'Crea los grupos predeterminados del sistema y asigna sus permisos (Administrador, Recepcionista, Housekeeping)'

    def handle(self, *args, **kwargs):
        # 1. Administrador
        admin_group, _ = Group.objects.get_or_create(name='Administrador')
        # Asignar todos los permisos disponibles en el sistema
        admin_group.permissions.set(Permission.objects.all())
        self.stdout.write(self.style.SUCCESS('✅ Grupo Administrador creado/actualizado con acceso total.'))

        # 2. Recepcionista
        recep_group, _ = Group.objects.get_or_create(name='Recepcionista')
        # Apps permitidas para Recepcionista (sin reportes ni configuración de admin/auth)
        apps_recepcion = ['hotel', 'huespedes', 'reservas', 'estancias']
        permisos_recepcion = Permission.objects.filter(content_type__app_label__in=apps_recepcion)
        recep_group.permissions.set(permisos_recepcion)
        self.stdout.write(self.style.SUCCESS('✅ Grupo Recepcionista creado/actualizado con acceso a módulos operativos.'))

        # 3. Housekeeping
        house_group, _ = Group.objects.get_or_create(name='Housekeeping')
        # Solo puede ver y cambiar el estado de las habitaciones (asumimos modelo habitacion en app hotel)
        permisos_housekeeping = Permission.objects.filter(
            content_type__app_label='hotel',
            codename__in=['view_habitacion', 'change_habitacion']
        )
        house_group.permissions.set(permisos_housekeeping)
        self.stdout.write(self.style.SUCCESS('✅ Grupo Housekeeping creado/actualizado con acceso restringido.'))

        self.stdout.write(self.style.SUCCESS('\n🎉 ¡Todos los grupos y permisos han sido configurados correctamente!'))
