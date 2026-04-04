const state = {
    token: localStorage.getItem("qb_token") || null,
    user: null,
    activeTab: "overview",
    allOrders: [],
    allCustomers: [],
    allRestaurants: [],
    allDeliveryPartners: [],
    allAudits: [],
    filteredOrders: [],
    selectedCustomerId: null,
    selectedRestaurantId: null,
    selectedDeliveryId: null,
    currentCustomer: null,
    currentRestaurant: null,
    currentDelivery: null,
};

const selectors = {
    userChip: document.getElementById("admin-user-chip"),
    refreshBtn: document.getElementById("admin-refresh-btn"),
    logoutBtn: document.getElementById("admin-logout-btn"),
    heroName: document.getElementById("admin-hero-name"),
    heroEmail: document.getElementById("admin-hero-email"),
    navLinks: document.querySelectorAll(".admin-nav-links a"),
    tabPanes: {
        overview: document.getElementById("tab-overview"),
        customers: document.getElementById("tab-customers"),
        restaurants: document.getElementById("tab-restaurants"),
        delivery: document.getElementById("tab-delivery"),
        audits: document.getElementById("tab-audits"),
    },
    counts: {
        members: document.getElementById("count-members"),
        customers: document.getElementById("count-customers"),
        restaurants: document.getElementById("count-restaurants"),
        delivery: document.getElementById("count-delivery"),
        orders: document.getElementById("count-orders"),
        payments: document.getElementById("count-payments"),
    },
    overviewSearchInput: document.getElementById("overview-search-input"),
    overviewSearchBtn: document.getElementById("overview-search-btn"),
    overviewOrdersBody: document.getElementById("overview-orders-body"),

    loadCustomersBtn: document.getElementById("load-customers-btn"),
    customersTableBody: document.getElementById("customers-table-body"),

    loadRestaurantsBtn: document.getElementById("load-restaurants-btn"),
    restaurantsTableBody: document.getElementById("restaurants-table-body"),

    loadDeliveryPartnersBtn: document.getElementById("load-delivery-partners-btn"),
    deliveryPartnersTableBody: document.getElementById("delivery-partners-table-body"),

    refreshAuditsBtn: document.getElementById("refresh-audits-btn"),
    auditsTableBody: document.getElementById("audits-table-body"),

    modals: {
        order: document.getElementById("order-detail-modal"),
        customer: document.getElementById("customer-detail-modal"),
        restaurant: document.getElementById("restaurant-detail-modal"),
        delivery: document.getElementById("delivery-detail-modal"),
        customerEdit: document.getElementById("customer-edit-modal"),
        restaurantEdit: document.getElementById("restaurant-edit-modal"),
        deliveryEdit: document.getElementById("delivery-edit-modal"),
    },
    modalBodies: {
        order: document.getElementById("order-detail-body"),
        customer: document.getElementById("customer-detail-body"),
        restaurant: document.getElementById("restaurant-detail-body"),
        delivery: document.getElementById("delivery-detail-body"),
    },
    modalBtns: {
        customerEdit: document.getElementById("customer-edit-btn"),
        customerDelete: document.getElementById("customer-delete-btn"),
        customerRestore: document.getElementById("customer-restore-btn"),
        restaurantEdit: document.getElementById("restaurant-edit-btn"),
        restaurantDelete: document.getElementById("restaurant-delete-btn"),
        restaurantRestore: document.getElementById("restaurant-restore-btn"),
        deliveryEdit: document.getElementById("delivery-edit-btn"),
        deliveryDelete: document.getElementById("delivery-delete-btn"),
        deliveryRestore: document.getElementById("delivery-restore-btn"),
        customerEditSave: document.getElementById("customer-edit-save-btn"),
        restaurantEditSave: document.getElementById("restaurant-edit-save-btn"),
        deliveryEditSave: document.getElementById("delivery-edit-save-btn"),
    },
    forms: {
        customer: {
            name: document.getElementById("customer-edit-name"),
            email: document.getElementById("customer-edit-email"),
            phone: document.getElementById("customer-edit-phone"),
            tier: document.getElementById("customer-edit-tier"),
            membership: document.getElementById("customer-edit-membership"),
            discount: document.getElementById("customer-edit-discount"),
            dueDate: document.getElementById("customer-edit-due-date"),
            password: document.getElementById("customer-edit-password"),
        },
        restaurant: {
            name: document.getElementById("restaurant-edit-name"),
            email: document.getElementById("restaurant-edit-email"),
            phone: document.getElementById("restaurant-edit-phone"),
            city: document.getElementById("restaurant-edit-city"),
            zip: document.getElementById("restaurant-edit-zip"),
            address: document.getElementById("restaurant-edit-address"),
            lat: document.getElementById("restaurant-edit-lat"),
            lng: document.getElementById("restaurant-edit-lng"),
            open: document.getElementById("restaurant-edit-open"),
            verified: document.getElementById("restaurant-edit-verified"),
            rating: document.getElementById("restaurant-edit-rating"),
            password: document.getElementById("restaurant-edit-password"),
        },
        delivery: {
            name: document.getElementById("delivery-edit-name"),
            email: document.getElementById("delivery-edit-email"),
            phone: document.getElementById("delivery-edit-phone"),
            vehicle: document.getElementById("delivery-edit-vehicle"),
            license: document.getElementById("delivery-edit-license"),
            dob: document.getElementById("delivery-edit-dob"),
            lat: document.getElementById("delivery-edit-lat"),
            lng: document.getElementById("delivery-edit-lng"),
            online: document.getElementById("delivery-edit-online"),
            rating: document.getElementById("delivery-edit-rating"),
            password: document.getElementById("delivery-edit-password"),
        },
    },
    toast: document.getElementById("admin-toast"),
};

