from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.db import transaction


class Command(BaseCommand):
    help = 'Consolida y sincroniza los roles y permisos del sistema hotelero'

    def handle(self, *args, **kwargs):
        canon_roles = {
            'admin': 'ALL',
            'recepcionista': 'OPERATIVE',
            'housekeeping': 'HOUSEKEEPING'
        }
        
        role_synonyms = {
            'admin': ['admin', 'administrador', 'administradores'],
            'recepcionista': ['recepcionista', 'recepcionistas'],
            'housekeeping': ['housekeeping']
        }

        with transaction.atomic():
            self.stdout.write('Iniciando sincronización de roles...')

            for canon_name, role_type in canon_roles.items():
                self.stdout.write(f'\nProcesando rol canónico: {canon_name}')
                
                # 1. Obtener o crear grupo canónico
                canon_group, created = Group.objects.get_or_create(name=canon_name)
                if created:
                    self.stdout.write(f'  [OK] Creado grupo canónico "{canon_name}"')

                # 2. Buscar variantes (búsqueda insensible a mayúsculas/minúsculas de sinónimos)
                from django.db.models import Q
                synonyms = role_synonyms.get(canon_name, [canon_name])
                query = Q()
                for syn in synonyms:
                    query |= Q(name__iexact=syn)
                variants = Group.objects.filter(query).exclude(id=canon_group.id)
                
                for variant in variants:
                    self.stdout.write(f'  -> Integrando variante encontrada: "{variant.name}"')
                    
                    # Transferir usuarios
                    users_to_move = list(variant.user_set.all())
                    if users_to_move:
                        for user in users_to_move:
                            user.groups.add(canon_group)
                            self.stdout.write(f'    - Usuario "{user.username}" movido a "{canon_name}"')
                    
                    # Transferir permisos
                    perms_to_move = list(variant.permissions.all())
                    if perms_to_move:
                        canon_group.permissions.add(*perms_to_move)
                        self.stdout.write(f'    - {len(perms_to_move)} permisos transferidos a "{canon_name}"')
                    
                    # Eliminar la variante
                    variant_name = variant.name
                    variant.delete()
                    self.stdout.write(f'    - Grupo variante "{variant_name}" eliminado.')

                # 3. Asignación explícita de permisos canónicos
                if role_type == 'ALL':
                    all_permissions = Permission.objects.all()
                    canon_group.permissions.set(all_permissions)
                    self.stdout.write(f'  [OK] Asignados todos los permisos ({all_permissions.count()}) a "{canon_name}"')
                
                elif role_type == 'OPERATIVE':
                    # Apps operativas para Recepcionista sin reportes ni configuración de admin/auth, y sin privilegios de eliminación
                    apps_recepcion = ['hotel', 'huespedes', 'reservas', 'estancias']
                    permisos_recepcion = Permission.objects.filter(
                        content_type__app_label__in=apps_recepcion
                    ).exclude(
                        codename__startswith='delete_'
                    )
                    canon_group.permissions.set(permisos_recepcion)
                    self.stdout.write(f'  [OK] Asignados permisos de atención al cliente (sin eliminación) a "{canon_name}" ({permisos_recepcion.count()} permisos)')
                
                elif role_type == 'HOUSEKEEPING':
                    # Permisos limitados a visualización y cambio de estado de habitaciones
                    permisos_housekeeping = Permission.objects.filter(
                        content_type__app_label='hotel',
                        codename__in=['view_habitacion', 'change_habitacion']
                    )
                    canon_group.permissions.set(permisos_housekeeping)
                    self.stdout.write(f'  [OK] Asignados permisos de limpieza de habitaciones a "{canon_name}"')

            # 4. Asegurar que los usuarios de prueba tengan asignados los grupos en minúsculas correctos
            from django.contrib.auth.models import User
            # rcp -> recepcionista
            rcp_user = User.objects.filter(username__iexact='rcp').first()
            if rcp_user:
                recep_group = Group.objects.get(name='recepcionista')
                rcp_user.groups.add(recep_group)
                self.stdout.write('  [OK] Asegurado que el usuario "rcp" pertenece al grupo "recepcionista"')

            self.stdout.write(self.style.SUCCESS('\n[SUCCESS] Sincronización y consolidación de roles completada con éxito.'))
