def dynamic_forms_navigation(request):
    """Expose published/active form links to the shared backoffice sidebar."""
    try:
        from apps.cms.models import DynamicForm
        forms = DynamicForm.objects.filter(is_active=True, deleted_at__isnull=True).order_by("name")
    except Exception:
        forms = []
    return {"backoffice_dynamic_forms": forms}