function showToast(message, isError = false) {
    selectors.toast.textContent = message;
    selectors.toast.style.background = isError ? "#7f1d1d" : "var(--admin-accent-dark)";
    selectors.toast.classList.remove("hidden");
    setTimeout(() => selectors.toast.classList.add("hidden"), 2800);
}

function openModal(modalKey) {
    selectors.modals[modalKey]?.classList.add("active");
}

function closeModal(modalKey) {
    selectors.modals[modalKey]?.classList.remove("active");
}

class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

async function api(path, options = {}) {
    const headers = options.headers || {};
    headers["Content-Type"] = "application/json";
    if (state.token) {
        headers.Authorization = `Bearer ${state.token}`;
    }

    const response = await fetch(path, { ...options, headers });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new ApiError(payload.message || "Request failed", response.status);
    }
    return payload;
}

function isAuthError(error) {
    return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

function formatDate(value) {
    if (!value) return "-";
    const dateObj = new Date(value);
    return Number.isNaN(dateObj.getTime()) ? "-" : dateObj.toLocaleString();
}

function toDatetimeLocal(value) {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function setTab(tabName) {
    state.activeTab = tabName;
    selectors.navLinks.forEach((link) => {
        const isActive = link.dataset.tab === tabName;
        link.style.color = isActive ? "var(--admin-accent)" : "var(--admin-ink)";
        link.style.fontWeight = isActive ? "700" : "600";
    });
    Object.entries(selectors.tabPanes).forEach(([name, pane]) => {
        pane.classList.toggle("active", name === tabName);
    });
}

async function ensureAdminAuth() {
    if (!state.token) {
        window.location.href = "/admin";
        return false;
    }

    const payload = await api("/api/auth/me");
    const user = payload.data;
    if (!user.roles.includes("Admin")) {
        localStorage.removeItem("qb_token");
        localStorage.removeItem("qb_portal");
        window.location.href = "/";
        return false;
    }

    state.user = user;
    localStorage.setItem("qb_portal", "Admin");
    selectors.userChip.textContent = user.name;
    selectors.heroName.textContent = `Welcome, ${user.name}`;
    selectors.heroEmail.textContent = `Email: ${user.email}`;
    return true;
}

async function loadOverview() {
    const payload = await api("/api/admin/overview");
    const counts = payload.data.counts || {};
    selectors.counts.members.textContent = counts.Member || 0;
    selectors.counts.customers.textContent = counts.Customer || 0;
    selectors.counts.restaurants.textContent = counts.Restaurant || 0;
    selectors.counts.delivery.textContent = counts.DeliveryPartner || 0;
    selectors.counts.orders.textContent = counts.Orders || 0;
    selectors.counts.payments.textContent = counts.Payment || 0;

    state.allOrders = payload.data.recentOrders || [];
    state.filteredOrders = [...state.allOrders];
    renderOrdersTable(state.filteredOrders);
}

function renderOrdersTable(orders) {
    selectors.overviewOrdersBody.innerHTML = "";
    if (!orders.length) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="8" style="text-align:center;">No orders found</td>`;
        selectors.overviewOrdersBody.appendChild(tr);
        return;
    }

    for (const order of orders) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>#${order.orderID}</td>
            <td>${order.orderStatus}</td>
            <td>${order.customerName || "-"}</td>
            <td>${order.restaurantName || "-"}</td>
            <td>${order.partnerName || "-"}</td>
            <td>${order.totalAmount || 0}</td>
            <td>${formatDate(order.orderTime)}</td>
            <td><button onclick="viewOrderDetails(${order.orderID})" type="button">View</button></td>
        `;
        selectors.overviewOrdersBody.appendChild(tr);
    }
}

function filterOrders() {
    const query = selectors.overviewSearchInput.value.toLowerCase();
    if (!query) {
        state.filteredOrders = [...state.allOrders];
    } else {
        state.filteredOrders = state.allOrders.filter((order) =>
            (order.customerName || "").toLowerCase().includes(query) ||
            (order.restaurantName || "").toLowerCase().includes(query) ||
            (order.partnerName || "").toLowerCase().includes(query)
        );
    }
    renderOrdersTable(state.filteredOrders);
}

async function viewOrderDetails(orderId) {
    const payload = await api(`/api/admin/order/${orderId}`);
    const order = payload.data;

    let html = `
        <div class="detail-section">
            <h3>Order Information</h3>
            <div class="detail-row"><div class="detail-label">Order ID:</div><div class="detail-value">#${order.orderID}</div></div>
            <div class="detail-row"><div class="detail-label">Status:</div><div class="detail-value">${order.orderStatus}</div></div>
            <div class="detail-row"><div class="detail-label">Time:</div><div class="detail-value">${formatDate(order.orderTime)}</div></div>
            <div class="detail-row"><div class="detail-label">Total:</div><div class="detail-value">₹${order.totalAmount}</div></div>
        </div>
        <div class="detail-section">
            <h3>Customer Details</h3>
            <div class="detail-row"><div class="detail-label">Name:</div><div class="detail-value">${order.customerName || "-"}</div></div>
            <div class="detail-row"><div class="detail-label">Email:</div><div class="detail-value">${order.customerEmail || "-"}</div></div>
            <div class="detail-row"><div class="detail-label">Phone:</div><div class="detail-value">${order.customerPhone || "-"}</div></div>
        </div>
        <div class="detail-section">
            <h3>Restaurant Details</h3>
            <div class="detail-row"><div class="detail-label">Name:</div><div class="detail-value">${order.restaurantName || "-"}</div></div>
            <div class="detail-row"><div class="detail-label">City:</div><div class="detail-value">${order.restaurantCity || "-"}</div></div>
        </div>
    `;

    if (order.partnerName) {
        html += `
            <div class="detail-section">
                <h3>Delivery Partner Details</h3>
                <div class="detail-row"><div class="detail-label">Name:</div><div class="detail-value">${order.partnerName}</div></div>
                <div class="detail-row"><div class="detail-label">Status:</div><div class="detail-value">${order.deliveryStatus || "-"}</div></div>
                <div class="detail-row"><div class="detail-label">Accepted:</div><div class="detail-value">${formatDate(order.acceptanceTime)}</div></div>
                <div class="detail-row"><div class="detail-label">Pickup:</div><div class="detail-value">${formatDate(order.pickupTime)}</div></div>
                <div class="detail-row"><div class="detail-label">Delivered:</div><div class="detail-value">${formatDate(order.deliveryTime)}</div></div>
            </div>
        `;
    }

    if (order.items && order.items.length > 0) {
        html += `<div class="detail-section"><h3>Order Items</h3><table style="width:100%;"><tr><th>Item</th><th>Qty</th><th>Price</th></tr>`;
        for (const item of order.items) {
            html += `<tr><td>${item.name}</td><td>${item.quantity}</td><td>₹${item.priceAtPurchase}</td></tr>`;
        }
        html += `</table></div>`;
    }

    selectors.modalBodies.order.innerHTML = html;
    openModal("order");
}

async function loadCustomers() {
    const payload = await api("/api/admin/customers");
    state.allCustomers = payload.data || [];
    renderCustomersTable();
}

function renderCustomersTable() {
    selectors.customersTableBody.innerHTML = "";
    if (!state.allCustomers.length) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="7" style="text-align:center;">No customers found</td>`;
        selectors.customersTableBody.appendChild(tr);
        return;
    }

    for (const customer of state.allCustomers) {
        const status = customer.isDeleted ? "Deleted" : "Active";
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${customer.customerID}</td>
            <td>${customer.name}</td>
            <td>${customer.email}</td>
            <td>${customer.phoneNumber || "-"}</td>
            <td>${customer.orderCount || 0}</td>
            <td>${status}</td>
            <td><button onclick="viewCustomerDetails(${customer.customerID})" type="button">View</button></td>
        `;
        selectors.customersTableBody.appendChild(tr);
    }
}

