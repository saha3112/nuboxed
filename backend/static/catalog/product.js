(function () {
    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function setText(node, value) {
        if (node) node.textContent = value;
    }

    function initLegacyGallery() {
        const mainImage = document.getElementById("main-product-image");
        const thumbButtons = document.querySelectorAll(".thumb-button[data-image]");
        const zoomLens = document.getElementById("zoom-lens");

        if (!mainImage || !thumbButtons.length) return;

        thumbButtons.forEach((button) => {
            button.addEventListener("click", () => {
                const imageUrl = button.getAttribute("data-image");
                if (imageUrl) {
                    mainImage.src = imageUrl;
                }
                thumbButtons.forEach((thumb) => thumb.classList.remove("active"));
                button.classList.add("active");
            });
        });

        if (!zoomLens) return;

        const gallery = mainImage.closest(".gallery-panel");
        if (!gallery) return;

        gallery.addEventListener("mousemove", (event) => {
            const rect = mainImage.getBoundingClientRect();
            const x = clamp(event.clientX - rect.left, 0, rect.width);
            const y = clamp(event.clientY - rect.top, 0, rect.height);
            zoomLens.style.display = "block";
            zoomLens.style.left = `${Math.max(0, x - zoomLens.offsetWidth / 2)}px`;
            zoomLens.style.top = `${Math.max(0, y - zoomLens.offsetHeight / 2)}px`;
        });

        gallery.addEventListener("mouseleave", () => {
            zoomLens.style.display = "none";
        });
    }

    function initReferenceGallery() {
        const galleryPanel = document.querySelector("[data-gallery-panel]");
        const thumbButtons = Array.from(document.querySelectorAll("[data-gallery-thumb], .thumb[data-pane-id]"));
        const mediaPanes = Array.from(document.querySelectorAll("[data-media-pane]"));
        const zoomSource = document.getElementById("zoomSource");
        const zoomLens = document.getElementById("zoomLens");
        const zoomResult = document.getElementById("zoomResult");
        const zoomImage = document.querySelector(".zoom-image");
        const thumbViewport = document.getElementById("thumbViewport");
        const thumbList = document.getElementById("thumbList");
        const upButton = document.querySelector(".thumb-up");
        const downButton = document.querySelector(".thumb-down");

        if (!galleryPanel) return;

        let activeId = galleryPanel.dataset.activeId || "";
        let activeType = galleryPanel.dataset.activeType || "image";
        let thumbOffset = 0;

        function initSpinViewer() {
            const spinPane = document.querySelector('[data-media-type="image_360"]');
            if (!spinPane) return;
            const frames = Array.from(spinPane.querySelectorAll("[data-spin-frame]"));
            if (frames.length < 2) return;
            let frame = 0;
            let startX = null;
            let moved = false;
            const showFrame = (next) => {
                frame = (next + frames.length) % frames.length;
                frames.forEach((node, index) => { node.hidden = index !== frame; });
            };
            const moveBy = (distance) => {
                const steps = Math.max(1, Math.round(Math.abs(distance) / 18));
                showFrame(frame + (distance < 0 ? steps : -steps));
            };
            spinPane.style.cursor = "grab";
            spinPane.addEventListener("pointerdown", (event) => {
                startX = event.clientX;
                moved = false;
                spinPane.setPointerCapture?.(event.pointerId);
                spinPane.style.cursor = "grabbing";
            });
            spinPane.addEventListener("pointermove", (event) => {
                if (startX === null) return;
                const distance = event.clientX - startX;
                if (Math.abs(distance) >= 12) {
                    moveBy(distance);
                    startX = event.clientX;
                    moved = true;
                }
            });
            const finishSpin = (event) => {
                if (startX !== null && !moved && event?.type === "click") showFrame(frame + 1);
                startX = null;
                spinPane.style.cursor = "grab";
            };
            spinPane.addEventListener("pointerup", finishSpin);
            spinPane.addEventListener("pointercancel", finishSpin);
            spinPane.addEventListener("click", (event) => { if (!moved) showFrame(frame + 1); });
            showFrame(0);
        }

        function setActivePane(targetId, targetType) {
            // Leaving a video always pauses and rewinds it, including when the
            // customer switches to an image or the 360 viewer.
            document.querySelectorAll(".media-video video").forEach((video) => {
                if (!video.paused) video.pause();
                try { video.currentTime = 0; } catch (error) { /* unloaded video */ }
            });
            document.querySelectorAll(".media-video iframe").forEach((frame) => {
                try {
                    frame.contentWindow.postMessage(JSON.stringify({ event: "command", func: "stopVideo", args: [] }), "*");
                } catch (error) { /* cross-origin player may ignore this */ }
            });
            mediaPanes.forEach((pane) => {
                const isActive = pane.dataset.mediaId === targetId;
                pane.classList.toggle("is-active", isActive);
                pane.hidden = !isActive;
            });

            if (zoomImage) {
                const activeImage = zoomSource.querySelector(`.media-pane.is-active img[data-zoom-image]`);
                if (activeImage && activeImage.getAttribute("src")) {
                    zoomImage.setAttribute("src", activeImage.getAttribute("src"));
                }
            }

            if (targetType !== "image" && zoomLens && zoomResult) {
                zoomSource.classList.remove("zooming");
                zoomLens.style.display = "none";
                zoomResult.style.display = "none";
            }

            thumbButtons.forEach((button) => {
                const buttonTarget = button.dataset.targetId || button.dataset.paneId || "";
                button.classList.toggle("active", buttonTarget === targetId);
            });

            activeId = targetId;
            activeType = targetType;
            galleryPanel.dataset.activeId = targetId;
            galleryPanel.dataset.activeType = targetType;

            // A video thumbnail is itself the user's play gesture. Start the
            // selected player immediately instead of requiring a second click.
            if (targetType === "video") {
                const pane = mediaPanes.find((node) => node.dataset.mediaId === targetId);
                if (!pane) return;
                const video = pane.querySelector("video");
                if (video) {
                    const play = video.play();
                    if (play?.catch) play.catch(() => {});
                    return;
                }
                const frame = pane.querySelector("iframe");
                if (frame) {
                    const playMessage = () => {
                        try {
                            frame.contentWindow.postMessage(JSON.stringify({
                                event: "command", func: "playVideo", args: []
                            }), "*");
                        } catch (error) { /* player may still be loading */ }
                    };
                    playMessage();
                    window.setTimeout(playMessage, 150);
                    window.setTimeout(playMessage, 500);
                }
            }
        }

        function updateThumbPosition() {
            if (!thumbList || !thumbViewport) return;

            if (window.matchMedia("(max-width: 640px)").matches) {
                const max = Math.max(0, thumbList.scrollWidth - thumbViewport.clientWidth);
                thumbOffset = clamp(thumbOffset, 0, max);
                thumbList.style.transform = `translateX(${-thumbOffset}px)`;
                if (upButton) upButton.disabled = thumbOffset <= 0;
                if (downButton) downButton.disabled = thumbOffset >= max - 1;
                return;
            }

            const max = Math.max(0, thumbList.scrollHeight - thumbViewport.clientHeight);
            thumbOffset = clamp(thumbOffset, 0, max);
            thumbList.style.transform = `translateY(${-thumbOffset}px)`;
            if (upButton) upButton.disabled = thumbOffset <= 0;
            if (downButton) downButton.disabled = thumbOffset >= max - 1;
        }

        function stepThumbs(direction) {
            thumbOffset += direction * (window.matchMedia("(max-width: 640px)").matches ? 80 : 98);
            updateThumbPosition();
        }

        // Scroll the thumbnail rail while the pointer is over it. At either
        // end, leave the wheel event untouched so the page can keep scrolling.
        if (thumbViewport) {
            thumbViewport.addEventListener("wheel", (event) => {
                const before = thumbOffset;
                const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX)
                    ? event.deltaY
                    : event.deltaX;
                if (!delta) return;
                thumbOffset += delta;
                updateThumbPosition();
                if (thumbOffset !== before) {
                    event.preventDefault();
                    event.stopPropagation();
                }
            }, { passive: false });
        }

        thumbButtons.forEach((button) => {
            button.addEventListener("click", () => {
                const targetId = button.dataset.targetId || button.dataset.paneId || "";
                const targetType = button.dataset.targetType || button.dataset.style || "image";
                if (targetId) setActivePane(targetId, targetType);
            });
        });

        if (upButton) upButton.addEventListener("click", () => stepThumbs(-1));
        if (downButton) downButton.addEventListener("click", () => stepThumbs(1));

        if (zoomSource && zoomLens && zoomResult && zoomImage) {
            function updateZoom(event) {
                if (window.matchMedia("(max-width: 640px)").matches) return;
                const stage = zoomSource.querySelector(".media-pane.is-active");
                const img = zoomSource.querySelector(".media-pane.is-active img[data-zoom-image]");
                if (!stage || !img) return;

                const rect = stage.getBoundingClientRect();
                const lensW = zoomLens.offsetWidth;
                const lensH = zoomLens.offsetHeight;
                let x = event.clientX - rect.left - lensW / 2;
                let y = event.clientY - rect.top - lensH / 2;
                x = clamp(x, 0, rect.width - lensW);
                y = clamp(y, 0, rect.height - lensH);

                zoomLens.style.display = "block";
                zoomResult.style.display = "block";
                zoomLens.style.left = `${x}px`;
                zoomLens.style.top = `${y}px`;

                const scaleX = zoomResult.clientWidth / lensW;
                const scaleY = zoomResult.clientHeight / lensH;
                const imgRect = img.getBoundingClientRect();
                const imgLeft = imgRect.left - rect.left;
                const imgTop = imgRect.top - rect.top;

                zoomImage.style.left = `${(imgLeft * scaleX) - (x * scaleX)}px`;
                zoomImage.style.top = `${(imgTop * scaleY) - (y * scaleY)}px`;
                zoomImage.style.width = `${img.offsetWidth * scaleX}px`;
                zoomImage.style.height = `${img.offsetHeight * scaleY}px`;
                zoomImage.style.transform = "none";
            }

            zoomSource.addEventListener("mouseenter", () => {
                if (galleryPanel.dataset.activeType === "image") {
                    zoomSource.classList.add("zooming");
                }
            });
            zoomSource.addEventListener("mousemove", (e) => {
                if (galleryPanel.dataset.activeType === "image") {
                    updateZoom(e);
                } else {
                    zoomSource.classList.remove("zooming");
                    zoomLens.style.display = "none";
                    zoomResult.style.display = "none";
                }
            });
            zoomSource.addEventListener("mouseleave", () => {
                zoomSource.classList.remove("zooming");
                zoomLens.style.display = "none";
                zoomResult.style.display = "none";
            });
        }

        setActivePane(activeId || (thumbButtons[0] && (thumbButtons[0].dataset.targetId || thumbButtons[0].dataset.paneId)) || "", activeType);
        initSpinViewer();
        updateThumbPosition();
        window.addEventListener("resize", () => {
            thumbOffset = 0;
            updateThumbPosition();
        });
    }

    const CURRENCY_SYMBOLS = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "INR": "₹",
        "BDT": "৳",
        "SGD": "S$",
        "AED": "د.إ"
    };

    function formatCurrency(val, currencyCode) {
        const num = parseFloat(val);
        if (isNaN(num)) return val;
        const symbol = CURRENCY_SYMBOLS[currencyCode.toUpperCase()] || (currencyCode.toUpperCase() + " ");
        return symbol + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function initStorageButtons() {
        const storageButtons = document.querySelectorAll(".storage, [data-variant-chip]");
        const storageLabel = document.getElementById("storageLabel");
        const variantLabel = document.getElementById("variantLabel");

        // Parse variants JSON
        let variants = [];
        const jsonNode = document.getElementById("product-variants-json");
        if (jsonNode) {
            try {
                variants = JSON.parse(jsonNode.textContent || "[]");
            } catch (err) {
                console.error("Error parsing variants JSON:", err);
            }
        }

        const hiddenCartVariantId = document.getElementById("hiddenCartVariantId");
        const hiddenBuyNowVariantId = document.getElementById("hiddenBuyNowVariantId");
        const displayCurrentPrice = document.getElementById("displayCurrentPrice");
        const displayComparePrice = document.getElementById("displayComparePrice");
        const displayDiscountBadge = document.getElementById("displayDiscountBadge");
        const productStockLine = document.getElementById("productStockLine");
        const addToCartButton = document.querySelector("#addToCartForm button[type='submit']");
        const buyNowButton = document.querySelector("#buyNowForm button[type='submit']");
        const quantityInput = document.querySelector("[data-qty-input]");

        function getStockSnapshot(stock) {
            const qty = Number(stock || 0);
            if (qty > 0) {
                return { label: "Available Stock", tone: "success", icon: "fa-circle-check" };
            }
            return { label: "Out of Stock", tone: "danger", icon: "fa-circle-xmark" };
        }

        function updateStockLine(stock) {
            if (!productStockLine) return;
            const snapshot = getStockSnapshot(stock);
            productStockLine.className = `stock-line ${snapshot.tone}`;
            productStockLine.innerHTML = `<span><i class="fa-solid ${snapshot.icon}"></i> ${snapshot.label}</span>`;
        }

        function updatePurchaseState(stock) {
            const qty = Number(stock || 0);
            const disabled = qty <= 0;
            [addToCartButton, buyNowButton].forEach((button) => {
                if (!button) return;
                button.disabled = disabled;
                button.classList.toggle("disabled", disabled);
            });
            if (quantityInput) {
                quantityInput.max = String(Math.max(qty, 1));
                if (Number(quantityInput.value || 1) > qty && qty > 0) {
                    quantityInput.value = String(qty);
                    quantityInput.dispatchEvent(new Event("input", { bubbles: true }));
                }
            }
        }

        function normalized(value) {
            return (value || "").toLowerCase().replace(/\s+/g, "");
        }

        function variantAttribute(variant, type) {
            const attributes = variant.attributes || {};
            const exact = attributes[type];
            if (exact !== undefined) return exact;
            const key = Object.keys(attributes).find((name) => {
                const normalizedName = normalized(name);
                if (type === "storage") return normalizedName.includes("storage") || normalizedName.includes("internal");
                if (type === "ram") return normalizedName.includes("ram") || normalizedName.includes("memory");
                if (type === "color") return normalizedName.includes("color");
                return normalizedName === normalized(type);
            });
            return key ? attributes[key] : "";
        }

        function selectFirstAvailableVariant() {
            const firstAvailable = variants.find((variant) => Number(variant.stock || 0) > 0);
            if (!firstAvailable) return;
            document.querySelectorAll(".option-block").forEach((block) => {
                const titleEl = block.querySelector(".option-title");
                if (!titleEl) return;
                const titleText = titleEl.textContent.trim().toLowerCase();
                const attrKey = titleText.includes("color")
                    ? "color"
                    : (titleText.includes("storage") || titleText.includes("internal") ? "storage" : titleText.replace(":", "").trim().toLowerCase());
                const target = normalized(variantAttribute(firstAvailable, attrKey));
                if (!target) return;
                const buttons = Array.from(block.querySelectorAll(".storage"));
                const match = buttons.find((btn) => normalized(btn.dataset.value || btn.textContent.trim()) === target);
                if (!match) return;
                buttons.forEach((btn) => btn.classList.remove("active"));
                match.classList.add("active");
                const labelEl = attrKey === "color"
                    ? document.getElementById("colorLabel")
                    : (attrKey === "storage" ? document.getElementById("storageLabel") : (attrKey === "ram" ? document.getElementById("ramLabel") : titleEl.querySelector("strong")));
                if (labelEl) labelEl.textContent = match.dataset.value || match.textContent.trim();
            });
        }

        function updateSelectedVariant() {
            const activeOptions = {};
            document.querySelectorAll(".option-block").forEach((block) => {
                const titleEl = block.querySelector(".option-title");
                if (!titleEl) return;
                const titleText = titleEl.textContent.trim().toLowerCase();
                let attrKey = "";
                let labelEl = null;

                if (titleText.includes("color")) {
                    attrKey = "color";
                    labelEl = document.getElementById("colorLabel");
                } else if (titleText.includes("storage") || titleText.includes("internal")) {
                    attrKey = "storage";
                    labelEl = document.getElementById("storageLabel");
                } else if (titleText.includes("ram") || titleText.includes("memory")) {
                    attrKey = "ram";
                    labelEl = document.getElementById("ramLabel");
                } else {
                    attrKey = titleText.replace(":", "").trim().toLowerCase();
                    labelEl = titleEl.querySelector("strong");
                }

                const activeBtn = block.querySelector(".storage.active");
                if (activeBtn) {
                    const value = activeBtn.dataset.value || activeBtn.textContent.trim();
                    activeOptions[attrKey] = normalized(value);
                    if (labelEl) {
                        labelEl.textContent = value;
                    }
                }
            });

            // Find matching variant
            const matching = variants.find((variant) => {
                return Object.entries(activeOptions).every(([attrKey, activeVal]) => {
                    const varVal = normalized(variantAttribute(variant, attrKey));
                    return varVal === activeVal;
                });
            });

            if (matching) {
                if (hiddenCartVariantId) hiddenCartVariantId.value = matching.id;
                if (hiddenBuyNowVariantId) hiddenBuyNowVariantId.value = matching.id;

                // Update prices
                const currency = displayCurrentPrice ? (displayCurrentPrice.dataset.currency || "EUR") : "EUR";
                if (displayCurrentPrice && matching.price) {
                    displayCurrentPrice.textContent = formatCurrency(matching.price, currency);
                }
                if (displayComparePrice) {
                    if (matching.compare_price) {
                        displayComparePrice.textContent = formatCurrency(matching.compare_price, currency);
                        displayComparePrice.style.display = "";
                    } else {
                        displayComparePrice.style.display = "none";
                    }
                }

                // Update discount badge
                if (displayDiscountBadge) {
                    const price = parseFloat(matching.price);
                    const compPrice = parseFloat(matching.compare_price);
                    if (!isNaN(price) && !isNaN(compPrice) && compPrice > price) {
                        const pct = Math.round(((compPrice - price) / compPrice) * 100);
                        displayDiscountBadge.textContent = `Save ${pct}%`;
                        displayDiscountBadge.style.display = "";
                    } else {
                        displayDiscountBadge.style.display = "none";
                    }
                }

                updateStockLine(matching.stock);
                updatePurchaseState(matching.stock);
            } else {
                updatePurchaseState(0);
            }
        }

        function updateOptionAvailability(changedAttr) {
            let activeColor = "";
            let activeStorage = "";

            document.querySelectorAll(".option-block").forEach((block) => {
                const titleEl = block.querySelector(".option-title");
                if (!titleEl) return;
                const titleText = titleEl.textContent.trim().toLowerCase();
                const activeBtn = block.querySelector(".storage.active");
                if (titleText.includes("color")) {
                    if (activeBtn) activeColor = normalized(activeBtn.dataset.value || activeBtn.textContent.trim());
                } else if (titleText.includes("storage") || titleText.includes("internal")) {
                    if (activeBtn) activeStorage = normalized(activeBtn.dataset.value || activeBtn.textContent.trim());
                }
            });

            // Auto-fallback if invalid combination
            let matching = variants.find(v => {
                const varColor = normalized(variantAttribute(v, "color"));
                const varStorage = normalized(variantAttribute(v, "storage"));
                return varColor === activeColor && varStorage === activeStorage;
            });

            if (!matching && variants.length > 0) {
                if (changedAttr === "storage" && activeStorage) {
                    const fallback = variants.find(v => normalized(variantAttribute(v, "storage")) === activeStorage);
                    if (fallback) {
                        const fallbackColor = normalized(variantAttribute(fallback, "color"));
                        document.querySelectorAll(".option-block").forEach((block) => {
                            const titleEl = block.querySelector(".option-title");
                            if (titleEl && titleEl.textContent.toLowerCase().includes("color")) {
                                block.querySelectorAll(".storage").forEach(btn => {
                                    const btnVal = normalized(btn.dataset.value || btn.textContent.trim());
                                    if (btnVal === fallbackColor) {
                                        block.querySelectorAll(".storage").forEach(b => b.classList.remove("active"));
                                        btn.classList.add("active");
                                        activeColor = fallbackColor;
                                    }
                                });
                            }
                        });
                    }
                } else if (changedAttr === "color" && activeColor) {
                    const fallback = variants.find(v => normalized(variantAttribute(v, "color")) === activeColor);
                    if (fallback) {
                        const fallbackStorage = normalized(variantAttribute(fallback, "storage"));
                        document.querySelectorAll(".option-block").forEach((block) => {
                            const titleEl = block.querySelector(".option-title");
                            if (titleEl && (titleEl.textContent.toLowerCase().includes("storage") || titleEl.textContent.toLowerCase().includes("internal"))) {
                                block.querySelectorAll(".storage").forEach(btn => {
                                    const btnVal = normalized(btn.dataset.value || btn.textContent.trim());
                                    if (btnVal === fallbackStorage) {
                                        block.querySelectorAll(".storage").forEach(b => b.classList.remove("active"));
                                        btn.classList.add("active");
                                        activeStorage = fallbackStorage;
                                    }
                                });
                            }
                        });
                    }
                }
            }

            // Now update classes (fade and crossed-out/out-of-stock)
            const activeByType = {};
            document.querySelectorAll(".option-block").forEach((block) => {
                const titleEl = block.querySelector(".option-title");
                const activeBtn = block.querySelector(".storage.active");
                if (!titleEl || !activeBtn) return;
                const titleText = titleEl.textContent.trim().toLowerCase();
                const type = titleText.includes("color")
                    ? "color"
                    : (titleText.includes("storage") || titleText.includes("internal")
                        ? "storage"
                        : (titleText.includes("ram") || titleText.includes("memory") ? "ram" : ""));
                if (type) activeByType[type] = normalized(activeBtn.dataset.value || activeBtn.textContent.trim());
            });

            document.querySelectorAll(".option-block").forEach((block) => {
                const titleEl = block.querySelector(".option-title");
                if (!titleEl) return;
                const titleText = titleEl.textContent.trim().toLowerCase();
                const isColorGroup = titleText.includes("color");
                const isStorageGroup = titleText.includes("storage") || titleText.includes("internal");
                const isRamGroup = titleText.includes("ram") || titleText.includes("memory");
                const optionType = isColorGroup ? "color" : (isStorageGroup ? "storage" : (isRamGroup ? "ram" : ""));

                block.querySelectorAll(".storage").forEach(btn => {
                    const btnVal = normalized(btn.dataset.value || btn.textContent.trim());
                    if (!optionType) return;

                    // Evaluate this option against the currently selected values
                    // of every other attribute (e.g. RAM + Yellow + 256GB).
                    const relatedVariants = variants.filter((variant) => {
                        if (normalized(variantAttribute(variant, optionType)) !== btnVal) return false;
                        return Object.entries(activeByType).every(([type, value]) => {
                            if (type === optionType || !value) return true;
                            return normalized(variantAttribute(variant, type)) === value;
                        });
                    });
                    const isOutOfStock = variants.length > 0 && (
                        relatedVariants.length === 0 || relatedVariants.every(v => Number(v.stock || 0) <= 0)
                    );
                    btn.classList.toggle("out-of-stock", isOutOfStock);
                    btn.classList.toggle("faded", isOutOfStock);
                    btn.dataset.stockState = isOutOfStock ? "out" : "in";
                    btn.setAttribute("aria-disabled", isOutOfStock ? "true" : "false");
                });
            });
        }

        if (!storageButtons.length) return;

        storageButtons.forEach((button) => {
            button.addEventListener("click", () => {
                if (button.dataset.stockState === "out") return;
                const group = button.closest(".storage-options");
                if (group) {
                    group.querySelectorAll(".storage").forEach((item) => item.classList.remove("active"));
                } else {
                    document.querySelectorAll("[data-variant-chip]").forEach((item) => item.classList.remove("active"));
                }
                button.classList.add("active");

                // Check if color or storage clicked
                let type = "storage";
                const block = button.closest(".option-block");
                if (block) {
                    const titleEl = block.querySelector(".option-title");
                    if (titleEl && titleEl.textContent.toLowerCase().includes("color")) {
                        type = "color";
                        
                        // Switch image to matching color index
                        const colorVal = (button.dataset.value || button.textContent.trim()).toLowerCase().trim();
                        const matchThumb = Array.from(document.querySelectorAll(".thumb")).find(thumb => {
                            return (thumb.dataset.color || "").toLowerCase().trim() === colorVal;
                        });
                        if (matchThumb) {
                            matchThumb.click();
                        }
                    }
                }

                updateOptionAvailability(type);
                updateSelectedVariant();
            });
        });

        // Run initially to set initial states
        selectFirstAvailableVariant();
        updateOptionAvailability("storage");
        updateSelectedVariant();
    }

    function initTabs() {
        const buttons = document.querySelectorAll(".tab-btn");
        const panels = document.querySelectorAll(".tab-panel");
        if (!buttons.length || !panels.length) return;

        buttons.forEach((button) => {
            button.addEventListener("click", () => {
                buttons.forEach((item) => item.classList.remove("active"));
                panels.forEach((panel) => panel.classList.remove("active"));
                button.classList.add("active");
                const panel = document.getElementById(button.dataset.tab);
                if (panel) panel.classList.add("active");
            });
        });
    }

    function initCountdown() {
        const root = document.querySelector("[data-countdown]");
        if (!root) return;

        const days = root.querySelector("[data-countdown-days]");
        const hours = root.querySelector("[data-countdown-hours]");
        const minutes = root.querySelector("[data-countdown-minutes]");
        const seconds = root.querySelector("[data-countdown-seconds]");
        let total = 534 * 86400 + 1 * 3600 + 6 * 60 + 47;

        const render = () => {
            const d = Math.floor(total / 86400);
            const h = Math.floor((total % 86400) / 3600);
            const m = Math.floor((total % 3600) / 60);
            const s = total % 60;
            setText(days, String(d));
            setText(hours, String(h).padStart(2, "0"));
            setText(minutes, String(m).padStart(2, "0"));
            setText(seconds, String(s).padStart(2, "0"));
        };

        render();
        setInterval(() => {
            total = Math.max(0, total - 1);
            render();
        }, 1000);
    }

    function initQuantity() {
        const input = document.querySelector("[data-qty-input]");
        const plus = document.querySelector("[data-qty-plus]");
        const minus = document.querySelector("[data-qty-minus]");
        const hiddenCartQty = document.getElementById("hiddenCartQty");
        const hiddenBuyNowQty = document.getElementById("hiddenBuyNowQty");

        if (!input) return;

        function syncQty() {
            const max = Number(input.max || 0);
            let next = Math.max(1, Number(input.value || 1));
            if (max > 0) next = Math.min(next, max);
            input.value = String(next);
            const val = input.value || "1";
            if (hiddenCartQty) hiddenCartQty.value = val;
            if (hiddenBuyNowQty) hiddenBuyNowQty.value = val;
        }

        if (plus) {
            plus.addEventListener("click", () => {
                input.value = Number(input.value || 1) + 1;
                syncQty();
            });
        }
        if (minus) {
            minus.addEventListener("click", () => {
                input.value = Math.max(1, Number(input.value || 1) - 1);
                syncQty();
            });
        }
        input.addEventListener("input", syncQty);
        syncQty();
    }

    function initReviewModal() {
        const reviewModal = document.getElementById("reviewModal");
        const reviewOpen = document.querySelector(".review-btn");
        const reviewClose = document.getElementById("reviewClose");
        const reviewCancel = document.getElementById("reviewCancel");
        const reviewForm = document.getElementById("reviewForm");
        const reviewSuccess = document.getElementById("reviewSuccess");
        if (!reviewModal || !reviewOpen || !reviewClose || !reviewCancel || !reviewForm || !reviewSuccess) return;

        function openReviewModal() {
            reviewModal.classList.add("open");
            reviewModal.setAttribute("aria-hidden", "false");
            document.body.style.overflow = "hidden";
            const title = document.getElementById("reviewInputTitle");
            if (title) setTimeout(() => title.focus(), 50);
        }

        function closeReviewModal() {
            reviewModal.classList.remove("open");
            reviewModal.setAttribute("aria-hidden", "true");
            document.body.style.overflow = "";
            reviewSuccess.classList.remove("show");
        }

        reviewOpen.addEventListener("click", openReviewModal);
        reviewClose.addEventListener("click", closeReviewModal);
        reviewCancel.addEventListener("click", closeReviewModal);
        reviewModal.addEventListener("click", (event) => {
            if (event.target === reviewModal) closeReviewModal();
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && reviewModal.classList.contains("open")) {
                closeReviewModal();
            }
        });
        reviewForm.addEventListener("submit", (event) => {
            event.preventDefault();
            if (!reviewForm.checkValidity()) {
                reviewForm.reportValidity();
                return;
            }

            const submitUrl = reviewForm.dataset.submitUrl;
            const formData = new FormData(reviewForm);

            // Get selected rating radio button
            const selectedRating = reviewForm.closest('#reviewModal')?.querySelector('input[name="rating"]:checked');
            if (selectedRating) {
                formData.append('rating', selectedRating.value);
            }

            fetch(submitUrl, {
                method: "POST",
                body: formData,
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    reviewSuccess.textContent = data.message;
                    reviewSuccess.classList.add("show");
                    setTimeout(() => {
                        reviewForm.reset();
                        const star3 = document.getElementById("star3");
                        if (star3) star3.checked = true;
                        closeReviewModal();
                        window.location.reload();
                    }, 1800);
                } else {
                    alert("Error: " + (data.message || "Could not submit review."));
                }
            })
            .catch(err => {
                console.error(err);
                alert("Something went wrong. Please try again.");
            });
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        initLegacyGallery();
        initReferenceGallery();
        initStorageButtons();
        initTabs();
        initQuantity();
        initReviewModal();
    });
})();
