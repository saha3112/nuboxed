const navToggle = document.querySelector("[data-toggle-nav]");
const mainNav = document.getElementById("main-nav");
const deliveryToggle = document.querySelector("[data-toggle-delivery]");
const deliveryPopover = document.getElementById("delivery-popover");
const detectLocationButton = document.querySelector("[data-detect-location]");
const geolocationForm = document.querySelector("[data-geolocation-form]");
const cartDrawer = document.getElementById("cart-drawer");
const cartDrawerOverlay = document.querySelector(".cart-drawer-overlay");
const cartDrawerToggles = document.querySelectorAll("[data-cart-drawer-toggle]");
const cartDrawerClosers = document.querySelectorAll("[data-cart-drawer-close]");
const pageLoader = document.getElementById("page-loader");
const heroCarousel = document.querySelector(".hero-carousel");

function hidePageLoader() {
    if (!pageLoader || pageLoader.dataset.hidden === "1") return;
    pageLoader.classList.add("loaded");
    pageLoader.dataset.hidden = "1";
    setTimeout(() => pageLoader.remove(), 350);
}

window.addEventListener("DOMContentLoaded", hidePageLoader);
window.addEventListener("load", hidePageLoader);
setTimeout(hidePageLoader, 1800);

if (navToggle && mainNav) {
    navToggle.addEventListener("click", () => {
        mainNav.classList.toggle("open");
    });
}

if (deliveryToggle && deliveryPopover) {
    deliveryToggle.addEventListener("click", () => {
        deliveryPopover.classList.toggle("open");
    });

    document.addEventListener("click", (event) => {
        if (!deliveryPopover.contains(event.target) && !deliveryToggle.contains(event.target)) {
            deliveryPopover.classList.remove("open");
        }
    });
}

if (detectLocationButton && geolocationForm && navigator.geolocation) {
    detectLocationButton.addEventListener("click", () => {
        detectLocationButton.disabled = true;
        detectLocationButton.textContent = "Detecting...";
        navigator.geolocation.getCurrentPosition(
            (position) => {
                geolocationForm.querySelector('input[name="latitude"]').value = position.coords.latitude;
                geolocationForm.querySelector('input[name="longitude"]').value = position.coords.longitude;
                geolocationForm.submit();
            },
            () => {
                detectLocationButton.disabled = false;
                detectLocationButton.textContent = "Use current location";
                window.alert("Location detection failed. Enter your pincode manually.");
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
        );
    });
}

function openCartDrawer() {
    if (!cartDrawer) return;
    cartDrawer.classList.add("open");
    cartDrawer.setAttribute("aria-hidden", "false");
    document.body.classList.add("cart-drawer-open");
}

function closeCartDrawer() {
    if (!cartDrawer) return;
    cartDrawer.classList.remove("open");
    cartDrawer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("cart-drawer-open");
}

cartDrawerToggles.forEach((toggle) => {
    toggle.addEventListener("click", (event) => {
        event.preventDefault();
        openCartDrawer();
    });
});

cartDrawerClosers.forEach((closer) => {
    closer.addEventListener("click", closeCartDrawer);
});

if (cartDrawerOverlay) {
    cartDrawerOverlay.addEventListener("click", closeCartDrawer);
}

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        closeCartDrawer();
    }
});

document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest("[data-cart-drawer-close]")) {
        closeCartDrawer();
    }
});

function updateCartBadge(count) {
    const badge = document.querySelector(".header-support.cart-total b");
    if (badge && count !== undefined && count !== null) {
        badge.innerText = count;
    }
}

function setDrawerFormLoading(form, loading) {
    form.querySelectorAll("button").forEach((button) => {
        button.disabled = loading;
    });
    form.classList.toggle("is-loading", loading);
}

function postDrawerForm(form) {
    const formData = new FormData(form);
    setDrawerFormLoading(form, true);

    return fetch(form.action, {
        method: "POST",
        body: formData,
        headers: {
            "X-Requested-With": "XMLHttpRequest"
        }
    })
    .then((response) => {
        if (response.redirected) {
            window.location.href = response.url;
            throw new Error("Redirected");
        }
        return response.json();
    })
    .then((data) => {
        if (!data.success) {
            if (data.message) window.alert(data.message);
            return data;
        }
        updateCartBadge(data.cart_count);
        return refreshCartDrawer().then(() => data);
    })
    .finally(() => {
        setDrawerFormLoading(form, false);
    });
}

document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest("[data-cart-qty-action]");
    if (!button) return;

    const form = button.closest("[data-cart-drawer-qty-form]");
    if (!form) return;

    const input = form.querySelector('input[name="quantity"]');
    const action = button.dataset.cartQtyAction;
    const currentQuantity = Number.parseInt(input.value, 10) || 1;
    const nextQuantity = action === "increase" ? currentQuantity + 1 : currentQuantity - 1;

    if (nextQuantity < 1) return;
    input.value = nextQuantity;

    postDrawerForm(form).catch(() => {
        input.value = currentQuantity;
    });
});

