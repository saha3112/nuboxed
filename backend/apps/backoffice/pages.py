from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.backoffice.registry import grouped_modules
from apps.backoffice.views import SuperAdminRequiredMixin
from apps.cms.models import Page


def _context(**extra):
    return {"sidebar_groups": grouped_modules(), "active_group": "Page Settings", "page_title": "Pages", **extra}


class PageListView(SuperAdminRequiredMixin, View):
    def get(self, request):
        show = request.GET.get("show", "active")
        pages = Page.objects.all().order_by("title")
        if show == "deleted":
            pages = pages.filter(deleted_at__isnull=False)
        elif show != "all":
            pages = pages.filter(deleted_at__isnull=True)
        return render(request, "backoffice/pages/list.html", _context(pages=pages, show=show))


class PageEditView(SuperAdminRequiredMixin, View):
    def get(self, request, pk=None):
        page = get_object_or_404(Page, pk=pk) if pk else None
        return render(request, "backoffice/pages/edit.html", _context(page=page))

    def post(self, request, pk=None):
        page = get_object_or_404(Page, pk=pk) if pk else Page()
        title = request.POST.get("title", "").strip()
        slug = request.POST.get("slug", "").strip()
        if not title or not slug:
            messages.error(request, "Title and slug are required.")
            return render(request, "backoffice/pages/edit.html", _context(page=page, error="Title and slug are required."))
        page.title, page.slug = title, slug
        page.content = request.POST.get("content", "")
        page.is_published = request.POST.get("is_published") == "on"
        page.deleted_at = None
        page.save()
        messages.success(request, "Page saved successfully.")
        if request.POST.get("save_action") == "stay":
            return redirect("backoffice:page-edit", pk=page.pk)
        return redirect("backoffice:pages")


class PageTrashView(SuperAdminRequiredMixin, View):
    def post(self, request, pk=None, action="delete"):
        ids = request.POST.getlist("page_ids")
        if action == "bulk-delete":
            Page.objects.filter(pk__in=ids, deleted_at__isnull=True).update(deleted_at=timezone.now())
            messages.success(request, "Selected pages moved to trash.")
        else:
            page = get_object_or_404(Page, pk=pk)
            if action == "restore":
                page.deleted_at = None; page.save(update_fields=["deleted_at", "updated_at"]); messages.success(request, "Page restored.")
            elif action == "permanent":
                page.delete(); messages.success(request, "Page permanently deleted.")
            else:
                page.deleted_at = timezone.now(); page.save(update_fields=["deleted_at", "updated_at"]); messages.success(request, "Page moved to trash.")
        return redirect("backoffice:pages")
