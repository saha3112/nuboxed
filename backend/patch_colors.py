import re

with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'r') as f:
    content = f.read()

header_start = content.find('<header class="site-header">')
header_end = content.find('</header>') + len('</header>')
style_start = content.find('.header-shell-custom')

if header_start != -1 and header_end != -1 and style_start != -1:
    # 1. Change color in style block for .main-nav > a
    content = content.replace('color: #fff !important;', 'color: #111 !important;')
    
    # 2. Change all color: #fff; to color: #111; inside the new header HTML block (except for buttons or elements that might need white, but wait, I only added color: #fff to location and actions, so it should be fine).
    # To be safe, I'll extract the header HTML and replace `color: #fff;` with `color: #111;`
    header_html = content[header_start:header_end]
    header_html = header_html.replace('color: #fff;', 'color: #111;')
    
    content = content[:header_start] + header_html + content[header_end:]
    
    with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'w') as f:
        f.write(content)
    print("Colors patched successfully.")
else:
    print("Could not find boundaries.")