document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.classList.contains("drawer-remove-form")) return;

    event.preventDefault();
    postDrawerForm(form).catch(() => {
        form.submit();
    });
});

document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const dialog = event.target.closest("dialog.quickview-dialog");
    if (dialog && event.target === dialog) {
        dialog.close();
    }
});

if (heroCarousel) {
    const slides = Array.from(heroCarousel.querySelectorAll(".hero-slide"));
    const prevButton = heroCarousel.querySelector("[data-hero-prev]");
    const nextButton = heroCarousel.querySelector("[data-hero-next]");
    const dotsRoot = heroCarousel.querySelector("[data-hero-dots]");
    let activeIndex = Math.max(slides.findIndex((slide) => slide.classList.contains("active")), 0);
    let timer = null;

    const showSlide = (index) => {
        if (!slides.length) return;
        activeIndex = (index + slides.length) % slides.length;
        slides.forEach((slide, slideIndex) => {
            slide.classList.toggle("active", slideIndex === activeIndex);
        });
        if (dotsRoot) {
            Array.from(dotsRoot.children).forEach((dot, dotIndex) => {
                dot.classList.toggle("active", dotIndex === activeIndex);
            });
        }
    };

    const restart = () => {
        if (timer) window.clearInterval(timer);
        if (slides.length > 1) {
            timer = window.setInterval(() => showSlide(activeIndex + 1), 6500);
        }
    };

    if (slides.length < 2) {
        prevButton?.remove();
        nextButton?.remove();
        if (dotsRoot) dotsRoot.remove();
        slides.forEach((slide) => slide.classList.add("active"));
    } else {
        if (dotsRoot) {
            dotsRoot.innerHTML = "";
            slides.forEach((_, index) => {
                const dot = document.createElement("button");
                dot.type = "button";
                dot.className = "hero-dot" + (index === activeIndex ? " active" : "");
                dot.addEventListener("click", () => {
                    showSlide(index);
                    restart();
                });
                dotsRoot.appendChild(dot);
            });
        }

        prevButton?.addEventListener("click", () => {
            showSlide(activeIndex - 1);
            restart();
        });
        nextButton?.addEventListener("click", () => {
            showSlide(activeIndex + 1);
            restart();
        });
        showSlide(activeIndex);
        restart();
    }
}

document.querySelectorAll("[data-filter-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
        const card = button.closest(".filter-card, .facet");
        if (!card) return;
        const collapsed = card.classList.toggle("is-collapsed");
        button.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });
});

const quickModal = document.getElementById("quickModal");
const quickClose = document.getElementById("quickClose");
const quickPhoneImage = document.getElementById("quickPhoneImage");
const quickPhoneFallback = document.getElementById("quickPhoneFallback");
const quickThumbs = document.getElementById("quickThumbs");
const quickThumbPrev = document.getElementById("quickThumbPrev");
const quickThumbNext = document.getElementById("quickThumbNext");
const quickPrev = document.getElementById("quickPrev");
const quickNext = document.getElementById("quickNext");
const quickTitle = document.getElementById("quickTitle");
const quickBrand = document.getElementById("quickBrand");
const quickPrice = document.getElementById("quickPrice");
const quickOldPrice = document.getElementById("quickOldPrice");
const quickSave = document.getElementById("quickSave");
const quickStorageLabel = document.getElementById("quickStorageLabel");
const quickStorageButtons = document.getElementById("quickStorageButtons");
const quickRamLabel = document.getElementById("quickRamLabel");
const quickRamButtons = document.getElementById("quickRamButtons");
const quickColorLabel = document.getElementById("quickColorLabel");
const quickColorButtons = document.getElementById("quickColorButtons");
const quickQty = document.getElementById("quickQty");
const quickAddForm = document.getElementById("quickAddForm");
const quickBuyForm = document.getElementById("quickBuyForm");
const quickAddButton = document.getElementById("quickAdd");
const quickBuyButton = quickBuyForm ? quickBuyForm.querySelector("button[type='submit']") : null;
const quickWishlistForm = document.getElementById("quickWishlistForm");
const quickWishlistButton = document.getElementById("quickWishlist");
const quickStock = document.getElementById("quickStock");
const quickPoints = document.getElementById("quickPoints");

let quickImages = [];
let quickIndex = 0;
let quickThumbOffset = 0;
let activeQuickProductId = null;

function syncQuickQuantity() {
    if (!quickQty) return;
    const max = Number(quickQty.max || 0);
    let value = Math.max(1, Number(quickQty.value || 1));
    if (max > 0) value = Math.min(value, max);
    quickQty.value = String(value);
    [quickAddForm, quickBuyForm].forEach((form) => {
        const input = form?.querySelector('[data-buy-qty]');
        if (input) input.value = String(value);
    });
}

function updateQuickPurchaseState(stock) {
    const qty = Number(stock || 0);
    const disabled = qty <= 0;
    [quickAddButton, quickBuyButton].forEach((button) => {
        if (!button) return;
        button.disabled = disabled;
        button.classList.toggle("disabled", disabled);
    });
    if (quickQty) {
        quickQty.max = String(Math.max(qty, 1));
        syncQuickQuantity();
    }
}