async function viewCustomerDetails(customerId) {
    const payload = await api(`/api/admin/customer/${customerId}`);
    const customer = payload.data;
    state.selectedCustomerId = customerId;
    state.currentCustomer = customer;

    const tierText = customer.loyaltyTier ?? customer.membershipTier ?? "Standard";
    const html = `
        <div class="detail-section">
            <h3>Customer Information</h3>
            <div class="detail-row"><div class="detail-label">ID:</div><div class="detail-value">#${customer.customerID}</div></div>
            <div class="detail-row"><div class="detail-label">Name:</div><div class="detail-value">${customer.name}</div></div>
            <div class="detail-row"><div class="detail-label">Email:</div><div class="detail-value">${customer.email}</div></div>
            <div class="detail-row"><div class="detail-label">Phone:</div><div class="detail-value">${customer.phoneNumber || "-"}</div></div>
            <div class="detail-row"><div class="detail-label">Member Since:</div><div class="detail-value">${formatDate(customer.joinDate)}</div></div>
        </div>
        <div class="detail-section">
            <h3>Membership Details</h3>
            <div class="detail-row"><div class="detail-label">Tier:</div><div class="detail-value">${tierText}</div></div>
            <div class="detail-row"><div class="detail-label">Membership:</div><div class="detail-value">${customer.membership ? "Yes" : "No"}</div></div>
            <div class="detail-row"><div class="detail-label">Due Date:</div><div class="detail-value">${formatDate(customer.membershipDueDate)}</div></div>
        </div>
        <div class="detail-section">
            <h3>Order History</h3>
            <div class="detail-row"><div class="detail-label">Total Orders:</div><div class="detail-value">${customer.totalOrders || 0}</div></div>
            <div class="detail-row"><div class="detail-label">Total Spent:</div><div class="detail-value">₹${customer.totalSpent || 0}</div></div>
        </div>
    `;

    selectors.modalBodies.customer.innerHTML = html;
    selectors.modalBtns.customerDelete.style.display = customer.isDeleted ? "none" : "inline-block";
    selectors.modalBtns.customerRestore.style.display = customer.isDeleted ? "inline-block" : "none";
    selectors.modalBtns.customerEdit.style.display = customer.isDeleted ? "none" : "inline-block";
    openModal("customer");
}

