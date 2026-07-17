ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN_STAFF = "admin_staff"
ROLE_RETAILER_OWNER = "retailer_owner"
ROLE_RETAILER_MANAGER = "retailer_manager"
ROLE_PRODUCT_MANAGER = "product_manager"
ROLE_STOCK_MANAGER = "stock_manager"
ROLE_ORDER_MANAGER = "order_manager"
ROLE_FINANCE_MANAGER = "finance_manager"
ROLE_REPORT_VIEWER = "report_viewer"
ROLE_CUSTOMER = "customer"

DEFAULT_ROLES = {
    ROLE_SUPER_ADMIN: "Super Admin",
    ROLE_ADMIN_STAFF: "Admin Staff",
    ROLE_RETAILER_OWNER: "Retailer Owner",
    ROLE_RETAILER_MANAGER: "Retailer Manager",
    ROLE_PRODUCT_MANAGER: "Product Manager",
    ROLE_STOCK_MANAGER: "Stock Manager",
    ROLE_ORDER_MANAGER: "Order Manager",
    ROLE_FINANCE_MANAGER: "Finance Manager",
    ROLE_REPORT_VIEWER: "Report Viewer",
    ROLE_CUSTOMER: "Customer",
}

DEFAULT_PERMISSIONS = {
    "platform.manage": "Manage platform configuration",
    "users.manage": "Manage users",
    "staff.manage": "Manage store staff and role assignments",
    "retailers.manage": "Manage retailers",
    "stores.manage": "Manage stores",
    "catalog.manage": "Manage catalog",
    "sale_countdown.manage": "Manage sale countdown settings",
    "inventory.manage": "Manage inventory",
    "orders.manage": "Manage orders",
    "shipments.manage": "Manage shipments and courier operations",
    "payments.manage": "Manage payments and finance",
    "reports.view": "View reports",
    "customer.self": "Access own customer data",
}

ROLE_PERMISSION_MAP = {
    ROLE_SUPER_ADMIN: list(DEFAULT_PERMISSIONS.keys()),
    ROLE_ADMIN_STAFF: [
        "users.manage",
        "staff.manage",
        "retailers.manage",
        "stores.manage",
        "catalog.manage",
        "sale_countdown.manage",
        "inventory.manage",
        "orders.manage",
        "shipments.manage",
        "payments.manage",
        "reports.view",
    ],
    ROLE_RETAILER_OWNER: [
        "staff.manage",
        "stores.manage",
        "catalog.manage",
        "inventory.manage",
        "orders.manage",
        "shipments.manage",
        "payments.manage",
        "reports.view",
    ],
    ROLE_RETAILER_MANAGER: [
        "staff.manage",
        "stores.manage",
        "catalog.manage",
        "inventory.manage",
        "orders.manage",
        "reports.view",
    ],
    ROLE_PRODUCT_MANAGER: ["catalog.manage"],
    ROLE_STOCK_MANAGER: ["inventory.manage"],
    ROLE_ORDER_MANAGER: ["orders.manage"],
    ROLE_FINANCE_MANAGER: ["payments.manage", "reports.view"],
    ROLE_REPORT_VIEWER: ["reports.view"],
    ROLE_CUSTOMER: ["customer.self"],
}