function normalizeQuickOption(value) {
    return (value || "").toLowerCase().replace(/\s+/g, "");
}

function setQuickActiveButton(container, value, datasetKey) {
    if (!container || !value) return;
    const target = normalizeQuickOption(value);
    const buttons = Array.from(container.querySelectorAll("button"));
    const match = buttons.find((button) => normalizeQuickOption(datasetKey ? button.dataset[datasetKey] : button.textContent.trim()) === target);
    if (!match) return;
    buttons.forEach((button) => button.classList.remove("active"));
    match.classList.add("active");
}

function selectFirstAvailableQuickVariant() {
    const variants = window.quickVariants || [];
    const firstAvailable = variants.find((variant) => Number(variant.stock || 0) > 0);
    if (!firstAvailable) return;
    const ram = firstAvailable.attributes.ram || "";
    const storage = firstAvailable.attributes.storage || "";
    const color = firstAvailable.attributes.color || "";
    setQuickActiveButton(quickRamButtons, ram);
    setQuickActiveButton(quickStorageButtons, storage);
    setQuickActiveButton(quickColorButtons, color, "color");
    
    const activeRamBtn = quickRamButtons ? quickRamButtons.querySelector("button.active") : null;
    if (activeRamBtn && quickRamLabel) quickRamLabel.textContent = activeRamBtn.textContent;
    
    const activeStorageBtn = quickStorageButtons ? quickStorageButtons.querySelector("button.active") : null;
    if (activeStorageBtn && quickStorageLabel) quickStorageLabel.textContent = activeStorageBtn.textContent;
    
    const activeColorBtn = quickColorButtons ? quickColorButtons.querySelector("button.active") : null;
    if (activeColorBtn && quickColorLabel) quickColorLabel.textContent = activeColorBtn.dataset.color || activeColorBtn.textContent;
}

function applyQuickOptionStockState(button, attrKey, value) {
    const variants = window.quickVariants || [];
    const optionValue = normalizeQuickOption(value || "");
    const relatedVariants = variants.filter((variant) => normalizeQuickOption(variant.attributes[attrKey] || "") === optionValue);
    const isOutOfStock = relatedVariants.length > 0 && relatedVariants.every((variant) => Number(variant.stock || 0) <= 0);
    button.classList.toggle("out-of-stock", isOutOfStock);
    button.classList.toggle("faded", isOutOfStock);
    button.dataset.stockState = isOutOfStock ? "out" : "in";
    button.setAttribute("aria-disabled", isOutOfStock ? "true" : "false");
}

function renderQuickThumbs() {
    if (!quickThumbs) return;
    quickThumbs.innerHTML = "";
    quickImages.forEach((url, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "quick-thumb" + (index === quickIndex ? " active" : "");
        button.dataset.index = String(index);
        button.innerHTML = `<img src="${url}" alt="">`;
        button.addEventListener("click", () => {
            setQuickImage(index);
        });
        quickThumbs.appendChild(button);
    });
}

function setQuickImage(index) {
    if (!quickImages.length) {
        if (quickPhoneImage) quickPhoneImage.style.display = "none";
        if (quickPhoneFallback) quickPhoneFallback.style.display = "grid";
        return;
    }
    quickIndex = (index + quickImages.length) % quickImages.length;
    const url = quickImages[quickIndex];
    if (quickPhoneImage) {
        quickPhoneImage.src = url;
        quickPhoneImage.style.display = "block";
    }
    if (quickPhoneFallback) quickPhoneFallback.style.display = "none";
    if (quickThumbs) {
        Array.from(quickThumbs.children).forEach((button, idx) => {
            button.classList.toggle("active", idx === quickIndex);
        });
    }
}