async function deleteCustomer() {
    if (!state.selectedCustomerId) return;
    if (!window.confirm("Soft delete this customer?")) return;

    await api(`/api/admin/customer/${state.selectedCustomerId}`, { method: "DELETE" });
    showToast("Customer deleted");
    await Promise.all([loadCustomers(), viewCustomerDetails(state.selectedCustomerId)]);
}

async function restoreCustomer() {
    if (!state.selectedCustomerId) return;
    await api(`/api/admin/customer/${state.selectedCustomerId}/restore`, { method: "POST" });
    showToast("Customer restored");
    await Promise.all([loadCustomers(), viewCustomerDetails(state.selectedCustomerId)]);
}

async function openCustomerEditModal() {
    if (!state.selectedCustomerId) return;
    if (!state.currentCustomer || state.currentCustomer.customerID !== state.selectedCustomerId) {
        const payload = await api(`/api/admin/customer/${state.selectedCustomerId}`);
        state.currentCustomer = payload.data;
    }
    const c = state.currentCustomer;
    selectors.forms.customer.name.value = c.name || "";
    selectors.forms.customer.email.value = c.email || "";
    selectors.forms.customer.phone.value = c.phoneNumber || "";
    selectors.forms.customer.tier.value = c.loyaltyTier ?? "";
    selectors.forms.customer.membership.value = c.membership ? "1" : "0";
    selectors.forms.customer.discount.value = c.membershipDiscount ?? "";
    selectors.forms.customer.dueDate.value = toDatetimeLocal(c.membershipDueDate);
    selectors.forms.customer.password.value = "";
    openModal("customerEdit");
}

