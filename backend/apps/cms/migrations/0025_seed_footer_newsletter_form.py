from django.db import migrations


def create_footer_newsletter_form(apps, schema_editor):
    DynamicForm = apps.get_model("cms", "DynamicForm")
    DynamicFormField = apps.get_model("cms", "DynamicFormField")

    form, _ = DynamicForm.objects.get_or_create(
        slug="footer-newsletter-subscription",
        defaults={
            "name": "Footer Newsletter Subscription",
            "description": "Collect customer email addresses from the storefront footer.",
            "submit_button_text": "Subscribe",
            "success_message": "You are subscribed. Thanks for joining us!",
            "error_message": "Please enter a valid email address.",
            "show_heading": False,
            "is_published": False,
        },
    )
    DynamicFormField.objects.get_or_create(
        form=form,
        key="email",
        defaults={
            "label": "Email address",
            "field_type": "email",
            "placeholder": "Enter your email address",
            "help_text": "We will only use this address for newsletter updates.",
            "required": True,
            "show_label": False,
            "sort_order": 1,
        },
    )


def remove_footer_newsletter_form(apps, schema_editor):
    DynamicForm = apps.get_model("cms", "DynamicForm")
    DynamicForm.objects.filter(slug="footer-newsletter-subscription").delete()


class Migration(migrations.Migration):
    dependencies = [("cms", "0024_dynamicform_field_gap")]

    operations = [migrations.RunPython(create_footer_newsletter_form, remove_footer_newsletter_form)]