function updateQuickSelectedVariant() {
    let activeColor = "";
    let activeStorage = "";
    let activeRam = "";

    const activeColorBtn = quickColorButtons ? quickColorButtons.querySelector("button.active") : null;
    const activeStorageBtn = quickStorageButtons ? quickStorageButtons.querySelector("button.active") : null;
    const activeRamBtn = quickRamButtons ? quickRamButtons.querySelector("button.active") : null;

    if (activeColorBtn) {
        activeColor = normalizeQuickOption(activeColorBtn.dataset.color || "");
    }
    if (activeStorageBtn) {
        activeStorage = normalizeQuickOption(activeStorageBtn.textContent || "");
    }
    if (activeRamBtn) {
        activeRam = normalizeQuickOption(activeRamBtn.textContent || "");
    }

    const variants = window.quickVariants || [];
    const matching = variants.find((v) => {
        const varColor = normalizeQuickOption(v.attributes.color || "");
        const varStorage = normalizeQuickOption(v.attributes.storage || "");
        const varRam = normalizeQuickOption(v.attributes.ram || "");
        return varColor === activeColor && varStorage === activeStorage && varRam === activeRam;
    });

    const hiddenCartVariantId = document.getElementById("quickCartVariantId");
    const hiddenBuyNowVariantId = document.getElementById("quickBuyNowVariantId");

    if (matching) {
        if (hiddenCartVariantId) hiddenCartVariantId.value = matching.id;
        if (hiddenBuyNowVariantId) hiddenBuyNowVariantId.value = matching.id;

        // Update price
        const currency = window.quickCurrency || "USD";
        if (quickPrice && matching.price) {
            quickPrice.textContent = formatMoney(matching.price, currency);
        }
        if (quickOldPrice) {
            if (matching.compare_price) {
                quickOldPrice.textContent = formatMoney(matching.compare_price, currency);
                quickOldPrice.style.display = "inline";
            } else {
                quickOldPrice.style.display = "none";
            }
        }
        if (quickSave) {
            const price = parseFloat(matching.price);
            const compPrice = parseFloat(matching.compare_price);
            if (!isNaN(price) && !isNaN(compPrice) && compPrice > price) {
                const pct = Math.round(((compPrice - price) / compPrice) * 100);
                quickSave.textContent = `Save ${pct}%`;
                quickSave.style.display = "inline-flex";
            } else {
                quickSave.style.display = "none";
            }
        }
        if (quickStock) {
            if (matching.stock > 0) {
                quickStock.innerHTML = '<i class="fa-solid fa-circle-check"></i> Available Stock';
                quickStock.className = "quick-stock success";
            } else {
                quickStock.innerHTML = '<i class="fa-solid fa-circle-xmark"></i> Out of Stock';
                quickStock.className = "quick-stock danger";
            }
        }
        updateQuickPurchaseState(matching.stock);
    } else {
        updateQuickPurchaseState(0);
    }
}

function updateQuickOptionAvailability(changedAttr) {
    let activeColor = "";
    let activeStorage = "";
    let activeRam = "";

    const activeColorBtn = quickColorButtons ? quickColorButtons.querySelector("button.active") : null;
    const activeStorageBtn = quickStorageButtons ? quickStorageButtons.querySelector("button.active") : null;
    const activeRamBtn = quickRamButtons ? quickRamButtons.querySelector("button.active") : null;

    if (activeColorBtn) {
        activeColor = normalizeQuickOption(activeColorBtn.dataset.color || "");
    }
    if (activeStorageBtn) {
        activeStorage = normalizeQuickOption(activeStorageBtn.textContent || "");
    }
    if (activeRamBtn) {
        activeRam = normalizeQuickOption(activeRamBtn.textContent || "");
    }

    const variants = window.quickVariants || [];

    // Auto fallback if combination doesn't exist
    let matching = variants.find(v => {
        const varColor = normalizeQuickOption(v.attributes.color || "");
        const varStorage = normalizeQuickOption(v.attributes.storage || "");
        const varRam = normalizeQuickOption(v.attributes.ram || "");
        return varColor === activeColor && varStorage === activeStorage && varRam === activeRam;
    });

    if (!matching && variants.length > 0) {
        if (changedAttr === "storage" && activeStorage) {
            const fallback = variants.find(v => normalizeQuickOption(v.attributes.storage || "") === activeStorage);
            if (fallback && quickColorButtons) {
                const fallbackColor = normalizeQuickOption(fallback.attributes.color || "");
                Array.from(quickColorButtons.children).forEach(btn => {
                    const btnColor = normalizeQuickOption(btn.dataset.color || "");
                    if (btnColor === fallbackColor) {
                        Array.from(quickColorButtons.children).forEach(b => b.classList.remove("active"));
                        btn.classList.add("active");
                        activeColor = fallbackColor;
                        if (quickColorLabel) quickColorLabel.textContent = btn.dataset.color;
                    }
                });
            }
        } else if (changedAttr === "color" && activeColor) {
            const fallback = variants.find(v => normalizeQuickOption(v.attributes.color || "") === activeColor);
            if (fallback && quickStorageButtons) {
                const fallbackStorage = normalizeQuickOption(fallback.attributes.storage || "");
                Array.from(quickStorageButtons.children).forEach(btn => {
                    const btnStorage = normalizeQuickOption(btn.textContent || "");
                    if (btnStorage === fallbackStorage) {
                        Array.from(quickStorageButtons.children).forEach(b => b.classList.remove("active"));
                        btn.classList.add("active");
                        activeStorage = fallbackStorage;
                        if (quickStorageLabel) quickStorageLabel.textContent = btn.textContent;
                    }
                });
            }
        }
    }

    // Now update button classes (fade and crossed-out/out-of-stock)
    if (quickColorButtons) {
        Array.from(quickColorButtons.children).forEach(btn => {
            const btnVal = normalizeQuickOption(btn.dataset.color || "");
            applyQuickOptionStockState(btn, "color", btnVal);
        });
    }

    if (quickStorageButtons) {
        Array.from(quickStorageButtons.children).forEach(btn => {
            const btnVal = normalizeQuickOption(btn.textContent || "");
            applyQuickOptionStockState(btn, "storage", btnVal);
        });
    }
    if (quickRamButtons) {
        Array.from(quickRamButtons.children).forEach(btn => {
            const btnVal = normalizeQuickOption(btn.textContent || "");
            applyQuickOptionStockState(btn, "ram", btnVal);
        });
    }
}


