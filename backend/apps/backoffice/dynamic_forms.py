import csv
import io
import json
import zipfile
from datetime import date
from html import escape

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from apps.cms.models import DynamicForm, DynamicFormField, DynamicFormSubmission
from apps.backoffice.views import SuperAdminRequiredMixin
from apps.common.captcha import public_captcha_settings, verify_captcha


def _active_fields(form):
    return form.fields.filter(is_active=True, deleted_at__isnull=True).order_by("sort_order", "created_at")


def _submission_filter_values(request):
    return request.GET.get("q", "").strip(), request.GET.get("date_from", "").strip(), request.GET.get("date_to", "").strip()


def _filter_submissions(queryset, request):
    query, date_from, date_to = _submission_filter_values(request)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    return queryset, query, date_from, date_to


def _download(name, content, content_type):
    return HttpResponse(content, content_type=content_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _simple_docx(headers, values):
    rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{escape(str(value))}</w:t></w:r></w:p></w:tc>" for value in row) + "</w:tr>" for row in [headers] + values)
    document = f"<?xml version='1.0' encoding='UTF-8'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:tbl>{rows}</w:tbl><w:sectPr/></w:body></w:document>"
    content_types = "<?xml version='1.0' encoding='UTF-8'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>"
    rels = "<?xml version='1.0' encoding='UTF-8'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/></Relationships>"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types); archive.writestr("_rels/.rels", rels); archive.writestr("word/document.xml", document)
    return out.getvalue()


class DynamicFormListView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/dynamic_forms/list.html"

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        show = self.request.GET.get("show", "active")
        qs = DynamicForm.objects.all().order_by("-created_at")
        if show == "deleted": qs = qs.filter(deleted_at__isnull=False)
        elif show != "all": qs = qs.filter(deleted_at__isnull=True)
        c.update({"forms": qs, "show": show, "sidebar_groups": self.sidebar_groups, "active_group": "Storefront Content", "page_title": "Dynamic Forms"})
        return c

    @property
    def sidebar_groups(self):
        from apps.backoffice.registry import grouped_modules
        return grouped_modules()


class DynamicFormEditView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/dynamic_forms/builder.html"

    def get_object(self):
        return get_object_or_404(DynamicForm, pk=self.kwargs.get("pk"))

    def get_context(self, form, field=None):
        from apps.backoffice.registry import grouped_modules
        return {"dynamic_form": form, "fields": form.fields.order_by("sort_order", "created_at"), "editing_field": field, "sidebar_groups": grouped_modules(), "active_group": "Storefront Content", "page_title": form.name}

    def get(self, request, *args, **kwargs):
        form = self.get_object()
        field = DynamicFormField.objects.filter(pk=request.GET.get("field"), form=form).first() if request.GET.get("field") else None
        return render(request, self.template_name, self.get_context(form, field))

    def post(self, request, *args, **kwargs):
        form = self.get_object()
        action = request.POST.get("action", "settings")
        if action == "settings":
            form.name = request.POST.get("name", "").strip() or form.name
            form.slug = request.POST.get("slug", "").strip() or form.slug
            form.description = request.POST.get("description", "")
            form.submit_button_text = request.POST.get("submit_button_text", "Submit")
            form.submit_button_alignment = request.POST.get("submit_button_alignment", "left")
            form.success_message = request.POST.get("success_message", "")
            form.error_message = request.POST.get("error_message", "")
            form.show_heading = request.POST.get("show_heading") == "on"
            form.captcha_enabled = request.POST.get("captcha_enabled") == "on"
            form.field_gap = max(0, min(int(request.POST.get("field_gap") or 18), 80))
            form.is_published = request.POST.get("is_published") == "on"
            form.save()
            messages.success(request, "Form settings saved.")
        elif action == "field":
            field_id = request.POST.get("field_id")
            field = DynamicFormField.objects.filter(pk=field_id, form=form).first() if field_id else DynamicFormField(form=form)
            field.label = request.POST.get("label", "").strip() or "Untitled field"
            field.key = request.POST.get("key", "").strip().lower().replace(" ", "-") or f"field-{form.fields.count()+1}"
            field.field_type = request.POST.get("field_type", "text")
            field.placeholder = request.POST.get("placeholder", "")
            field.help_text = request.POST.get("help_text", "")
            field.options = [x.strip() for x in request.POST.get("options", "").splitlines() if x.strip()]
            field.default_value = request.POST.get("default_value", "")
            field.required = request.POST.get("required") == "on"
            field.show_label = request.POST.get("show_label") == "on"
            field.alignment = request.POST.get("alignment", "left")
            field.date_minimum = request.POST.get("date_minimum", "").strip() if field.field_type == "date" else ""
            field.date_maximum = request.POST.get("date_maximum", "").strip() if field.field_type == "date" else ""
            field.date_block_weekends = request.POST.get("date_block_weekends") == "on" if field.field_type == "date" else False
            field.date_specific_dates = [x.strip() for x in request.POST.get("date_specific_dates", "").splitlines() if x.strip()] if field.field_type == "date" else []
            field.sort_order = int(request.POST.get("sort_order") or 0)
            field.deleted_at = None
            field.is_active = True
            field.save()
            messages.success(request, "Field saved.")
        return redirect("backoffice:dynamic-form-edit", pk=form.pk)


