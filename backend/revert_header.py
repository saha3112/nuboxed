import re

with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'r') as f:
    content = f.read()

# The start of the patched section is <style> just before <header class="site-header">
style_start = content.find('<style>\n    .header-shell-custom {')
header_end = content.find('</header>') + len('</header>')

if style_start != -1 and header_end != -1:
    original_header = """<header class="site-header">
        <div class="header-shell">
            <a href="{% url 'storefront:home' %}" class="logo-mark">
                {% if global_site_logo and global_site_logo.logo_image %}
                    <img src="{{ global_site_logo.logo_image.url }}" alt="{{ global_site_logo.alt_text|default:'Nuboxed' }}" class="site-logo-image">
                {% else %}
                    <img src="{% static 'storefront/images/logo.webp' %}" alt="Nuboxed" class="site-logo-image">
                {% endif %}
            </a>

            <div class="live-search-container header-search">
                <form action="{% url 'storefront:products' %}" method="get" class="search-shell">
                    <input type="search" name="q" id="live-search-input" placeholder="Search product here...">
                    <button type="submit" aria-label="Search"><i class="fa-solid fa-magnifying-glass"></i></button>
                </form>
                <div id="live-search-results"></div>
            </div>
            <a href="javascript:void(0)" onclick="document.getElementById('locationModal').style.display='flex'" class="header-support location-picker-btn" style="padding: 5px 8px; border: 1px solid transparent; border-radius: 2px; transition: all 0.2s; margin-left: auto; color: #000;">
                <div style="display: flex; align-items: flex-end; gap: 4px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 2px;"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
                    <div style="display: flex; flex-direction: column; align-items: flex-start; line-height: 1.1;">
                        <span style="font-size: 11px; color: #000; font-weight: 400; text-transform: none; white-space: nowrap; display: block;">Delivering to <span id="loc-city" style="display: inline;"></span> <span id="loc-pin" style="display: inline;"></span></span>
                        <strong style="font-size: 14px; font-weight: 700; color: #000; white-space: nowrap; display: block;">Update location</strong>
                    </div>
                </div>
            </a>
        </div>
        <div class="nav-shell">
            <nav class="main-nav" id="main-nav">
                <a href="{% url 'storefront:home' %}">Home</a>
                {% for menu_item in global_menu_items %}
                    {% if menu_item.title|lower == "store" or menu_item.title|lower == "stores" %}
                        <div class="nav-dropdown mega-dropdown-sm">
                            <a href="{{ menu_item.url }}" class="nav-button">{{ menu_item.title }} <i class="fa-solid fa-chevron-down"></i></a>
                            <div class="mega-menu-wrapper sm">
                                <div class="mega-menu-column">
                                    <h4>Our Stores</h4>
                                    <ul class="mega-menu-list">
                                    {% for store in nav_store_links %}
                                        <li><a href="{% url 'storefront:store-detail' slug=store.slug %}">{{ store.name }}</a></li>
                                    {% empty %}
                                        <li><span>No stores yet</span></li>
                                    {% endfor %}
                                    </ul>
                                </div>
                                <div class="mega-menu-column mega-promo">
                                    <span>{{ global_mega_menu_settings.promo_subtitle|default:"SPECIAL OFFER" }}</span>
                                    <h3>{{ global_mega_menu_settings.promo_title|default:"Visit Our Stores" }}</h3>
                                    <p>{{ global_mega_menu_settings.promo_description|default:"Find the best deals at a store near you." }}</p>
                                    <a href="{% url 'storefront:stores' %}" class="btn">{{ global_mega_menu_settings.promo_button_text|default:"VIEW ALL" }}</a>
                                </div>
                            </div>
                        </div>
                    {% elif menu_item.title|lower == "products" or menu_item.title|lower == "product" %}
                        <div class="nav-dropdown mega-dropdown">
                            <a href="{{ menu_item.url }}" class="nav-button">{{ menu_item.title }} <i class="fa-solid fa-chevron-down"></i></a>
                            <div class="mega-menu-wrapper">
                                {% for device in nav_device_categories %}
                                    <div class="mega-menu-column">
                                        <h4>{{ device.name }}</h4>
                                        <ul class="mega-menu-list">
                                        {% for brand in device.children.all %}
                                            <li>
                                                <a href="{% url 'storefront:category' slug=brand.slug %}">{{ brand.name }}</a>
                                                {% if brand.children.all %}
                                                    <ul class="mega-menu-sublist">
                                                    {% for model in brand.children.all %}
                                                        <li><a href="{% url 'storefront:category' slug=model.slug %}">{{ model.name }}</a></li>
                                                    {% endfor %}
                                                    </ul>
                                                {% endif %}
                                            </li>
                                        {% endfor %}
                                        </ul>
                                    </div>
                                {% empty %}
                                    <div class="mega-menu-column">
                                        <h4>Products</h4>
                                        <ul class="mega-menu-list">
                                            <li><a href="{% url 'storefront:products' %}">All Products</a></li>
                                        </ul>
                                    </div>
                                {% endfor %}
                            </div>
                        </div>
                    {% else %}
                        <a href="{{ menu_item.url }}">{{ menu_item.title }}</a>
                    {% endif %}
                {% empty %}
                    <div class="nav-dropdown mega-dropdown-sm">
                        <a href="{% url 'storefront:stores' %}" class="nav-button">Store <i class="fa-solid fa-chevron-down"></i></a>
                        <div class="mega-menu-wrapper sm">
                            <div class="mega-menu-column">
                                <h4>Our Stores</h4>
                                <ul class="mega-menu-list">
                                {% for store in nav_store_links %}
                                    <li><a href="{% url 'storefront:store-detail' slug=store.slug %}">{{ store.name }}</a></li>
                                {% empty %}
                                    <li><span>No stores yet</span></li>
                                {% endfor %}
                                </ul>
                            </div>
                            <div class="mega-menu-column mega-promo">
                                <span>{{ global_mega_menu_settings.promo_subtitle|default:"SPECIAL OFFER" }}</span>
                                <h3>{{ global_mega_menu_settings.promo_title|default:"Visit Our Stores" }}</h3>
                                <p>{{ global_mega_menu_settings.promo_description|default:"Find the best deals at a store near you." }}</p>
                                <a href="{% url 'storefront:stores' %}" class="btn">{{ global_mega_menu_settings.promo_button_text|default:"VIEW ALL" }}</a>
                            </div>
                        </div>
                    </div>
                    <div class="nav-dropdown mega-dropdown">
                        <a href="{% url 'storefront:products' %}" class="nav-button">Products <i class="fa-solid fa-chevron-down"></i></a>
                        <div class="mega-menu-wrapper">
                            {% for device in nav_device_categories %}
                                <div class="mega-menu-column">
                                    <h4>{{ device.name }}</h4>
                                    <ul class="mega-menu-list">
                                    {% for brand in device.children.all %}
                                        <li>
                                            <a href="{% url 'storefront:category' slug=brand.slug %}">{{ brand.name }}</a>
                                            {% if brand.children.all %}
                                                <ul class="mega-menu-sublist">
                                                {% for model in brand.children.all %}
                                                    <li><a href="{% url 'storefront:category' slug=model.slug %}">{{ model.name }}</a></li>
                                                {% endfor %}
                                                </ul>
                                            {% endif %}
                                        </li>
                                    {% endfor %}
                                    </ul>
                                </div>
                            {% empty %}
                                <div class="mega-menu-column">
                                    <h4>Products</h4>
                                    <ul class="mega-menu-list">
                                        <li><a href="{% url 'storefront:products' %}">All Products</a></li>
                                    </ul>
                                </div>
                            {% endfor %}
                        </div>
                    </div>
                    <a href="{% url 'storefront:products' %}">Top Deals</a>
                    <a href="{% url 'storefront:contact' %}">Contact</a>
                {% endfor %}
            </nav>
            <div class="header-actions" style="display: flex; gap: 20px; align-items: center; margin-left: auto; justify-content: flex-end; color: #fff;">
                <a href="{% if user.is_authenticated %}{% url 'storefront:customer-dashboard' %}{% else %}{% url 'storefront:login' %}{% endif %}" class="header-support icon-stack" style="color: #fff;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 2px;"><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>
                    <span style="color: #fff;">Returns & Orders</span>
                </a>
                <div class="nav-dropdown">
                    <a href="{% if user.is_authenticated and not user.is_staff and not user.is_superuser %}{% url 'storefront:customer-dashboard' %}{% else %}{% url 'storefront:login' %}{% endif %}" class="header-support icon-stack" style="color: #fff;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 2px;"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        <span style="color: #fff;">Account <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="display:inline; margin-left: 2px;"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
                    </a>
                    <div class="dropdown-panel amazon-account-dropdown">
                        <div class="dropdown-signin-header">
                            <a href="{% url 'storefront:login' %}" class="btn-signin-yellow">Sign in</a>
                            <p class="new-customer-text">New customer? <a href="{% url 'storefront:register' %}">Start here.</a></p>
                        </div>
                        <div class="dropdown-columns" style="display: block;">
                            <div class="dropdown-col account-col" style="padding-left: 0;">
                                <h3>Your Account</h3>
                                <ul class="dropdown-list amazon-list" style="list-style: none; padding: 0; margin: 0;">
                                    <li><a href="{% if user.is_authenticated %}{% url 'storefront:customer-dashboard' %}{% else %}{% url 'storefront:login' %}{% endif %}">Your Account</a></li>
                                    <li><a href="{% if user.is_authenticated %}{% url 'storefront:customer-dashboard' %}{% else %}{% url 'storefront:login' %}{% endif %}">Your Orders</a></li>
                                    <li><a href="{% url 'storefront:wishlist' %}">Your Wish List</a></li>
                                    {% if user.is_authenticated and not user.is_staff and not user.is_superuser %}
                                    <li>
                                        <form action="{% url 'storefront:logout' %}" method="post" style="display:inline; margin:0; padding:0;">
                                            {% csrf_token %}
                                            <button type="submit" style="background: transparent; border: 0; padding: 0; cursor: pointer; font: inherit; text-align: left; color: #111;">Logout</button>
                                        </form>
                                    </li>
                                    {% endif %}
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
                <a href="{% url 'storefront:compare' %}" class="header-support icon-stack" style="color: #fff;">
                    <div class="cart-icon" style="position: relative;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 2px;"><path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/></svg>
                        <b>{{ nav_compare_count|default:"0" }}</b>
                    </div>
                    <span style="color: #fff;">Compare</span>
                </a>
                <a href="{% url 'storefront:wishlist' %}" class="header-support icon-stack" style="color: #fff;">
                    <div style="position: relative;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 2px;"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>
                        {% if nav_wishlist_count > 0 %}<b>{{ nav_wishlist_count }}</b>{% endif %}
                    </div>
                    <span style="color: #fff;">Wishlist</span>
                </a>
                <a href="{% url 'storefront:cart' %}" class="header-support cart-total icon-stack" data-cart-drawer-toggle style="color: #fff;">
                    <div style="position: relative;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 2px;"><circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/></svg>
                        <b>{{ nav_cart_count|default:"0" }}</b>
                    </div>
                    <span style="color: #fff;">My Cart</span>
                </a>
            </div>
            <button class="mobile-nav-toggle" type="button" data-toggle-nav><i class="fa-solid fa-bars"></i> Menu</button>
        </div>
    </header>"""

    new_content = content[:style_start] + original_header + content[header_end:]
    
    with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'w') as f:
        f.write(new_content)
    print("Successfully reverted to original header.")
else:
    print("Could not find boundaries to revert.")