function renderRamButtons(labels) {
    if (!quickRamButtons) return;
    quickRamButtons.innerHTML = "";
    const titleContainer = document.getElementById("quickRamTitleContainer");
    if (!labels.length) {
        if (titleContainer) titleContainer.style.display = "none";
        quickRamButtons.style.display = "none";
        return;
    }
    if (titleContainer) titleContainer.style.display = "block";
    quickRamButtons.style.display = "flex";
    
    const values = labels;
    values.forEach((label, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.className = "storage";
        applyQuickOptionStockState(button, "ram", label);
        if (index === 0) button.classList.add("active");
        button.addEventListener("click", () => {
            Array.from(quickRamButtons.children).forEach((child) => child.classList.remove("active"));
            button.classList.add("active");
            if (quickRamLabel) quickRamLabel.textContent = label;
            updateQuickOptionAvailability("ram");
            updateQuickSelectedVariant();
        });
        quickRamButtons.appendChild(button);
    });
    if (quickRamLabel) quickRamLabel.textContent = values[0] || "Default";
}

function renderStorageButtons(labels) {
    if (!quickStorageButtons) return;
    quickStorageButtons.innerHTML = "";
    const values = labels.length ? labels : ["Default"];
    values.forEach((label, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.className = "storage";
        applyQuickOptionStockState(button, "storage", label);
        if (index === 0) button.classList.add("active");
        button.addEventListener("click", () => {
            Array.from(quickStorageButtons.children).forEach((child) => child.classList.remove("active"));
            button.classList.add("active");
            if (quickStorageLabel) quickStorageLabel.textContent = label;
            updateQuickOptionAvailability("storage");
            updateQuickSelectedVariant();
        });
        quickStorageButtons.appendChild(button);
    });
    if (quickStorageLabel) quickStorageLabel.textContent = values[0] || "Default";
}

function renderColorButtons(colors) {
    if (!quickColorButtons) return;
    quickColorButtons.innerHTML = "";
    const titleContainer = document.getElementById("quickColorTitleContainer");
    if (!colors.length) {
        if (titleContainer) titleContainer.style.display = "none";
        quickColorButtons.style.display = "none";
        return;
    }
    if (titleContainer) titleContainer.style.display = "block";
    quickColorButtons.style.display = "flex";

    colors.forEach((colorStr, index) => {
        const parts = colorStr.split(":");
        const label = parts[0] || "Color";
        const hex = parts[1] || "#ccc";

        const btn = document.createElement("button");
        btn.type = "button";
        btn.title = label;
        btn.dataset.color = label;
        btn.className = "storage is-color";
        btn.classList.toggle("active", index === 0);
        btn.style.setProperty("--swatch", hex);

        const swatch = document.createElement("span");
        swatch.className = "color-swatch";
        btn.appendChild(swatch);
        applyQuickOptionStockState(btn, "color", label);

        btn.addEventListener("click", () => {
            Array.from(quickColorButtons.children).forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            if (quickColorLabel) quickColorLabel.textContent = label;
            
            if (window.quickImagesColors) {
                const targetColor = label.toLowerCase().trim();
                const matchedIdx = window.quickImagesColors.findIndex(c => (c || '').toLowerCase().trim() === targetColor);
                if (matchedIdx !== -1) {
                    setQuickImage(matchedIdx);
                }
            }
            updateQuickOptionAvailability("color");
            updateQuickSelectedVariant();
        });

        quickColorButtons.appendChild(btn);
    });

    if (quickColorLabel) {
        const parts = colors[0].split(":");
        quickColorLabel.textContent = parts[0] || "Default";
    }
}