class DynamicFormNewView(SuperAdminRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        from apps.backoffice.registry import grouped_modules
        return render(request, "backoffice/dynamic_forms/new.html", {"sidebar_groups": grouped_modules(), "active_group": "Storefront Content", "page_title": "Add New Form"})

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name", "New form").strip() or "New form"
        slug = request.POST.get("slug", "").strip() or name.lower().replace(" ", "-")
        base, suffix = slug, 2
        while DynamicForm.objects.filter(slug=slug).exists(): slug = f"{base}-{suffix}"; suffix += 1
        form = DynamicForm.objects.create(name=name, slug=slug)
        return redirect("backoffice:dynamic-form-edit", pk=form.pk)


class DynamicFormTrashView(SuperAdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if kwargs.get("action") == "bulk-delete":
            ids = request.POST.getlist("form_ids")
            count = DynamicForm.objects.filter(pk__in=ids, deleted_at__isnull=True).update(deleted_at=timezone.now(), is_active=False)
            messages.success(request, f"{count} form(s) moved to trash.")
            return redirect("backoffice:dynamic-forms")
        form = get_object_or_404(DynamicForm, pk=kwargs["pk"])
        action = kwargs["action"]
        if action == "delete":
            form.deleted_at = timezone.now(); form.is_active = False; form.save(update_fields=["deleted_at", "is_active", "updated_at"])
            messages.success(request, f"{form.name} moved to trash.")
        elif action == "restore":
            form.deleted_at = None; form.is_active = True; form.save(update_fields=["deleted_at", "is_active", "updated_at"])
            messages.success(request, f"{form.name} restored successfully.")
        elif action == "permanent":
            name = form.name; form.delete(); messages.success(request, f"{name} permanently deleted.")
        return redirect("backoffice:dynamic-forms")


class DynamicFormFieldTrashView(SuperAdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        field = get_object_or_404(DynamicFormField, pk=kwargs["field_pk"], form_id=kwargs["pk"])
        action = kwargs["action"]
        if action == "delete": field.deleted_at = timezone.now(); field.is_active = False; field.save(update_fields=["deleted_at", "is_active", "updated_at"]); messages.success(request, f"{field.label} moved to trash.")
        elif action == "restore": field.deleted_at = None; field.is_active = True; field.save(update_fields=["deleted_at", "is_active", "updated_at"]); messages.success(request, f"{field.label} restored successfully.")
        elif action == "permanent": name = field.label; field.delete(); messages.success(request, f"{name} permanently deleted.")
        return redirect("backoffice:dynamic-form-edit", pk=kwargs["pk"])


class DynamicFormSubmissionsView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/dynamic_forms/submissions.html"

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        form = get_object_or_404(DynamicForm, pk=kwargs["pk"])
        fields = list(_active_fields(form)); submissions, query, date_from, date_to = _filter_submissions(form.submissions.filter(deleted_at__isnull=True), self.request)
        rows = [{"submission": row, "values": [", ".join(row.data.get(field.key, [])) if isinstance(row.data.get(field.key), list) else row.data.get(field.key, "") for field in fields]} for row in submissions]
        if query:
            rows = [row for row in rows if query.lower() in " ".join(str(value) for value in row["values"]).lower()]
        submission_title = "Forms Lead Data" if form.slug == "footer-newsletter-subscription" else f"{form.name} submissions"
        c.update({"dynamic_form": form, "fields": fields, "submissions": submissions, "rows": rows, "query": query, "date_from": date_from, "date_to": date_to, "submission_title": submission_title, "sidebar_groups": __import__("apps.backoffice.registry", fromlist=["grouped_modules"]).grouped_modules(), "active_group": "Storefront Content", "page_title": submission_title})
        return c

    def post(self, request, *args, **kwargs):
        form = get_object_or_404(DynamicForm, pk=kwargs["pk"])
        ids = request.POST.getlist("submission_ids")
        action = request.POST.get("submission_action", "delete")
        qs = form.submissions.filter(pk__in=ids)
        if action == "permanent": qs.delete()
        else: qs.update(deleted_at=timezone.now(), is_active=False)
        return redirect("backoffice:dynamic-form-submissions", pk=form.pk)


class DynamicFormExportView(SuperAdminRequiredMixin, View):
    def get(self, request, pk, file_format):
        form = get_object_or_404(DynamicForm, pk=pk); fields = list(_active_fields(form)); filtered, query, date_from, date_to = _filter_submissions(form.submissions.filter(deleted_at__isnull=True), request); rows = list(filtered)
        if query:
            rows = [row for row in rows if query.lower() in " ".join(str(value) for value in row.data.values()).lower()]
        headers = ["Submitted at"] + [f.label for f in fields]
        values = [[timezone.localtime(row.created_at).strftime("%Y-%m-%d %H:%M:%S")] + [", ".join(row.data.get(f.key, [])) if isinstance(row.data.get(f.key), list) else str(row.data.get(f.key, "")) for f in fields] for row in rows]
        if file_format == "csv":
            out = io.StringIO(); writer = csv.writer(out); writer.writerow(headers); writer.writerows(values)
            return _download(f"{form.slug}-submissions.csv", out.getvalue(), "text/csv")
        if file_format == "xls":
            table = "<table><tr>" + "".join(f"<th>{escape(h)}</th>" for h in headers) + "</tr>" + "".join("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in row) + "</tr>" for row in values) + "</table>"
            return _download(f"{form.slug}-submissions.xls", f"<html><meta charset='utf-8'><body>{table}</body></html>", "application/vnd.ms-excel")
        if file_format == "docx":
            return _download(f"{form.slug}-submissions.docx", _simple_docx(headers, values), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        if file_format == "pdf":
            lines = [" | ".join(headers)] + [" | ".join(map(str, row)) for row in values]
            stream = "BT /F1 8 Tf 40 780 Td " + " ".join(f"({str(line).replace('(', '[').replace(')', ']')}) Tj 0 -14 Td" for line in lines[:48]) + " ET"
            pdf = "%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R>>endobj\n2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1>>endobj\n3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources<< /Font<< /F1 4 0 R>>>> /Contents 5 0 R>>endobj\n4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica>>endobj\n5 0 obj<< /Length " + str(len(stream.encode())) + " >>stream\n" + stream + "\nendstream endobj\ntrailer<< /Root 1 0 R>>\n%%EOF"
            return _download(f"{form.slug}-submissions.pdf", pdf, "application/pdf")
        text = "\n".join(["\t".join(headers)] + ["\t".join(map(str, row)) for row in values])
        content_type, ext = ("application/msword", "doc") if file_format == "doc" else ("text/plain", "txt")
        return HttpResponse(text, content_type=content_type, headers={"Content-Disposition": f'attachment; filename="{form.slug}-submissions.{ext}"'})


class DynamicFormPublicView(View):
    def get(self, request, slug):
        form = get_object_or_404(DynamicForm, slug=slug, is_published=True, is_active=True, deleted_at__isnull=True)
        return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form)})

    def post(self, request, slug):
        form = get_object_or_404(DynamicForm, slug=slug, is_published=True, is_active=True, deleted_at__isnull=True)
        valid, captcha_error = verify_captcha(request, "public_forms", enabled_override=form.captcha_enabled)
        if not valid:
            return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "error": captcha_error})
        data = {}
        for field in _active_fields(form):
            value = request.POST.getlist(field.key) if field.field_type == "checkbox" else request.POST.get(field.key, "")
            if field.field_type == "file": value = request.FILES.get(field.key).name if request.FILES.get(field.key) else ""
            if field.required and not value: return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "error": form.error_message})
            if field.field_type == "date" and value:
                try:
                    selected_date = date.fromisoformat(value)
                except ValueError:
                    return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "error": "Please choose a valid date."})
                if selected_date < timezone.localdate():
                    return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "error": "Previous dates are not available."})
                if field.date_minimum and value < field.date_minimum:
                    return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "error": "Please choose a date within the available range."})
                if field.date_maximum and value > field.date_maximum:
                    return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "error": "Please choose a date within the available range."})
                if field.date_block_weekends and selected_date.weekday() > 4:
                    return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "error": "Weekend dates are not available."})
                allowed_dates = [item for item in (field.date_specific_dates or []) if item]
                if allowed_dates and value not in allowed_dates:
                    return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "error": "Please choose one of the available dates."})
            data[field.key] = value
        DynamicFormSubmission.objects.create(form=form, data=data, submitted_by=request.user if request.user.is_authenticated else None, ip_address=request.META.get("REMOTE_ADDR"), user_agent=request.META.get("HTTP_USER_AGENT", ""))
        return render(request, "storefront/dynamic_form.html", {"dynamic_form": form, "fields": _active_fields(form), "success": form.success_message})
