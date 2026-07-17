from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.http import HttpResponse, JsonResponse
from huespedes.models import Huesped
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from config.views_shared import _es_admin, _es_recepcionista, _acceso_denegado


@login_required
def huespedes_lista(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    query = request.GET.get('q', '')
    huespedes = Huesped.objects.all().order_by('-created_at')
    if query:
        huespedes = huespedes.filter(
            Q(nombres__icontains=query) |
            Q(apellidos__icontains=query) |
            Q(num_doc__icontains=query)
        )
    return render(request, 'huespedes/lista.html', {'huespedes': huespedes, 'query': query})


@login_required
def huesped_nuevo(request):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    if request.method == 'POST':
        try:
            huesped = Huesped.objects.create(
                tipo_doc=request.POST['tipo_doc'],
                num_doc=request.POST['num_doc'],
                nombres=request.POST['nombres'],
                apellidos=request.POST['apellidos'],
                email=request.POST.get('email') or None,
                telefono=request.POST.get('telefono') or None,
                nacionalidad=request.POST.get('nacionalidad', 'Peruana'),
            )
            messages.success(request, 'Huésped registrado correctamente.')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                separator = '&' if '?' in next_url else '?'
                return redirect(f'{next_url}{separator}huesped={huesped.id}')
            return redirect('huespedes_lista')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    return render(request, 'huespedes/form.html', {
        'next': next_url,
        'initial_query': request.GET.get('q', ''),
    })


@login_required
def huesped_editar(request, huesped_id):
    if not _es_recepcionista(request.user):
        return _acceso_denegado(request)
    huesped = get_object_or_404(Huesped, id=huesped_id)
    if request.method == 'POST':
        try:
            huesped.tipo_doc = request.POST['tipo_doc']
            huesped.num_doc = request.POST['num_doc']
            huesped.nombres = request.POST['nombres']
            huesped.apellidos = request.POST['apellidos']
            huesped.email = request.POST.get('email') or None
            huesped.telefono = request.POST.get('telefono') or None
            huesped.nacionalidad = request.POST.get('nacionalidad', 'Peruana')
            huesped.save()
            messages.success(request, 'Huésped actualizado correctamente.')
            return redirect('huespedes_lista')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    return render(request, 'huespedes/form.html', {
        'huesped': huesped,
        'initial_query': '',
        'next': '',
    })


@login_required
def exportar_huespedes_excel(request):
    if not _es_admin(request.user):
        return _acceso_denegado(request, 'Solo los administradores pueden exportar datos.')
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse
    from huespedes.models import Huesped
    from django.db.models import Count, Sum
    
    huespedes = Huesped.objects.annotate(
        total_estancias=Count('reservas__estancia', distinct=True),
        total_pagado=Sum('reservas__estancia__folio__pagos__monto')
    ).order_by('id')
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Huéspedes"
    
    headers = ["#", "Nombre completo", "DNI", "Teléfono", "Email", "Fecha de registro", "Total estancias", "Total pagado"]
    ws.append(headers)
    
    header_font = Font(color="FFFFFF", bold=True)
    header_fill = PatternFill(start_color="1E2433", end_color="1E2433", fill_type="solid")
    
    for col_num, cell in enumerate(ws[1], 1):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    for h in huespedes:
        fecha_reg = h.created_at.strftime('%Y-%m-%d') if hasattr(h, 'created_at') and h.created_at else "N/A"
        total_p = h.total_pagado or 0.0
        ws.append([
            h.id,
            f"{h.nombres} {h.apellidos}",
            h.num_doc,
            h.telefono or "-",
            h.email or "-",
            fecha_reg,
            h.total_estancias,
            float(total_p)
        ])
        
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[col_letter].width = (max_length + 2)
        
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="huespedes_hotelsystem.xlsx"'
    wb.save(response)
    return response


@login_required
def api_buscar_huesped(request):
    """API para buscar huésped registrado en la BD local por documento o nombre."""
    from django.http import JsonResponse
    from huespedes.models import Huesped
    q = request.GET.get('q', '').strip()
    if not q or len(q) < 2:
        return JsonResponse({'results': []})
    from django.db.models import Q
    huespedes = Huesped.objects.filter(
        Q(num_doc__icontains=q) |
        Q(nombres__icontains=q) |
        Q(apellidos__icontains=q)
    ).order_by('apellidos', 'nombres')[:10]
    results = []
    for h in huespedes:
        results.append({
            'id': h.id,
            'num_doc': h.num_doc,
            'tipo_doc': h.tipo_doc,
            'nombres': h.nombres,
            'apellidos': h.apellidos,
            'nombre_completo': f'{h.nombres} {h.apellidos}',
            'telefono': h.telefono or '',
            'email': h.email or '',
            'nacionalidad': h.nacionalidad,
        })
    return JsonResponse({'results': results})


@login_required
def api_consulta_dni(request):
    from django.http import JsonResponse
    numero = request.GET.get('numero')
    if not numero or len(numero) != 8:
        return JsonResponse({'error': 'DNI inválido'}, status=400)
    
    try:
        import urllib.request, json
        req = urllib.request.Request(f'https://api.apis.net.pe/v1/dni?numero={numero}', headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
