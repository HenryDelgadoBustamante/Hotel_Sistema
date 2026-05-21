# Clases de permisos personalizados (EsAdmin, EsRecepcionista, etc.)
from rest_framework.permissions import BasePermission


class EsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            request.user.groups.filter(name='admin').exists()
        )


class EsRecepcionista(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            request.user.groups.filter(name__in=['admin', 'recepcionista']).exists()
        )


class EsHousekeeping(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            request.user.groups.filter(name__in=['admin', 'housekeeping']).exists()
        )


class EsRecepcionistaOHousekeeping(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            request.user.groups.filter(
                name__in=['admin', 'recepcionista', 'housekeeping']
            ).exists()
        )
