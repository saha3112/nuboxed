with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'r') as f:
    content = f.read()

import re

# Remove the old script block
content = re.sub(r'<script>\s*document\.addEventListener\("submit", function\(e\) {.*?ajax-wishlist-form.*?</script>', '', content, flags=re.DOTALL)

new_script = """
<script>
function flyToIcon(imgElement, targetSelector) {
    if(!imgElement) return;
    let target = document.querySelector(targetSelector);
    if(!target) return;
    
    let clone = imgElement.cloneNode(true);
    let rect = imgElement.getBoundingClientRect();
    let targetRect = target.getBoundingClientRect();
    
    clone.style.position = 'fixed';
    clone.style.top = rect.top + 'px';
    clone.style.left = rect.left + 'px';
    clone.style.width = rect.width + 'px';
    clone.style.height = rect.height + 'px';
    clone.style.zIndex = '9999';
    clone.style.transition = 'all 0.8s cubic-bezier(0.25, 1, 0.5, 1)';
    clone.style.opacity = '1';
    clone.style.borderRadius = '50%';
    clone.style.objectFit = 'cover';
    
    document.body.appendChild(clone);
    
    setTimeout(() => {
        clone.style.top = (targetRect.top + targetRect.height/2 - 10) + 'px';
        clone.style.left = (targetRect.left + targetRect.width/2 - 10) + 'px';
        clone.style.width = '20px';
        clone.style.height = '20px';
        clone.style.opacity = '0.5';
    }, 10);
    
    setTimeout(() => {
        clone.remove();
        // target bounce effect
        target.style.transform = 'scale(1.2)';
        target.style.transition = 'transform 0.2s';
        setTimeout(() => target.style.transform = 'scale(1)', 200);
    }, 800);
}

document.addEventListener("submit", function(e) {
    let form = e.target;
    
    if (form.classList.contains("ajax-wishlist-form") || 
        form.classList.contains("ajax-compare-form") || 
        form.classList.contains("ajax-cart-form")) {
        e.preventDefault();
        
        let url = form.getAttribute("action");
        let btn = form.querySelector("button[type='submit']");
        let formData = new FormData(form);
        
        let isWishlist = form.classList.contains("ajax-wishlist-form");
        let isCompare = form.classList.contains("ajax-compare-form");
        let isCart = form.classList.contains("ajax-cart-form");
        
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
                // Find image to fly
                let container = form.closest("td") || form.closest(".product-card") || form.closest(".product-media") || form.closest(".product-details-container");
                let img = container ? container.querySelector("img") : null;
                
                if (isWishlist) {
                    let icon = btn.querySelector("i.fa-heart");
                    if (data.added) {
                        if(icon) {
                            icon.classList.remove("fa-regular");
                            icon.classList.add("fa-solid", "in-wishlist");
                            icon.style.color = "#ef4444";
                        }
                        flyToIcon(img, "a[href*='wishlist']");
                    } else {
                        if(icon) {
                            icon.classList.remove("fa-solid", "in-wishlist");
                            icon.classList.add("fa-regular");
                            icon.style.color = "";
                            if(btn.style.borderColor === 'rgb(239, 68, 68)' || btn.style.borderColor === '#ef4444') {
                                btn.style.color = '#94a3b8';
                                btn.style.borderColor = '#e2e8f0';
                            }
                        }
                    }
                    document.querySelectorAll("a[href*='wishlist'] b, a[href*='wishlist'] .badge, a[href*='wishlist'] .count").forEach(b => b.innerText = data.wishlist_count);
                }
                
                else if (isCompare) {
                    let icon = btn.querySelector("i.fa-right-left");
                    if (data.added) {
                        if(icon) {
                            icon.classList.add("in-compare");
                            icon.style.color = "var(--primary, #0f766e)";
                        }
                        flyToIcon(img, "a[href*='compare']");
                    } else {
                        if(icon) {
                            icon.classList.remove("in-compare");
                            icon.style.color = "";
                        }
                    }
                    document.querySelectorAll("a[href*='compare'] b, a[href*='compare'] .badge, a[href*='compare'] .count").forEach(b => b.innerText = data.compare_count);
                }
                
                else if (isCart) {
                    flyToIcon(img, "a[href*='cart']");
                    document.querySelectorAll("a[href*='cart'] b, a[href*='cart'] .badge, a[href*='cart'] .count").forEach(b => b.innerText = data.cart_count);
                    // maybe show a quick checkmark on button
                    let oldHtml = btn.innerHTML;
                    btn.innerHTML = '<i class="fa-solid fa-check"></i> Added';
                    btn.style.background = '#059669';
                    btn.style.color = '#fff';
                    setTimeout(() => {
                        btn.innerHTML = oldHtml;
                        btn.style.background = '';
                        btn.style.color = '';
                    }, 2000);
                }
            } else {
                alert(data.message || "An error occurred.");
            }
        });
    }
});
</script>
</body>
"""

content = content.replace("</body>", new_script)

with open('/usr/local/var/www/Nuboxed/backend/templates/storefront/base.html', 'w') as f:
    f.write(content)

print("Script updated.")
