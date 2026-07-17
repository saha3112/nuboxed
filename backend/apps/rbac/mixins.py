class AccountScopeMixin:
    account_lookup_kwarg = "account_id"
    account_field = "account_id"

    def get_permission_account(self, request):
        account_id = (
            self.kwargs.get(self.account_lookup_kwarg)
            or request.query_params.get(self.account_lookup_kwarg)
            or request.data.get(self.account_lookup_kwarg)
        )
        if not account_id:
            return None
        return account_id

    def filter_queryset_by_account_scope(self, queryset):
        user = self.request.user
        if user.is_super_admin:
            return queryset
        account_ids = user.get_accessible_account_ids()
        return queryset.filter(**{f"{self.account_field}__in": account_ids})


class CustomerScopeMixin:
    customer_field = "customer_id"

    def filter_queryset_by_customer_scope(self, queryset):
        user = self.request.user
        if user.is_super_admin:
            return queryset
        return queryset.filter(**{self.customer_field: user.id})
