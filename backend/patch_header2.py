import re

with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'r') as f:
    content = f.read()

header_start = content.find('<header class="site-header">')
header_end = content.find('</header>') + len('</header>')

if header_start != -1 and header_end != -1:
    old_header = content[header_start:header_end]
    
    logo_match = re.search(r'<a href="{% url \'storefront:home\' %}" class="logo-mark">.*?</a>', old_header, re.DOTALL)
    search_match = re.search(r'<div class="live-search-container header-search".*?</div>', old_header, re.DOTALL)
    loc_match = re.search(r'<a href="javascript:void\(0\)" onclick="document.getElementById\(\'locationModal\'\)\.style\.display=\'flex\'" class="header-support location-picker-btn".*?</a>', old_header, re.DOTALL)
    nav_match = re.search(r'<nav class="main-nav" id="main-nav">.*?</nav>', old_header, re.DOTALL)
    actions_match = re.search(r'<div class="header-actions".*?</div>\s*<button class="mobile-nav-toggle"', old_header, re.DOTALL)
    toggle_match = re.search(r'<button class="mobile-nav-toggle"[^>]*>.*?</button>', old_header, re.DOTALL)
    
    actions_str = old_header[old_header.find('<div class="header-actions"'):old_header.find('<button class="mobile-nav-toggle"')]
    loc_str = loc_match.group(0).replace('color: #000;', 'color: #fff;')
    
    # We will build a more robust responsive header.
    # On desktop:
    # Logo | Loc | Menus | Search | Actions
    # On mobile:
    # Logo | Actions & Toggle
    # Search
    
    new_header = f"""<style>
    .header-shell-custom {{
        display: flex;
        align-items: center;
        gap: 15px;
        padding: 15px 0;
        width: min(1630px, calc(100vw - 30px));
        margin: 0 auto;
    }}
    .header-shell-custom .main-nav {{
        display: flex;
        align-items: center;
        gap: 20px;
    }}
    .header-shell-custom .main-nav > a, .header-shell-custom .main-nav .nav-button {{
        color: #fff !important;
        font-weight: 600;
        text-decoration: none;
    }}
    .header-shell-custom .live-search-container {{
        flex: 1;
        min-width: 150px;
        max-width: 400px;
    }}
    .header-shell-custom .header-actions {{
        display: flex;
        gap: 20px;
        align-items: center;
        margin-left: auto;
    }}
    @media (max-width: 1080px) {{
        .header-shell-custom {{
            flex-wrap: wrap;
            justify-content: space-between;
        }}
        .header-shell-custom .main-nav {{
            display: none;
            width: 100%;
            order: 4;
            flex-direction: column;
            align-items: flex-start;
        }}
        .header-shell-custom .live-search-container {{
            order: 3;
            max-width: 100%;
            flex: 0 0 100%;
            margin-top: 10px;
        }}
        .header-shell-custom .logo-mark {{
            order: 1;
        }}
        .header-shell-custom .header-actions-wrap {{
            order: 2;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
    }}
</style>
<header class="site-header">
    <div class="header-shell-custom">
        {logo_match.group(0)}
        {loc_str}
        {nav_match.group(0)}
        {search_match.group(0)}
        <div class="header-actions-wrap" style="display: flex; align-items: center; gap: 20px; margin-left: auto;">
            {actions_str}
            {toggle_match.group(0)}
        </div>
    </div>
</header>"""

    new_content = content[:header_start] + new_header + content[header_end:]
    
    with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'w') as f:
        f.write(new_content)
    print("Header patched successfully (v2).")
else:
    print("Could not find header boundaries.")