function openQuickView(card) {
    if (!quickModal || !card) return;
    activeQuickProductId = card.dataset.productId || null;
    const name = card.dataset.qvName || "Product";
    const brand = card.dataset.qvBrand || "Store";
    const category = card.dataset.qvCategory || "";
    const priceRaw = card.dataset.qvPrice || "";
    const oldPriceRaw = card.dataset.qvOldPrice || "";
    const currency = card.dataset.qvCurrency || "USD";
    const save = card.dataset.qvSave || "";
    const description = card.dataset.qvDescription || "";
    const stock = card.dataset.qvStock || "Available";
    let stockClass = card.dataset.qvStockClass || "success";
    if (stock.toLowerCase().includes("out of stock")) {
        stockClass = "danger";
    }
    const ramLabels = (card.dataset.qvRamLabels || "").split("|").map((item) => item.trim()).filter(Boolean);
    const storageLabels = (card.dataset.qvStorageLabels || "").split("|").map((item) => item.trim()).filter(Boolean);
    const colorLabels = (card.dataset.qvColors || "").split("|").map((item) => item.trim()).filter(Boolean);
    quickImages = (card.dataset.qvImages || "").split("|").map((item) => item.trim()).filter(Boolean);
    quickIndex = 0;
    quickThumbOffset = 0;

    window.quickVariants = JSON.parse(card.dataset.qvVariants || "[]");
    window.quickCurrency = currency;
    window.quickImagesColors = card.dataset.qvImageColors ? card.dataset.qvImageColors.split("|") : [];

    if (quickTitle) quickTitle.textContent = name.toUpperCase();
    if (quickBrand) quickBrand.textContent = brand;
    if (quickPrice) quickPrice.textContent = priceRaw ? formatMoney(priceRaw, currency) : "";
    if (quickOldPrice) {
        quickOldPrice.textContent = oldPriceRaw ? formatMoney(oldPriceRaw, currency) : "";
        quickOldPrice.style.display = oldPriceRaw ? "inline" : "none";
    }
    if (quickSave) {
        quickSave.textContent = save ? `Save ${save}%` : "";
        quickSave.style.display = save ? "inline-flex" : "none";
    }
    if (quickPoints) {
        quickPoints.innerHTML = "";
        if (description) {
            const li = document.createElement("li");
            li.textContent = description;
            quickPoints.appendChild(li);
        }
        ["Verified product data from admin", "Store-aware delivery estimate and seller comparison"].forEach((text) => {
            const li = document.createElement("li");
            li.textContent = text;
            quickPoints.appendChild(li);
        });
    }
    if (quickStock) {
        const stockIcon = stockClass === "danger" ? "fa-circle-xmark" : "fa-circle-check";
        quickStock.innerHTML = `<i class="fa-solid ${stockIcon}"></i> ${stock}`;
        quickStock.className = `quick-stock ${stockClass}`;
    }
    renderRamButtons(ramLabels);
    renderStorageButtons(storageLabels);
    renderColorButtons(colorLabels);
    selectFirstAvailableQuickVariant();
    renderQuickThumbs();
    setQuickImage(0);

    updateQuickOptionAvailability("storage");
    updateQuickSelectedVariant();
    requestAnimationFrame(() => {
        selectFirstAvailableQuickVariant();
        updateQuickOptionAvailability("storage");
        updateQuickSelectedVariant();
    });

    if (quickAddForm) quickAddForm.action = `/cart/add/${activeQuickProductId}/`;
    if (quickBuyForm) quickBuyForm.action = `/buy-now/${activeQuickProductId}/`;
    if (quickWishlistForm) quickWishlistForm.action = `/wishlist/add/${activeQuickProductId}/`;

    syncQuickQuantity();
    quickModal.classList.add("open");
    quickModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("quick-modal-open");
}

function closeQuickView() {
    if (!quickModal) return;
    quickModal.classList.remove("open");
    quickModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("quick-modal-open");
}

function formatMoney(value, currency) {
    const number = Number(value || 0);
    try {
        return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency: currency || "USD",
            maximumFractionDigits: 2,
        }).format(number);
    } catch (error) {
        return `$${number.toFixed(2)}`;
    }
}

document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-open-quickview]");
    if (trigger) {
        const card = trigger.closest(".product-card");
        openQuickView(card);
        return;
    }
    if (event.target === quickModal) {
        closeQuickView();
        return;
    }
    if (event.target.closest("#quickClose")) {
        closeQuickView();
        return;
    }
});

quickQty?.addEventListener("input", syncQuickQuantity);
document.addEventListener("click", (event) => {
    if (event.target.closest("[data-qty-plus]") && quickQty) {
        quickQty.value = String(Math.max(1, Number(quickQty.value || 1) + 1));
        syncQuickQuantity();
    }
    if (event.target.closest("[data-qty-minus]") && quickQty) {
        quickQty.value = String(Math.max(1, Number(quickQty.value || 1) - 1));
        syncQuickQuantity();
    }
    if (event.target.closest("#quickPrev") && quickImages.length) {
        setQuickImage(quickIndex - 1);
    }
    if (event.target.closest("#quickNext") && quickImages.length) {
        setQuickImage(quickIndex + 1);
    }
    if (event.target.closest("#quickThumbPrev") && quickThumbs) {
        quickThumbOffset = Math.max(0, quickThumbOffset - 124);
        quickThumbs.style.transform = `translateX(-${quickThumbOffset}px)`;
    }
    if (event.target.closest("#quickThumbNext") && quickThumbs) {
        quickThumbOffset += 124;
        quickThumbs.style.transform = `translateX(-${quickThumbOffset}px)`;
    }
});

window.addEventListener("resize", () => {
    if (!quickThumbs) return;
    const max = Math.max(0, quickThumbs.scrollWidth - quickThumbs.parentElement.clientWidth);
    quickThumbOffset = Math.min(quickThumbOffset, max);
    quickThumbs.style.transform = `translateX(-${quickThumbOffset}px)`;
});

