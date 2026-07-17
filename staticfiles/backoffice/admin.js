const modal = document.getElementById("global-modal");
const body = document.body;
const sidebar = document.querySelector("[data-sidebar]");
const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
const sidebarOverlay = document.querySelector("[data-sidebar-overlay]");
const notifyToggle = document.querySelector("[data-notify-toggle]");
const notifyDropdown = document.querySelector("[data-notify-dropdown]");
const notifyCount = document.querySelector("[data-notify-count]");
const notifySummary = document.querySelector("[data-notify-summary]");
const notifyReadAll = document.querySelector("[data-notify-read-all]");
const notifyClose = document.querySelector("[data-notify-close]");

function setModalState(isOpen) {
    if (!modal) return;
    modal.hidden = !isOpen;
    body.style.overflow = isOpen ? "hidden" : "";
}

function setSidebarState() {
    if (!sidebar) return;
    const collapsed = localStorage.getItem("bo-sidebar-collapsed") === "1";
    const mobileOpen = body.dataset.sidebarOpen === "1";
    sidebar.classList.toggle("collapsed", collapsed && window.innerWidth > 1180);
    sidebar.classList.toggle("open", mobileOpen && window.innerWidth <= 1180);
    if (sidebarOverlay) {
        sidebarOverlay.classList.toggle("active", mobileOpen && window.innerWidth <= 1180);
    }
}

function toggleSidebarState() {
    if (!sidebar) return;
    if (window.innerWidth <= 1180) {
        body.dataset.sidebarOpen = body.dataset.sidebarOpen === "1" ? "0" : "1";
    } else {
        const next = localStorage.getItem("bo-sidebar-collapsed") === "1" ? "0" : "1";
        localStorage.setItem("bo-sidebar-collapsed", next);
    }
    setSidebarState();
}

function closeNotifications() {
    if (notifyDropdown) {
        notifyDropdown.style.display = "none";
    }
}

function toggleNotifications() {
    if (!notifyDropdown) return;
    const isOpen = notifyDropdown.style.display === "block";
    notifyDropdown.style.display = isOpen ? "none" : "block";
}

function refreshNotificationState() {
    const items = document.querySelectorAll("[data-notify-item]");
    const unread = Array.from(items).filter((item) => item.classList.contains("is-unread")).length;
    if (notifyCount) {
        notifyCount.textContent = unread;
        notifyCount.style.display = unread ? "inline-flex" : "none";
    }
    if (notifySummary) {
        notifySummary.textContent = unread ? `${unread} New` : "All caught up";
    }
}

document.addEventListener("click", (event) => {
    const openTrigger = event.target.closest("[data-open-modal]");
    if (openTrigger) {
        event.preventDefault();
        setModalState(true);
        return;
    }

    const closeTrigger = event.target.closest("[data-close-modal]");
    if (closeTrigger) {
        event.preventDefault();
        setModalState(false);
    }

    if (sidebarToggle && event.target.closest("[data-sidebar-toggle]")) {
        event.preventDefault();
        toggleSidebarState();
    }

    if (sidebarOverlay && event.target.closest("[data-sidebar-overlay]")) {
        body.dataset.sidebarOpen = "0";
        setSidebarState();
    }

    if (notifyToggle && event.target.closest("[data-notify-toggle]")) {
        event.preventDefault();
        toggleNotifications();
        return;
    }

    if (notifyClose && event.target.closest("[data-notify-close]")) {
        event.preventDefault();
        closeNotifications();
        return;
    }

    if (notifyDropdown && !event.target.closest("[data-notify-dropdown]")) {
        closeNotifications();
    }

    const notifyItem = event.target.closest("[data-notify-item]");
    if (notifyItem) {
        notifyItem.classList.remove("is-unread");
        refreshNotificationState();
    }

    if (notifyReadAll && event.target.closest("[data-notify-read-all]")) {
        event.preventDefault();
        document.querySelectorAll("[data-notify-item]").forEach((item) => {
            item.classList.remove("is-unread");
        });
        refreshNotificationState();
    }
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        setModalState(false);
        body.dataset.sidebarOpen = "0";
        setSidebarState();
        closeNotifications();
    }
});

window.addEventListener("resize", setSidebarState);
setSidebarState();
refreshNotificationState();