async function saveCustomerEdit() {
    if (!state.selectedCustomerId) return;
    const payload = {
        name: selectors.forms.customer.name.value.trim(),
        email: selectors.forms.customer.email.value.trim(),
        phoneNumber: selectors.forms.customer.phone.value.trim(),
        loyaltyTier: Number(selectors.forms.customer.tier.value || 0),
        membership: Number(selectors.forms.customer.membership.value || 0),
        membershipDiscount: Number(selectors.forms.customer.discount.value || 0),
        membershipDueDate: selectors.forms.customer.dueDate.value || null,
    };
    const password = selectors.forms.customer.password.value;
    if (password) payload.password = password;

    await api(`/api/admin/customer/${state.selectedCustomerId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
    });

    showToast("Customer updated");
    closeModal("customerEdit");
    await Promise.all([loadCustomers(), viewCustomerDetails(state.selectedCustomerId)]);
}

async function loadRestaurants() {
    const payload = await api("/api/admin/restaurants");
    state.allRestaurants = payload.data || [];
    renderRestaurantsTable();
}

function renderRestaurantsTable() {
    selectors.restaurantsTableBody.innerHTML = "";
    if (!state.allRestaurants.length) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="8" style="text-align:center;">No restaurants found</td>`;
        selectors.restaurantsTableBody.appendChild(tr);
        return;
    }

    for (const restaurant of state.allRestaurants) {
        const status = restaurant.isDeleted ? "Deleted" : (restaurant.isOpen ? "Open" : "Closed");
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${restaurant.restaurantID}</td>
            <td>${restaurant.name}</td>
            <td>${restaurant.city}</td>
            <td>${status}</td>
            <td>${restaurant.isVerified ? "Yes" : "No"}</td>
            <td>${restaurant.averageRating || "-"}</td>
            <td>${restaurant.isDeleted ? "Deleted" : "Active"}</td>
            <td><button onclick="viewRestaurantDetails(${restaurant.restaurantID})" type="button">View</button></td>
        `;
        selectors.restaurantsTableBody.appendChild(tr);
    }
}

async function viewRestaurantDetails(restaurantId) {
    const payload = await api(`/api/admin/restaurant/${restaurantId}`);
    const restaurant = payload.data;
    state.selectedRestaurantId = restaurantId;
    state.currentRestaurant = restaurant;

    const html = `
        <div class="detail-section">
            <h3>Restaurant Information</h3>
            <div class="detail-row"><div class="detail-label">ID:</div><div class="detail-value">#${restaurant.restaurantID}</div></div>
            <div class="detail-row"><div class="detail-label">Name:</div><div class="detail-value">${restaurant.name}</div></div>
            <div class="detail-row"><div class="detail-label">Email:</div><div class="detail-value">${restaurant.email}</div></div>
            <div class="detail-row"><div class="detail-label">Phone:</div><div class="detail-value">${restaurant.contactPhone || "-"}</div></div>
            <div class="detail-row"><div class="detail-label">City:</div><div class="detail-value">${restaurant.city}</div></div>
            <div class="detail-row"><div class="detail-label">Address:</div><div class="detail-value">${restaurant.addressLine || "-"}</div></div>
        </div>
        <div class="detail-section">
            <h3>Status</h3>
            <div class="detail-row"><div class="detail-label">Is Open:</div><div class="detail-value">${restaurant.isOpen ? "Yes" : "No"}</div></div>
            <div class="detail-row"><div class="detail-label">Is Verified:</div><div class="detail-value">${restaurant.isVerified ? "Yes" : "No"}</div></div>
            <div class="detail-row"><div class="detail-label">Rating:</div><div class="detail-value">${restaurant.averageRating || "-"}/5</div></div>
        </div>
    `;

    selectors.modalBodies.restaurant.innerHTML = html;
    selectors.modalBtns.restaurantDelete.style.display = restaurant.isDeleted ? "none" : "inline-block";
    selectors.modalBtns.restaurantRestore.style.display = restaurant.isDeleted ? "inline-block" : "none";
    selectors.modalBtns.restaurantEdit.style.display = restaurant.isDeleted ? "none" : "inline-block";
    openModal("restaurant");
}

async function deleteRestaurant() {
    if (!state.selectedRestaurantId) return;
    if (!window.confirm("Soft delete this restaurant?")) return;

    await api(`/api/admin/restaurant/${state.selectedRestaurantId}`, { method: "DELETE" });
    showToast("Restaurant deleted");
    await Promise.all([loadRestaurants(), viewRestaurantDetails(state.selectedRestaurantId)]);
}

async function restoreRestaurant() {
    if (!state.selectedRestaurantId) return;
    await api(`/api/admin/restaurant/${state.selectedRestaurantId}/restore`, { method: "POST" });
    showToast("Restaurant restored");
    await Promise.all([loadRestaurants(), viewRestaurantDetails(state.selectedRestaurantId)]);
}

async function openRestaurantEditModal() {
    if (!state.selectedRestaurantId) return;
    if (!state.currentRestaurant || state.currentRestaurant.restaurantID !== state.selectedRestaurantId) {
        const payload = await api(`/api/admin/restaurant/${state.selectedRestaurantId}`);
        state.currentRestaurant = payload.data;
    }
    const r = state.currentRestaurant;
    selectors.forms.restaurant.name.value = r.name || "";
    selectors.forms.restaurant.email.value = r.email || "";
    selectors.forms.restaurant.phone.value = r.contactPhone || "";
    selectors.forms.restaurant.city.value = r.city || "";
    selectors.forms.restaurant.zip.value = r.zipCode || "";
    selectors.forms.restaurant.address.value = r.addressLine || "";
    selectors.forms.restaurant.lat.value = r.latitude ?? "";
    selectors.forms.restaurant.lng.value = r.longitude ?? "";
    selectors.forms.restaurant.open.value = r.isOpen ? "1" : "0";
    selectors.forms.restaurant.verified.value = r.isVerified ? "1" : "0";
    selectors.forms.restaurant.rating.value = r.averageRating ?? "";
    selectors.forms.restaurant.password.value = "";
    openModal("restaurantEdit");
}

async function saveRestaurantEdit() {
    if (!state.selectedRestaurantId) return;
    const payload = {
        name: selectors.forms.restaurant.name.value.trim(),
        email: selectors.forms.restaurant.email.value.trim(),
        contactPhone: selectors.forms.restaurant.phone.value.trim(),
        city: selectors.forms.restaurant.city.value.trim(),
        zipCode: selectors.forms.restaurant.zip.value.trim(),
        addressLine: selectors.forms.restaurant.address.value.trim(),
        latitude: Number(selectors.forms.restaurant.lat.value || 0),
        longitude: Number(selectors.forms.restaurant.lng.value || 0),
        isOpen: Number(selectors.forms.restaurant.open.value || 0),
        isVerified: Number(selectors.forms.restaurant.verified.value || 0),
    };
    const password = selectors.forms.restaurant.password.value;
    if (password) payload.password = password;

    await api(`/api/admin/restaurant/${state.selectedRestaurantId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
    });

    showToast("Restaurant updated");
    closeModal("restaurantEdit");
    await Promise.all([loadRestaurants(), viewRestaurantDetails(state.selectedRestaurantId)]);
}

