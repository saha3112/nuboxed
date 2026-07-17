from django.test import TestCase
from django.urls import reverse

from apps.notifications.models import Notification
from apps.users.models import User


class BackofficeDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            password="safe-password",
        )
        self.client.force_login(self.user)

    def test_dashboard_uses_live_counts_and_queues(self):
        response = self.client.get(reverse("backoffice:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dashboard_cards"][0]["label"], "Active Retailers")
        self.assertEqual(len(response.context["performance_chart_series"]), 7)
        self.assertNotIn("+8%", response.content.decode())

    def test_notifications_are_loaded_from_notification_records(self):
        Notification.objects.create(
            user=self.user,
            channel=Notification.STATUS_PENDING,
            subject="Catalog review required",
            body="One product is awaiting review.",
        )

        response = self.client.get(reverse("backoffice:notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Catalog review required")
        self.assertEqual(response.context["backoffice_unread_notification_count"], 1)
