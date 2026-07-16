# Nombres de roles oficiales (canónicos)
ROL_ADMIN = 'admin'
ROL_RECEPCIONISTA = 'recepcionista'
ROL_HOUSEKEEPING = 'housekeeping'

def pertenece_a_grupo(user, group_name):
    """Comprueba si el usuario pertenece al grupo dado, de forma insensible a mayúsculas/minúsculas."""
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name__iexact=group_name).exists()

def es_admin(user):
    """Retorna True si el usuario es superusuario o pertenece al grupo de administradores."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or pertenece_a_grupo(user, ROL_ADMIN)

def es_recepcionista(user):
    """Retorna True si el usuario es administrador o pertenece al grupo de recepcionistas."""
    if not user or not user.is_authenticated:
        return False
    return es_admin(user) or pertenece_a_grupo(user, ROL_RECEPCIONISTA)

def es_housekeeping(user):
    """Retorna True si el usuario es administrador o pertenece al grupo de housekeeping."""
    if not user or not user.is_authenticated:
        return False
    return es_admin(user) or pertenece_a_grupo(user, ROL_HOUSEKEEPING)

def solo_housekeeping(user):
    """Retorna True si el usuario pertenece al grupo de housekeeping y no es administrador ni recepcionista."""
    if not user or not user.is_authenticated:
        return False
    return (
        pertenece_a_grupo(user, ROL_HOUSEKEEPING)
        and not user.is_superuser
        and not pertenece_a_grupo(user, ROL_ADMIN)
        and not pertenece_a_grupo(user, ROL_RECEPCIONISTA)
    )