document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!/\/(cart-add|buy-now)\//.test(form.action)) return;
    const button = form.querySelector('button[type="submit"]');
    if (!button || button.dataset.loadingApplied === "1") return;
    button.dataset.loadingApplied = "1";
    button.classList.add("is-loading");
    button.disabled = true;
    button.dataset.originalHtml = button.innerHTML;
    button.innerHTML = '<span class="btn-spinner"></span><span>Adding</span>';
});

const liveSearchInput = document.getElementById("live-search-input");
const liveSearchResults = document.getElementById("live-search-results");

if (liveSearchInput && liveSearchResults) {
    let debounceTimer;
    liveSearchInput.addEventListener("input", function(e) {
        clearTimeout(debounceTimer);
        const query = e.target.value.trim();
        
        if (query.length < 2) {
            liveSearchResults.style.display = "none";
            return;
        }
        
        debounceTimer = setTimeout(() => {
            let storeParam = "";
            const match = window.location.pathname.match(/^\/stores\/([^\/]+)/);
            if (match) {
                storeParam = `&store=${match[1]}`;
            }
            fetch(`/live-search/?q=${encodeURIComponent(query)}${storeParam}`)
                .then(response => response.json())
                .then(data => {
                    liveSearchResults.innerHTML = "";
                    if (data.results && data.results.length > 0) {
                        data.results.forEach(item => {
                            const link = document.createElement("a");
                            link.href = item.url;
                            link.style.display = "flex";
                            link.style.alignItems = "center";
                            link.style.padding = "10px";
                            link.style.textDecoration = "none";
                            link.style.color = "var(--text)";
                            
                            let imgHtml = item.image_url ? `<img src="${item.image_url}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px; margin-right: 10px;">` : `<div style="width: 40px; height: 40px; background: #eee; border-radius: 4px; margin-right: 10px;"></div>`;
                            
                            let variantsHtml = item.variants ? `<div style="font-size: 11px; color: var(--muted); margin-top: 2px;">${item.variants}</div>` : '';

                            link.innerHTML = `
                                ${imgHtml}
                                <div>
                                    <div style="font-weight: 500; font-size: 13px;">${item.name}</div>
                                    ${variantsHtml}
                                    <div style="font-weight: bold; color: var(--primary); font-size: 12px; margin-top: 2px;">€${item.price}</div>
                                </div>
                            `;
                            liveSearchResults.appendChild(link);
                        });
                        if (data.other_location_msg) {
                            const msgLink = document.createElement("a");
                            msgLink.href = data.other_location_url || `/products/?q=${encodeURIComponent(query)}&ignore_location=1`;
                            msgLink.style.display = "block";
                            msgLink.style.padding = "10px";
                            msgLink.style.textDecoration = "none";
                            msgLink.style.color = "var(--primary)";
                            msgLink.style.fontWeight = "bold";
                            msgLink.style.fontSize = "12px";
                            msgLink.style.textAlign = "center";
                            msgLink.style.borderTop = "1px solid #eee";
                            msgLink.innerText = data.other_location_msg;
                            liveSearchResults.appendChild(msgLink);
                        }
                        liveSearchResults.style.display = "block";
                    } else {
                        liveSearchResults.innerHTML = '<div style="padding: 15px; color: var(--muted); text-align: center;">No results found</div>';
                        if (data.other_location_msg) {
                            const fallbackUrl = data.other_location_url || `/products/?q=${encodeURIComponent(query)}&ignore_location=1`;
                            liveSearchResults.innerHTML += `<a href="${fallbackUrl}" style="display:block; padding: 10px; text-decoration: none; color: var(--primary); font-weight: bold; font-size: 12px; text-align: center; border-top: 1px solid #eee;">${data.other_location_msg}</a>`;
                        }
                        liveSearchResults.style.display = "block";
                    }
                });
        }, 300);
    });
    
    document.addEventListener("click", function(e) {
        if (!liveSearchInput.contains(e.target) && !liveSearchResults.contains(e.target)) {
            liveSearchResults.style.display = "none";
        }
    });
}

function changeCardImage(chip) {
    const imageUrl = chip.dataset.imageUrl;
    if (!imageUrl) return;
    const card = chip.closest(".product-card");
    if (!card) return;
    const mainImg = card.querySelector(".product-main-image");
    if (mainImg) {
        mainImg.src = imageUrl;
    }
}

