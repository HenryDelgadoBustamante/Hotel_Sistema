from django.contrib import admin
from .models import Huesped

@admin.register(Huesped)
class HuespedAdmin(admin.ModelAdmin):
    list_display = ['nombres', 'apellidos', 'tipo_doc', 'num_doc', 'email', 'nacionalidad']
    search_fields = ['nombres', 'apellidos', 'num_doc']