async function loadDeliveryPartners() {
    const payload = await api("/api/admin/delivery-partners");
    state.allDeliveryPartners = payload.data || [];
    renderDeliveryPartnersTable();
}

function renderDeliveryPartnersTable() {
    selectors.deliveryPartnersTableBody.innerHTML = "";
    if (!state.allDeliveryPartners.length) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="8" style="text-align:center;">No delivery partners found</td>`;
        selectors.deliveryPartnersTableBody.appendChild(tr);
        return;
    }

    for (const partner of state.allDeliveryPartners) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${partner.partnerID}</td>
            <td>${partner.name}</td>
            <td>${partner.phoneNumber || "-"}</td>
            <td>${partner.isOnline ? "Yes" : "No"}</td>
            <td>${partner.totalDeliveries || 0}</td>
            <td>${partner.averageRating || "-"}</td>
            <td>${partner.isDeleted ? "Deleted" : "Active"}</td>
            <td><button onclick="viewDeliveryDetails(${partner.partnerID})" type="button">View</button></td>
        `;
        selectors.deliveryPartnersTableBody.appendChild(tr);
    }
}

async function viewDeliveryDetails(partnerId) {
    const payload = await api(`/api/admin/delivery-partner/${partnerId}`);
    const partner = payload.data;
    state.selectedDeliveryId = partnerId;
    state.currentDelivery = partner;

    const html = `
        <div class="detail-section">
            <h3>Partner Information</h3>
            <div class="detail-row"><div class="detail-label">ID:</div><div class="detail-value">#${partner.partnerID}</div></div>
            <div class="detail-row"><div class="detail-label">Name:</div><div class="detail-value">${partner.name}</div></div>
            <div class="detail-row"><div class="detail-label">Email:</div><div class="detail-value">${partner.email}</div></div>
            <div class="detail-row"><div class="detail-label">Phone:</div><div class="detail-value">${partner.phoneNumber || "-"}</div></div>
        </div>
        <div class="detail-section">
            <h3>Status</h3>
            <div class="detail-row"><div class="detail-label">Is Online:</div><div class="detail-value">${partner.isOnline ? "Yes" : "No"}</div></div>
            <div class="detail-row"><div class="detail-label">Total Deliveries:</div><div class="detail-value">${partner.totalDeliveries || 0}</div></div>
            <div class="detail-row"><div class="detail-label">Average Rating:</div><div class="detail-value">${partner.averageRating || "-"}/5</div></div>
        </div>
    `;

    selectors.modalBodies.delivery.innerHTML = html;
    selectors.modalBtns.deliveryDelete.style.display = partner.isDeleted ? "none" : "inline-block";
    selectors.modalBtns.deliveryRestore.style.display = partner.isDeleted ? "inline-block" : "none";
    selectors.modalBtns.deliveryEdit.style.display = partner.isDeleted ? "none" : "inline-block";
    openModal("delivery");
}

