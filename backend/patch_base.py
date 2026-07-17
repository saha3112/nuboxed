with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'r') as f:
    content = f.read()

script_block = """
<script>
document.addEventListener("submit", function(e) {
    let form = e.target;
    if (form.classList.contains("ajax-wishlist-form")) {
        e.preventDefault();
        
        let url = form.getAttribute("action");
        let btn = form.querySelector("button[type='submit']");
        let icon = btn.querySelector("i.fa-heart");
        let formData = new FormData(form);
        
        fetch(url, {
            method: "POST",
            body: formData,
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Toggle Icon State
                if (data.added) {
                    if (icon) {
                        icon.classList.remove("fa-regular");
                        icon.classList.add("fa-solid", "in-wishlist");
                        icon.style.color = "#ef4444";
                    }
                } else {
                    if (icon) {
                        icon.classList.remove("fa-solid", "in-wishlist");
                        icon.classList.add("fa-regular");
                        icon.style.color = "";
                        
                        // If we are on compare page, reset border/color properly if needed
                        if(btn.style.borderColor === 'rgb(239, 68, 68)' || btn.style.borderColor === '#ef4444') {
                            btn.style.color = '#94a3b8';
                            btn.style.borderColor = '#e2e8f0';
                        }
                    }
                }
                
                // Update header wishlist counters globally
                let wishlistBadges = document.querySelectorAll("a[href*='wishlist'] b, a[href*='wishlist'] .badge, a[href*='wishlist'] .count");
                wishlistBadges.forEach(badge => {
                    badge.innerText = data.wishlist_count;
                });
            }
        });
    }
});
</script>
</body>
"""

if "</body>" in content and "ajax-wishlist-form" not in content:
    content = content.replace("</body>", script_block)
    with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'w') as f:
        f.write(content)
    print("Successfully added wishlist ajax script to base.html")
else:
    print("Script already present or </body> not found.")
