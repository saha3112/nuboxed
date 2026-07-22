from django.db import migrations


def create_contact_support_form(apps, schema_editor):
    DynamicForm = apps.get_model("cms", "DynamicForm")
    DynamicFormField = apps.get_model("cms", "DynamicFormField")

    form, _ = DynamicForm.objects.get_or_create(
        slug="contact-support-enquiries",
        defaults={
            "name": "Contact Support Enquiries",
            "description": "Collect customer support, order, product and partnership enquiries from the Contact page.",
            "submit_button_text": "Send message",
            "success_message": "Thanks! Your enquiry has been received.",
            "error_message": "Please complete the required fields and try again.",
            "show_heading": True,
            "field_gap": 18,
            "is_published": True,
        },
    )

    fields = [
        ("full-name", "Full name", "text", "Enter your name", True, [], 1),
        ("email", "Email address", "email", "you@example.com", True, [], 2),
        ("phone", "Phone number", "phone", "+91 00000 00000", False, [], 3),
        (
            "enquiry-type",
            "Enquiry type",
            "select",
            "Select a topic",
            True,
            ["Order support", "Return or refund", "Product enquiry", "Business partnership", "Technical support"],
            4,
        ),
        ("order-number", "Order number", "text", "Example: NBX-2026-00124", False, [], 5),
        ("message", "How can we help?", "textarea", "Tell us what happened and what assistance you need...", True, [], 6),
    ]
    for key, label, field_type, placeholder, required, options, sort_order in fields:
        DynamicFormField.objects.get_or_create(
            form=form,
            key=key,
            defaults={
                "label": label,
                "field_type": field_type,
                "placeholder": placeholder,
                "required": required,
                "show_label": True,
                "options": options,
                "sort_order": sort_order,
            },
        )


def remove_contact_support_form(apps, schema_editor):
    DynamicForm = apps.get_model("cms", "DynamicForm")
    DynamicForm.objects.filter(slug="contact-support-enquiries").delete()


class Migration(migrations.Migration):
    dependencies = [("cms", "0025_seed_footer_newsletter_form")]
    operations = [migrations.RunPython(create_contact_support_form, remove_contact_support_form)]
