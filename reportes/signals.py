import json
from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from reportes.models import Auditoria
from utils.auditoria import log_action

# Cache to hold pre-save state
_PRE_SAVE_CACHE = {}

def _model_is_excluded(model):
    # Exclude audit-related models themselves
    return model.__name__ in ['Auditoria', 'LoginIntento']

@receiver(pre_save)
def audit_pre_save(sender, instance, **kwargs):
    from django.conf import settings
    if getattr(settings, 'TESTING', False) or _model_is_excluded(sender):
        return
    data = {}
    for field in sender._meta.get_fields():
        if field.concrete and not field.many_to_many and not field.one_to_many:
            try:
                value = getattr(instance, field.name)
            except Exception:
                value = None
            # For FK store id
            if field.is_relation and field.many_to_one:
                value = getattr(instance, f"{field.name}_id")
            data[field.name] = value
    # Use pk (may be None for new objects) as key
    _PRE_SAVE_CACHE[id(instance)] = data

@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    from django.conf import settings
    if getattr(settings, 'TESTING', False) or _model_is_excluded(sender):
        return
    old_state = _PRE_SAVE_CACHE.pop(id(instance), {})
    new_state = {}
    for field in sender._meta.get_fields():
        if field.concrete and not field.many_to_many and not field.one_to_many:
            try:
                value = getattr(instance, field.name)
            except Exception:
                value = None
            if field.is_relation and field.many_to_one:
                value = getattr(instance, f"{field.name}_id")
            new_state[field.name] = value
    changed_fields = {k: {'old': old_state.get(k), 'new': v} for k, v in new_state.items() if old_state.get(k) != v}
    action = 'Crear' if created else 'Actualizar'
    observacion = json.dumps(changed_fields, default=str) if changed_fields else None
    # If the primary key is not an integer (e.g., Session keys), omit registro_id
    registro_id = instance.pk if isinstance(instance.pk, int) else None
    log_action(
        user=getattr(instance, 'modificado_por', None) or getattr(instance, 'creado_por', None),
        accion=action,
        registro_id=registro_id,
        tabla_afectada=sender._meta.db_table,
        observacion=observacion,
    )

@receiver(pre_delete)
def audit_pre_delete(sender, instance, **kwargs):
    from django.conf import settings
    if getattr(settings, 'TESTING', False) or _model_is_excluded(sender):
        return
    state = {}
    for field in sender._meta.get_fields():
        if field.concrete and not field.many_to_many and not field.one_to_many:
            try:
                value = getattr(instance, field.name)
            except Exception:
                value = None
            if field.is_relation and field.many_to_one:
                value = getattr(instance, f"{field.name}_id")
            state[field.name] = value
    observacion = json.dumps(state, default=str)
    # Avoid registro_id for non-integer PKs (e.g., Session)
    registro_id = instance.pk if isinstance(instance.pk, int) else None
    log_action(
        user=getattr(instance, 'modificado_por', None) or getattr(instance, 'creado_por', None),
        accion='Eliminar',
        registro_id=registro_id,
        tabla_afectada=sender._meta.db_table,
        observacion=observacion,
    )