document.addEventListener("submit", function(e) {
    const form = e.target;
    if (form.classList.contains("ajax-wishlist-form") ||
        form.classList.contains("ajax-compare-form") ||
        form.classList.contains("ajax-cart-form")) {
        return;
    }
    const action = form.getAttribute("action");
    if (action && (action.includes("/cart/add/") || action.includes("/compare/add/") || action.includes("/wishlist/add/"))) {
        e.preventDefault();
        
        const formData = new FormData(form);
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn ? submitBtn.innerHTML : "";
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
        }

        fetch(action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            // Check if redirect, meaning it wasn't intercepted as AJAX correctly (just in case)
            if (response.redirected) {
                window.location.href = response.url;
                throw new Error("Redirected");
            }
            return response.json();
        })
        .then(data => {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
            
            if (data.success) {
                // Update counter based on action
                let targetSelector = "";
                if (action.includes("/cart/add/")) {
                    targetSelector = ".header-support.cart-total b";
                    const b = document.querySelector(targetSelector);
                    if (b) b.innerText = data.cart_count;
                    
                    if (typeof refreshCartDrawer === 'function') {
                        refreshCartDrawer();
                    }
                } else if (action.includes("/compare/add/")) {
                    targetSelector = ".header-support[href*='/compare/'] b";
                    const b = document.querySelector(targetSelector);
                    if (b) b.innerText = data.compare_count;
                    
                    if (submitBtn) {
                        const i = submitBtn.querySelector("i");
                        if (data.added) {
                            submitBtn.classList.add("selected");
                            if (i) {
                                i.classList.add("in-compare");
                                i.style.color = "#ef4444";
                            }
                        } else {
                            submitBtn.classList.remove("selected");
                            if (i) {
                                i.classList.remove("in-compare");
                                i.style.removeProperty("color");
                            }
                        }
                    }
                } else if (action.includes("/wishlist/add/")) {
                    targetSelector = ".header-support[href*='/wishlist/'] b";
                    const b = document.querySelector(targetSelector);
                    if (!b) {
                        const container = document.querySelector(".header-support[href*='/wishlist/'] > div");
                        if (container) {
                            const newB = document.createElement("b");
                            newB.innerText = data.wishlist_count;
                            container.appendChild(newB);
                        }
                    } else {
                        b.innerText = data.wishlist_count;
                    }
                    
                    if (submitBtn) {
                        const i = submitBtn.querySelector("i.fa-heart");
                        if (data.added) {
                            submitBtn.classList.add("selected");
                            if (i) {
                                i.classList.remove("fa-regular");
                                i.classList.add("fa-solid", "in-wishlist");
                                i.style.color = "var(--primary, #0f766e)";
                            }
                        } else {
                            submitBtn.classList.remove("selected");
                            if (i) {
                                i.classList.remove("fa-solid", "in-wishlist");
                                i.classList.add("fa-regular");
                                i.style.removeProperty("color");
                            }
                        }
                    }
                }
                
                // Fly animation
                if (submitBtn && targetSelector && (data.added !== false || action.includes("/cart/add/"))) {
                    const targetIcon = document.querySelector(targetSelector);
                    if (targetIcon) {
                        let startObj = submitBtn.closest(".product-card") ? submitBtn.closest(".product-card").querySelector("img") : null;
                        if (!startObj) startObj = submitBtn.closest(".compare-table") ? submitBtn.closest("td").querySelector("img") : submitBtn;
                        
                        const startRect = (startObj || submitBtn).getBoundingClientRect();
                        const targetRect = targetIcon.getBoundingClientRect();
                        
                        const flyer = document.createElement("div");
                        flyer.style.position = "fixed";
                        flyer.style.zIndex = "999999";
                        flyer.style.top = startRect.top + "px";
                        flyer.style.left = startRect.left + "px";
                        flyer.style.width = "40px";
                        flyer.style.height = "40px";
                        flyer.style.borderRadius = "50%";
                        flyer.style.backgroundColor = "var(--primary, #4aa1df)";
                        flyer.style.boxShadow = "0 4px 12px rgba(0,0,0,0.2)";
                        flyer.style.opacity = "0.9";
                        flyer.style.transition = "all 0.6s cubic-bezier(0.2, 1, 0.3, 1)";
                        flyer.style.pointerEvents = "none";
                        
                        if (startObj && startObj.tagName === "IMG") {
                            flyer.style.backgroundImage = `url(${startObj.src})`;
                            flyer.style.backgroundSize = "cover";
                            flyer.style.backgroundPosition = "center";
                        }
                        
                        document.body.appendChild(flyer);
                        
                        setTimeout(() => {
                            flyer.style.top = targetRect.top + "px";
                            flyer.style.left = targetRect.left + "px";
                            flyer.style.width = "10px";
                            flyer.style.height = "10px";
                            flyer.style.opacity = "0.2";
                        }, 50);
                        
                        setTimeout(() => {
                            flyer.remove();
                            targetIcon.style.transition = "transform 0.2s";
                            targetIcon.style.transform = "scale(1.4)";
                            setTimeout(() => {
                                targetIcon.style.transform = "scale(1)";
                            }, 200);
                        }, 650);
                    }
                }
            } else if (data.message) {
                alert(data.message);
            }
        })
        .catch(err => {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        });
    }
});
// Extra logic to refresh cart drawer content quietly
function refreshCartDrawer() {
    return fetch('/cart/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
    .then(r => r.text())
    .then(html => {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const newDrawer = doc.getElementById('cart-drawer');
        const oldDrawer = document.getElementById('cart-drawer');
        if (newDrawer && oldDrawer) {
            oldDrawer.innerHTML = newDrawer.innerHTML;
        }
    }).catch(e => console.error(e));
}