async function deleteDeliveryPartner() {
    if (!state.selectedDeliveryId) return;
    if (!window.confirm("Soft delete this delivery partner?")) return;

    await api(`/api/admin/delivery-partner/${state.selectedDeliveryId}`, { method: "DELETE" });
    showToast("Delivery partner deleted");
    await Promise.all([loadDeliveryPartners(), viewDeliveryDetails(state.selectedDeliveryId)]);
}

async function restoreDeliveryPartner() {
    if (!state.selectedDeliveryId) return;
    await api(`/api/admin/delivery-partner/${state.selectedDeliveryId}/restore`, { method: "POST" });
    showToast("Delivery partner restored");
    await Promise.all([loadDeliveryPartners(), viewDeliveryDetails(state.selectedDeliveryId)]);
}

async function openDeliveryEditModal() {
    if (!state.selectedDeliveryId) return;
    if (!state.currentDelivery || state.currentDelivery.partnerID !== state.selectedDeliveryId) {
        const payload = await api(`/api/admin/delivery-partner/${state.selectedDeliveryId}`);
        state.currentDelivery = payload.data;
    }
    const d = state.currentDelivery;
    selectors.forms.delivery.name.value = d.name || "";
    selectors.forms.delivery.email.value = d.email || "";
    selectors.forms.delivery.phone.value = d.phoneNumber || "";
    selectors.forms.delivery.vehicle.value = d.vehicleNumber || "";
    selectors.forms.delivery.license.value = d.licenseID || "";
    selectors.forms.delivery.dob.value = d.dateOfBirth ? String(d.dateOfBirth).split("T")[0] : "";
    selectors.forms.delivery.lat.value = d.currentLatitude ?? "";
    selectors.forms.delivery.lng.value = d.currentLongitude ?? "";
    selectors.forms.delivery.online.value = d.isOnline ? "1" : "0";
    selectors.forms.delivery.rating.value = d.averageRating ?? "";
    selectors.forms.delivery.password.value = "";
    openModal("deliveryEdit");
}

async function saveDeliveryEdit() {
    if (!state.selectedDeliveryId) return;
    const payload = {
        name: selectors.forms.delivery.name.value.trim(),
        email: selectors.forms.delivery.email.value.trim(),
        phoneNumber: selectors.forms.delivery.phone.value.trim(),
        vehicleNumber: selectors.forms.delivery.vehicle.value.trim(),
        licenseID: selectors.forms.delivery.license.value.trim(),
        dateOfBirth: selectors.forms.delivery.dob.value || null,
        currentLatitude: Number(selectors.forms.delivery.lat.value || 0),
        currentLongitude: Number(selectors.forms.delivery.lng.value || 0),
        isOnline: Number(selectors.forms.delivery.online.value || 0),
    };
    const password = selectors.forms.delivery.password.value;
    if (password) payload.password = password;

    await api(`/api/admin/delivery-partner/${state.selectedDeliveryId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
    });

    showToast("Delivery partner updated");
    closeModal("deliveryEdit");
    await Promise.all([loadDeliveryPartners(), viewDeliveryDetails(state.selectedDeliveryId)]);
}

async function loadAudits() {
    const payload = await api("/api/admin/audits?limit=300");
    state.allAudits = payload.data || [];
    renderAuditsTable();
}

function renderAuditsTable() {
    selectors.auditsTableBody.innerHTML = "";
    if (!state.allAudits.length) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="8" style="text-align:center;">No audit records found</td>`;
        selectors.auditsTableBody.appendChild(tr);
        return;
    }

    for (const audit of state.allAudits) {
        const tr = document.createElement("tr");
        const detailsText = audit.details ? JSON.stringify(audit.details) : (audit.raw || "-");
        tr.innerHTML = `
            <td>${formatDate(audit.timestamp)}</td>
            <td>${audit.memberID ?? "-"}</td>
            <td>${audit.action || "-"}</td>
            <td>${audit.tableName || "-"}</td>
            <td>${audit.recordID || "-"}</td>
            <td>${audit.method || "-"}</td>
            <td>${audit.path || "-"}</td>
            <td title="${detailsText.replace(/\"/g, "&quot;")}">${detailsText}</td>
        `;
        selectors.auditsTableBody.appendChild(tr);
    }
}

