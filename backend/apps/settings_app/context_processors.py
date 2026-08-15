from apps.settings_app.models import BrandSettings, MenuItem, PageText, SiteLogo, SocialLink, MegaMenuSettings, StorefrontLocationMessages, Setting
from apps.common.captcha import public_captcha_settings
from django.core.cache import cache

def global_brand_settings(request):
    """Reuse the request-independent storefront settings for a short period."""
    cached = cache.get("global-brand-settings-context-v2")
    if cached is not None:
        return cached
    context = _build_global_brand_settings(request)
    cache.set("global-brand-settings-context-v2", context, 60)
    return context


def _build_global_brand_settings(request):
    settings = BrandSettings.objects.filter(is_active=True).first()
    footer_setting = Setting.objects.filter(key="footer_customization", is_active=True).values_list("value", flat=True).first() or {}
    contact_defaults = {
        "hero_eyebrow": "We are here to help", "hero_title": "Let’s start a conversation.",
        "hero_description": "Questions about an order, product, partnership or your Nuboxed account? Reach the right team and receive clear, friendly support.",
        "info_heading": "Contact information", "info_description": "Choose the fastest channel for your enquiry. Our team will guide you from there.",
        "form_heading": "Send us a message", "form_description": "Share a few details and the appropriate Nuboxed specialist will contact you.",
        "submit_text": "Send message", "form_note": "By submitting, you agree to our privacy policy and contact terms.",
        "support_eyebrow": "Quick assistance", "support_heading": "Find the right support faster", "support_description": "Use one of these dedicated support paths for common ecommerce enquiries.",
        "support_1_title": "Orders & delivery", "support_1_text": "Track your shipment, update delivery details or report an issue with an order.",
        "support_2_title": "Returns & refunds", "support_2_text": "Start a return, check refund status or understand our return eligibility policy.",
        "support_3_title": "Business enquiries", "support_3_text": "Connect with us about retail partnerships, marketplace selling or corporate orders.",
        "faq_eyebrow": "FAQ", "faq_heading": "Before you contact us", "faq_description": "Answers to a few common questions that may save you time.",
        "brand_color": "#e04420", "dark_color": "#5b241b", "icon_color": "#e04420", "heading_weight": "800", "heading_underline": "none", "body_font_size": "16",
        "hero_text_color": "#ffffff", "info_text_color": "#ffffff", "form_text_color": "#111827", "support_text_color": "#111827", "faq_text_color": "#111827",
        "hero_font": "Inter", "info_font": "Inter", "form_font": "Inter", "support_font": "Inter", "faq_font": "Inter",
        "info_icon": "fa-solid fa-envelope", "info_phone_icon": "fa-solid fa-phone", "info_location_icon": "fa-solid fa-location-dot", "support_icon_1": "fa-solid fa-box", "support_icon_2": "fa-solid fa-rotate-left", "support_icon_3": "fa-solid fa-handshake",
        "info_icon_svg": "", "info_icon_image": "", "support_icon_svg_1": "", "support_icon_svg_2": "", "support_icon_svg_3": "", "support_icon_image_1": "", "support_icon_image_2": "", "support_icon_image_3": "",
        "page_bg_color": "#f6f7fb", "hero_bg_mode": "gradient", "hero_bg_color": "#111827", "hero_bg_image": "", "hero_bg_opacity": "72", "hero_bg_blend": "normal", "card_bg_color": "#ffffff", "map_bg_image": "",
        "info_bg_mode": "gradient", "info_bg_color": "#e04420", "info_bg_gradient_color": "#b9381d", "info_bg_image": "", "form_bg_color": "#ffffff", "form_bg_image": "", "support_bg_color": "#ffffff", "support_bg_image": "", "faq_bg_color": "#ffffff", "faq_bg_image": "",
        "faq_items": [
            {"question": "How quickly will I receive a response?", "answer": "Most messages receive a response within two business hours during support hours. Complex order or payment cases may require additional verification."},
            {"question": "What information should I include?", "answer": "Include your order number, registered email or phone number, and a clear description of the issue."},
            {"question": "Can I contact you about a partnership?", "answer": "Yes. Select Business partnership in the form or email business@nuboxed.com so the enquiry reaches the appropriate team."},
        ],
        "hero_eyebrow_color": "#ffffff", "hero_eyebrow_font": "Inter", "hero_eyebrow_size": "12", "hero_title_color": "#ffffff", "hero_title_font": "Manrope", "hero_title_size": "72", "hero_description_color": "#d0d5dd", "hero_description_font": "Inter", "hero_description_size": "18",
        "info_heading_color": "#ffffff", "info_heading_font": "Manrope", "info_heading_size": "30", "info_description_color": "#e7e5ff", "info_description_font": "Inter", "info_description_size": "16", "form_heading_color": "#111827", "form_heading_font": "Manrope", "form_heading_size": "30", "form_description_color": "#667085", "form_description_font": "Inter", "form_description_size": "16",
        "support_eyebrow_color": "#e04420", "support_eyebrow_font": "Inter", "support_eyebrow_size": "12", "support_heading_color": "#111827", "support_heading_font": "Manrope", "support_heading_size": "46", "support_description_color": "#667085", "support_description_font": "Inter", "support_description_size": "16", "support_card_title_color": "#111827", "support_card_title_font": "Manrope", "support_card_title_size": "19", "support_card_text_color": "#667085", "support_card_text_font": "Inter", "support_card_text_size": "14",
        "faq_eyebrow_color": "#e04420", "faq_eyebrow_font": "Inter", "faq_eyebrow_size": "12", "faq_heading_color": "#111827", "faq_heading_font": "Manrope", "faq_heading_size": "46", "faq_description_color": "#667085", "faq_description_font": "Inter", "faq_description_size": "16", "faq_question_color": "#111827", "faq_question_font": "Inter", "faq_question_size": "16", "faq_answer_color": "#667085", "faq_answer_font": "Inter", "faq_answer_size": "16",
    }
    contact_setting = Setting.objects.filter(key="contact_page_customization", is_active=True).values_list("value", flat=True).first() or {}
    contact_defaults.update(contact_setting)
    if contact_defaults.get("info_bg_color") == "#5b4df7":
        contact_defaults["info_bg_color"] = "#e04420"
    if contact_defaults.get("info_bg_gradient_color") == "#4338ca":
        contact_defaults["info_bg_gradient_color"] = "#b9381d"
    product_page_defaults = {
        "visit_store_prefix": "Visit the", "reviews_label": "Reviews", "highlight_1": "Verified product data from Nuboxed", "highlight_2": "Store-aware delivery estimate and seller comparison", "highlight_3": "Shop confidently from verified retailers.", "sale_countdown": "Hurry up! Sale ends in:", "delivery_label": "Est. Delivery Time", "add_to_cart": "ADD TO CART", "buy_now": "BUY NOW", "add_wishlist": "Add to Wishlist", "add_compare": "Add to Compare", "share_label": "Share", "policy_1": "Free Shipping & Returns: Available on all orders over $99.", "policy_2": "Estimated Delivery: Orders are typically dispatched within 24 hours.", "policy_3": "Security Policy: Ensuring top-level security for your data and transactions.", "description_tab": "Description", "details_tab": "Product Details", "description_heading": "Its much more than mobile product", "description_fallback": "Shop the most popular featured products.", "description_note": "Your trusted marketplace page, wired to admin product data and structured for fast comparison, clear pricing, and clean buying actions.", "specifications_heading": "PRODUCT DETAILS", "related_heading": "You might also like", "category_heading_suffix": "in the same category:", "comments_heading": "Comments", "grade_label": "Grade", "write_review": "WRITE YOUR REVIEW", "view_all_comments": "View all comments", "customer_voice": "Customer voice", "all_comments": "All comments", "review_modal_heading": "Write your review", "review_title_label": "Title", "review_name_label": "Your name", "review_text_label": "Review", "review_terms": "I agree to the terms and the privacy policy", "required_note": "* Required fields", "cancel_button": "CANCEL", "send_button": "SEND", "review_success": "Thank you. Your review has been submitted successfully.",
        "quick_brand_fallback": "Store", "quick_delivery": "Est. Delivery Time 2-3 Days", "quick_reviews": "Reviews", "quick_point_1": "Verified product data from Nuboxed", "quick_point_2": "Store-aware delivery estimate and seller comparison", "quick_ram_label": "RAM:", "quick_storage_label": "Internal Storage:", "quick_color_label": "Color:", "quick_add_to_cart": "ADD TO CART", "quick_buy_now": "BUY NOW", "quick_wishlist": "Add to Wishlist", "quick_compare": "Add to Compare", "quick_stock": "Available Stock", "quick_share": "Share", "quick_save_prefix": "Save",
    }
    product_page_defaults.setdefault("show_sale_countdown", "1")
    product_page_setting = Setting.objects.filter(key="product_page_customization", is_active=True).values_list("value", flat=True).first() or {}
    product_page_defaults.update(product_page_setting)
    # Storefront pricing is EUR-focused; never expose the legacy dollar
    # threshold when an older saved customization still contains it.
    product_page_defaults["policy_1"] = product_page_defaults.get("policy_1", "").replace("$99", "€99")
    product_page_defaults.setdefault("show_share_icons", "1")
    product_page_defaults.setdefault("share_platforms", ["facebook", "x", "linkedin", "pinterest", "email"])
    site_logo = SiteLogo.objects.filter(is_active=True).order_by("-updated_at").first()
    return {
        "global_brand_settings": settings,
        "global_footer_settings": footer_setting,
        "contact_page_settings": contact_defaults,
        "product_page_settings": product_page_defaults,
        "global_site_logo": site_logo,
        "global_menu_items": MenuItem.objects.filter(is_active=True, parent__isnull=True).prefetch_related("children").order_by("sort_order", "title"),
        "storefront_page_texts": {page.key: page for page in PageText.objects.filter(is_active=True)},
        "storefront_location_messages": StorefrontLocationMessages.objects.filter(is_active=True).first(),
        "global_social_links": SocialLink.objects.filter(is_active=True).order_by("sort_order", "platform"),
        "global_mega_menu_settings": MegaMenuSettings.objects.first(),
        "captcha_customer_login": public_captcha_settings("customer_login"),
        "captcha_customer_register": public_captcha_settings("customer_register"),
        "captcha_retailer_login": public_captcha_settings("retailer_login"),
        "captcha_admin_login": public_captcha_settings("admin_login"),
        "captcha_public_forms": public_captcha_settings("public_forms"),
    }
