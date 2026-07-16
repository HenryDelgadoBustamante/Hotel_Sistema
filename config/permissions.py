# Clases de permisos personalizados (EsAdmin, EsRecepcionista, etc.)
from rest_framework.permissions import BasePermission
from config import roles


class EsAdmin(BasePermission):
    def has_permission(self, request, view):
        return roles.es_admin(request.user)


class EsRecepcionista(BasePermission):
    def has_permission(self, request, view):
        return roles.es_recepcionista(request.user)


class EsHousekeeping(BasePermission):
    def has_permission(self, request, view):
        return roles.es_housekeeping(request.user)


class EsRecepcionistaOHousekeeping(BasePermission):
    def has_permission(self, request, view):
        return (
            roles.es_recepcionista(request.user) or
            roles.es_housekeeping(request.user)
        )