async function handleLogout() {
    try {
        await api("/api/auth/logout", { method: "POST" });
    } catch {
        // ignore
    } finally {
        localStorage.removeItem("qb_token");
        localStorage.removeItem("qb_portal");
        window.location.href = "/admin";
    }
}

function bindEvents() {
    selectors.navLinks.forEach((link) => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            setTab(link.dataset.tab);
        });
    });

    selectors.refreshBtn.addEventListener("click", async () => {
        try {
            const results = await Promise.allSettled([
                loadOverview(),
                loadCustomers(),
                loadRestaurants(),
                loadDeliveryPartners(),
                loadAudits(),
            ]);
            for (const result of results) {
                if (result.status === "rejected" && isAuthError(result.reason)) {
                    throw result.reason;
                }
            }
            showToast("Dashboard refreshed");
        } catch (error) {
            if (isAuthError(error)) {
                localStorage.removeItem("qb_token");
                localStorage.removeItem("qb_portal");
                window.location.href = "/admin";
                return;
            }
            showToast(error.message || "Refresh failed", true);
        }
    });

    selectors.logoutBtn.addEventListener("click", handleLogout);
    selectors.overviewSearchBtn.addEventListener("click", filterOrders);
    selectors.overviewSearchInput.addEventListener("keyup", (e) => {
        if (e.key === "Enter") filterOrders();
    });

    selectors.loadCustomersBtn.addEventListener("click", () => loadCustomers().catch((e) => showToast(e.message, true)));
    selectors.loadRestaurantsBtn.addEventListener("click", () => loadRestaurants().catch((e) => showToast(e.message, true)));
    selectors.loadDeliveryPartnersBtn.addEventListener("click", () => loadDeliveryPartners().catch((e) => showToast(e.message, true)));
    selectors.refreshAuditsBtn.addEventListener("click", () => loadAudits().catch((e) => showToast(e.message, true)));

    selectors.modalBtns.customerEdit.addEventListener("click", () => openCustomerEditModal().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.customerDelete.addEventListener("click", () => deleteCustomer().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.customerRestore.addEventListener("click", () => restoreCustomer().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.restaurantEdit.addEventListener("click", () => openRestaurantEditModal().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.restaurantDelete.addEventListener("click", () => deleteRestaurant().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.restaurantRestore.addEventListener("click", () => restoreRestaurant().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.deliveryEdit.addEventListener("click", () => openDeliveryEditModal().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.deliveryDelete.addEventListener("click", () => deleteDeliveryPartner().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.deliveryRestore.addEventListener("click", () => restoreDeliveryPartner().catch((e) => showToast(e.message, true)));

    selectors.modalBtns.customerEditSave.addEventListener("click", () => saveCustomerEdit().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.restaurantEditSave.addEventListener("click", () => saveRestaurantEdit().catch((e) => showToast(e.message, true)));
    selectors.modalBtns.deliveryEditSave.addEventListener("click", () => saveDeliveryEdit().catch((e) => showToast(e.message, true)));

    document.querySelectorAll(".modal-close-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            const modal = e.target.closest(".modal");
            if (!modal) return;
            const modalKey = modal.dataset.modalKey;
            if (modalKey) closeModal(modalKey);
        });
    });

    Object.entries(selectors.modals).forEach(([modalKey, modal]) => {
        modal?.addEventListener("click", (e) => {
            if (e.target === modal) {
                closeModal(modalKey);
            }
        });
    });
}

async function bootstrap() {
    bindEvents();
    try {
        const ok = await ensureAdminAuth();
        if (!ok) return;

        const results = await Promise.allSettled([
            loadOverview(),
            loadCustomers(),
            loadRestaurants(),
            loadDeliveryPartners(),
            loadAudits(),
        ]);

        for (const result of results) {
            if (result.status === "rejected" && isAuthError(result.reason)) {
                throw result.reason;
            }
        }

        const failedCount = results.filter((r) => r.status === "rejected").length;
        if (failedCount > 0) {
            showToast(`Loaded with ${failedCount} non-fatal error(s)`, true);
        }
    } catch (error) {
        showToast(error.message || "Request failed", true);
        if (isAuthError(error)) {
            localStorage.removeItem("qb_token");
            localStorage.removeItem("qb_portal");
            setTimeout(() => {
                window.location.href = "/admin";
            }, 500);
        }
    }
}

window.viewOrderDetails = viewOrderDetails;
window.viewCustomerDetails = viewCustomerDetails;
window.viewRestaurantDetails = viewRestaurantDetails;
window.viewDeliveryDetails = viewDeliveryDetails;
window.closeModal = closeModal;

bootstrap();
