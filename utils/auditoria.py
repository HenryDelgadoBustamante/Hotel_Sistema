from reportes.models import registrar_auditoria

def log_action(user, accion, registro_id=None, tabla_afectada=None, **extra):
    """Convenient wrapper that forwards to registrar_auditoria.
    Handles None user and merges extra kwargs into observation.
    """
    observacion = extra.get('observacion')
    if extra:
        extra_str = ", ".join(f"{k}={v}" for k, v in extra.items() if k != 'observacion')
        observacion = f"{observacion or ''} {extra_str}".strip()
    return registrar_auditoria(
        usuario=user,
        accion=accion,
        registro_id=registro_id,
        tabla_afectada=tabla_afectada,
        observacion=observacion or None,
    )
