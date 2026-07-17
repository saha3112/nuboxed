import re

with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'r') as f:
    content = f.read()

# Replace the entire <header> block
header_start = content.find('<header class="site-header">')
header_end = content.find('</header>') + len('</header>')

if header_start != -1 and header_end != -1:
    old_header = content[header_start:header_end]
    
    # We will build the new header layout.
    # We need to extract the parts: logo-mark, search-shell, location-picker-btn, main-nav, header-actions, mobile-nav-toggle
    
    logo_match = re.search(r'<a href="{% url \'storefront:home\' %}" class="logo-mark">.*?</a>', old_header, re.DOTALL)
    search_match = re.search(r'<div class="live-search-container header-search">.*?</div>', old_header, re.DOTALL)
    loc_match = re.search(r'<a href="javascript:void\(0\)" onclick="document.getElementById\(\'locationModal\'\)\.style\.display=\'flex\'" class="header-support location-picker-btn".*?</a>', old_header, re.DOTALL)
    nav_match = re.search(r'<nav class="main-nav" id="main-nav">.*?</nav>', old_header, re.DOTALL)
    actions_match = re.search(r'<div class="header-actions".*?</div>\s*<button class="mobile-nav-toggle"', old_header, re.DOTALL)
    toggle_match = re.search(r'<button class="mobile-nav-toggle" type="button" data-toggle-nav><i class="fa-solid fa-bars"></i> Menu</button>', old_header, re.DOTALL)
    
    # Fix loc color to white
    loc_str = loc_match.group(0)
    loc_str = loc_str.replace('color: #000;', 'color: #fff;')
    
    # Extract actions (without the trailing button if it matched)
    actions_str = old_header[old_header.find('<div class="header-actions"'):old_header.find('<button class="mobile-nav-toggle"')]
    
    new_header = f"""<style>
    .header-shell-custom {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
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
        min-width: 200px;
        max-width: 400px;
    }}
    @media (max-width: 1080px) {{
        .header-shell-custom {{
            flex-direction: column;
            align-items: stretch;
        }}
        .header-shell-custom .main-nav {{
            display: none; /* hidden on mobile, toggled by js */
            flex-direction: column;
            width: 100%;
        }}
        .header-shell-custom .live-search-container {{
            max-width: 100%;
            order: 3;
        }}
        .header-top-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
        }}
    }}
</style>
<header class="site-header">
    <div class="header-shell-custom">
        <div class="header-top-row" style="display: flex; align-items: center; gap: 20px;">
            {logo_match.group(0)}
            {loc_str}
        </div>
        
        {nav_match.group(0)}

        {search_match.group(0)}

        <div style="display: flex; align-items: center; gap: 20px;">
            {actions_str}
            {toggle_match.group(0)}
        </div>
    </div>
</header>"""

    new_content = content[:header_start] + new_header + content[header_end:]
    
    with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'w') as f:
        f.write(new_content)
    print("Header patched successfully.")
else:
    print("Could not find header boundaries.")

