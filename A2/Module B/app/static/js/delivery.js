const state = {
    token: localStorage.getItem("qb_token") || null,
    user: null,
    partner: null,
    stats: null,
    liveOrders: [],
    activeOrder: null,
    activeAssignment: null,
    completedOrders: [],
    liveOrdersBlockedMessage: "",
    activeTab: "live",
    positionWatchId: null,
    locationPushAt: 0,
};

let fulfillmentMap = null;
let mapLayers = [];

const selectors = {
    navButtons: document.querySelectorAll(".nav-tab-btn"),
    featureCards: document.querySelectorAll(".feature-card"),
    tabPanes: {
        live: document.getElementById("tab-live"),
        fulfillment: document.getElementById("tab-fulfillment"),
        profile: document.getElementById("tab-profile"),
    },
    userChip: document.getElementById("delivery-user-chip"),
    refreshBtn: document.getElementById("delivery-refresh-btn"),
    logoutBtn: document.getElementById("delivery-logout-btn"),
    heroName: document.getElementById("delivery-hero-name"),
    heroEmail: document.getElementById("delivery-hero-email"),
    heroMetricRating: document.getElementById("hero-metric-rating"),
    heroMetricFulfilled: document.getElementById("hero-metric-fulfilled"),
    heroMetricActive: document.getElementById("hero-metric-active"),
    heroMetricLocation: document.getElementById("hero-metric-location"),
    reloadLiveOrdersBtn: document.getElementById("reload-live-orders-btn"),
    reloadActiveOrderBtn: document.getElementById("reload-active-order-btn"),
    activeOrderWarning: document.getElementById("active-order-warning"),
    liveOrdersBody: document.getElementById("delivery-live-orders-body"),
    completedOrdersBody: document.getElementById("delivery-completed-orders-body"),
    fulfillmentEmpty: document.getElementById("fulfillment-empty"),
    fulfillmentContent: document.getElementById("fulfillment-content"),
    fulfillmentRestaurantName: document.getElementById("fulfillment-restaurant-name"),
    fulfillmentRestaurantContact: document.getElementById("fulfillment-restaurant-contact"),
    fulfillmentRestaurantAddress: document.getElementById("fulfillment-restaurant-address"),
    fulfillmentCustomerName: document.getElementById("fulfillment-customer-name"),
    fulfillmentCustomerContact: document.getElementById("fulfillment-customer-contact"),
    fulfillmentCustomerAddress: document.getElementById("fulfillment-customer-address"),
    fulfillmentPaymentMode: document.getElementById("fulfillment-payment-mode"),
    fulfillmentPaymentStatus: document.getElementById("fulfillment-payment-status"),
    paymentCollectedBtn: document.getElementById("delivery-payment-collected-btn"),
    statusSelect: document.getElementById("delivery-status-select"),
    statusSaveBtn: document.getElementById("delivery-status-save-btn"),
    profileView: document.getElementById("delivery-profile-view"),
    profileForm: document.getElementById("delivery-profile-form"),
    profileDeleteBtn: document.getElementById("delivery-delete-profile-btn"),
    toast: document.getElementById("toast"),
};

function showToast(message, isError = false) {
    selectors.toast.textContent = message;
    selectors.toast.style.background = isError ? "#7f1d1d" : "#0f172a";
    selectors.toast.classList.remove("hidden");
    setTimeout(() => selectors.toast.classList.add("hidden"), 2500);
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
        throw new Error(payload.message || "Request failed");
    }

    return payload;
}

function switchTab(tabName) {
    state.activeTab = tabName;

    selectors.navButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.tab === tabName);
    });

    Object.entries(selectors.tabPanes).forEach(([name, pane]) => {
        pane.classList.toggle("active", name === tabName);
    });

    if (tabName === "fulfillment") {
        renderFulfillmentMap();
    }
}

function renderHero() {
    if (!state.partner) {
        return;
    }

    selectors.heroName.textContent = `Welcome, ${state.partner.name}`;
    selectors.heroEmail.textContent = `Email: ${state.partner.email}`;
    selectors.heroMetricRating.textContent = `Avg Rating: ${state.partner.averageRating || "-"}`;
    selectors.heroMetricFulfilled.textContent = `Orders Fulfilled: ${state.stats?.deliveredAssignments || 0}`;
    selectors.heroMetricActive.textContent = `Active Orders: ${state.stats?.activeAssignments || 0}`;
    selectors.heroMetricLocation.textContent = `Live Location: ${state.partner.currentLatitude}, ${state.partner.currentLongitude}`;
}

function renderLiveOrders() {
    selectors.liveOrdersBody.innerHTML = "";

    if (state.liveOrdersBlockedMessage) {
        selectors.activeOrderWarning.classList.remove("hidden");
        selectors.activeOrderWarning.textContent = state.liveOrdersBlockedMessage;
        const row = document.createElement("tr");
        row.innerHTML = '<td colspan="7">To view live orders, set isOnline to true.</td>';
        selectors.liveOrdersBody.appendChild(row);
        return;
    }

    if (state.activeAssignment) {
        selectors.activeOrderWarning.classList.remove("hidden");
        selectors.activeOrderWarning.textContent = `Active assignment #${state.activeAssignment.AssignmentID} is in progress. Finish it before taking another order.`;
    } else {
        selectors.activeOrderWarning.classList.add("hidden");
        selectors.activeOrderWarning.textContent = "";
    }

    for (const order of state.liveOrders) {
        const row = document.createElement("tr");
        const acceptBlocked = state.activeAssignment || order.orderStatus !== "ReadyForPickup";
        const disabled = acceptBlocked ? "disabled" : "";
        const buttonText = order.orderStatus === "ReadyForPickup" ? "Accept" : "Waiting";
        row.innerHTML = `
            <td>#${order.orderID}<br /><small>${order.orderStatus}</small></td>
            <td>${order.restaurantName}<br /><small>${order.restaurantAddress}, ${order.restaurantCity}</small></td>
            <td>${order.customerName}<br /><small>${order.customerAddress}, ${order.customerCity}</small></td>
            <td>Rs ${order.totalAmount}</td>
            <td>${new Date(order.estimatedTime).toLocaleString()}</td>
            <td>${order.pickupDistanceScore}</td>
            <td><button type="button" data-accept-order="${order.orderID}" ${disabled}>${buttonText}</button></td>
        `;
        selectors.liveOrdersBody.appendChild(row);
    }

    if (!state.liveOrders.length) {
        const row = document.createElement("tr");
        row.innerHTML = '<td colspan="7">No live orders available right now.</td>';
        selectors.liveOrdersBody.appendChild(row);
    }
}

function renderCompletedOrders() {
    selectors.completedOrdersBody.innerHTML = "";
    for (const rowData of state.completedOrders) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>#${rowData.AssignmentID}</td>
            <td>#${rowData.OrderID}</td>
            <td>${rowData.restaurantName}</td>
            <td>${rowData.customerName}</td>
            <td>Rs ${rowData.totalAmount}</td>
            <td>${new Date(rowData.deliveryTime).toLocaleString()}</td>
        `;
        selectors.completedOrdersBody.appendChild(row);
    }

    if (!state.completedOrders.length) {
        const row = document.createElement("tr");
        row.innerHTML = '<td colspan="6">No completed orders yet.</td>';
        selectors.completedOrdersBody.appendChild(row);
    }
}

function renderFulfillment() {
    if (!state.activeOrder) {
        selectors.fulfillmentEmpty.classList.remove("hidden");
        selectors.fulfillmentContent.classList.add("hidden");
        return;
    }

    selectors.fulfillmentEmpty.classList.add("hidden");
    selectors.fulfillmentContent.classList.remove("hidden");

    const order = state.activeOrder;
    selectors.fulfillmentRestaurantName.textContent = order.restaurantName;
    selectors.fulfillmentRestaurantContact.textContent = `Phone: ${order.restaurantPhone} | Email: ${order.restaurantEmail || "-"}`;
    selectors.fulfillmentRestaurantAddress.textContent = `${order.restaurantAddress}, ${order.restaurantCity} ${order.restaurantZip}`;

    selectors.fulfillmentCustomerName.textContent = order.customerName;
    selectors.fulfillmentCustomerContact.textContent = `Phone: ${order.customerPhone} | Email: ${order.customerEmail}`;
    selectors.fulfillmentCustomerAddress.textContent = `${order.customerAddress}, ${order.customerCity} ${order.customerZip}`;

    selectors.fulfillmentPaymentMode.textContent = `Mode: ${order.paymentType || "-"}`;
    selectors.fulfillmentPaymentStatus.textContent = `Status: ${order.paymentStatus || "-"}`;
    const showCODCollect = order.paymentType === "COD" && order.paymentStatus !== "Success";
    selectors.paymentCollectedBtn.classList.toggle("hidden", !showCODCollect);
    const isCODPendingCollection = order.paymentType === "COD" && order.paymentStatus !== "Success";

    selectors.statusSelect.value = "Delivered";
    selectors.statusSaveBtn.disabled = order.orderStatus === "Delivered" || order.orderStatus !== "OutForDelivery" || isCODPendingCollection;
    selectors.statusSaveBtn.title = isCODPendingCollection ? "Collect COD payment before marking Delivered" : "";

    renderFulfillmentMap();
}

function ensureMap() {
    if (fulfillmentMap || typeof L === "undefined") {
        return;
    }

    fulfillmentMap = L.map("fulfillment-map").setView([23.0225, 72.5714], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19,
    }).addTo(fulfillmentMap);
}

function renderFulfillmentMap() {
    if (!state.activeOrder) {
        return;
    }
    ensureMap();
    if (!fulfillmentMap) {
        return;
    }

    for (const layer of mapLayers) {
        fulfillmentMap.removeLayer(layer);
    }
    mapLayers = [];

    const pickup = [Number(state.activeOrder.restaurantLatitude), Number(state.activeOrder.restaurantLongitude)];
    const drop = [Number(state.activeOrder.customerLatitude), Number(state.activeOrder.customerLongitude)];

    const pickupMarker = L.marker(pickup).bindPopup("Pickup").addTo(fulfillmentMap);
    const dropMarker = L.marker(drop).bindPopup("Delivery").addTo(fulfillmentMap);
    const routeLine = L.polyline([pickup, drop], { color: "#16a34a", weight: 5 }).addTo(fulfillmentMap);

    mapLayers.push(pickupMarker, dropMarker, routeLine);
    fulfillmentMap.fitBounds(routeLine.getBounds(), { padding: [28, 28] });
}

function renderProfile() {
    if (!state.partner) {
        return;
    }

    selectors.profileView.innerHTML = `
        <dt>Partner ID</dt><dd>${state.partner.partnerID}</dd>
        <dt>Name</dt><dd>${state.partner.name}</dd>
        <dt>Email</dt><dd>${state.partner.email}</dd>
        <dt>Phone</dt><dd>${state.partner.phoneNumber}</dd>
        <dt>Vehicle Number</dt><dd>${state.partner.vehicleNumber}</dd>
        <dt>License ID</dt><dd>${state.partner.licenseID}</dd>
        <dt>Date of Birth</dt><dd>${state.partner.dateOfBirth}</dd>
        <dt>Average Rating</dt><dd>${state.partner.averageRating || "-"}</dd>
        <dt>Online</dt><dd>${state.partner.isOnline ? "Yes" : "No"}</dd>
        <dt>Current Latitude</dt><dd>${state.partner.currentLatitude}</dd>
        <dt>Current Longitude</dt><dd>${state.partner.currentLongitude}</dd>
    `;
}

async function loadProfileAndStats() {
    const payload = await api("/api/delivery/me");
    state.partner = payload.data.partner;
    state.stats = payload.data.stats;
    state.activeAssignment = payload.data.activeAssignment;
    renderHero();
    renderProfile();
}

async function loadLiveOrders() {
    const payload = await api("/api/delivery/live-orders");
    state.liveOrders = payload.data.orders || [];
    state.liveOrdersBlockedMessage = payload.data?.canViewLiveOrders === false
        ? (payload.message || "To view live orders, set isOnline to true.")
        : "";
    state.activeAssignment = payload.data?.activeAssignment ?? null;
    renderLiveOrders();
}

async function loadActiveOrder() {
    const payload = await api("/api/delivery/active-order");
    if (!payload.data.active) {
        state.activeOrder = null;
        state.activeAssignment = null;
    } else {
        state.activeOrder = payload.data.order;
        state.activeAssignment = payload.data.assignment;
    }
    renderFulfillment();
}

async function loadCompletedOrders() {
    const payload = await api("/api/delivery/completed-orders");
    state.completedOrders = payload.data || [];
    renderCompletedOrders();
}

async function loadAll() {
    await loadProfileAndStats();
    await Promise.all([loadLiveOrders(), loadActiveOrder(), loadCompletedOrders()]);
}

async function ensureDeliveryAuth() {
    if (!state.token) {
        window.location.href = "/";
        return false;
    }

    const mePayload = await api("/api/auth/me");
    state.user = mePayload.data;

    const roles = state.user.roles || [];
    if (!roles.includes("DeliveryPartner") && !roles.includes("Admin")) {
        showToast("Delivery access denied", true);
        window.location.href = "/";
        return false;
    }

    selectors.userChip.textContent = state.user.name;
    return true;
}

async function handleAcceptOrder(orderID) {
    try {
        await api(`/api/delivery/orders/${orderID}/accept`, { method: "POST" });
        showToast(`Order ${orderID} accepted`);
        switchTab("fulfillment");
        await loadAll();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleLiveOrderActions(event) {
    const orderID = event.target.dataset.acceptOrder;
    if (!orderID) {
        return;
    }
    await handleAcceptOrder(Number(orderID));
}

async function handleSaveStatus() {
    if (!state.activeOrder) {
        showToast("No active order", true);
        return;
    }

    if (state.activeOrder.paymentType === "COD" && state.activeOrder.paymentStatus !== "Success") {
        showToast("Collect COD payment before marking Delivered", true);
        return;
    }

    try {
        await api(`/api/delivery/orders/${state.activeOrder.orderID}/status`, {
            method: "PUT",
            body: JSON.stringify({ orderStatus: selectors.statusSelect.value }),
        });
        showToast("Order status updated");
        await loadAll();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handlePaymentCollected() {
    if (!state.activeOrder) {
        showToast("No active order", true);
        return;
    }

    try {
        await api(`/api/delivery/orders/${state.activeOrder.orderID}/payment-collected`, {
            method: "PUT",
        });
        showToast("COD payment marked as collected");
        await loadAll();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleProfileUpdate(event) {
    event.preventDefault();
    const formData = new FormData(event.target);

    const payload = {};
    const stringFields = ["name", "email", "phoneNumber", "password", "vehicleNumber", "licenseID"];
    for (const field of stringFields) {
        const value = String(formData.get(field) || "").trim();
        if (value) {
            payload[field] = value;
        }
    }

    const isOnlineChoice = String(formData.get("isOnlineChoice") || "").trim();
    if (isOnlineChoice !== "") {
        payload.isOnline = isOnlineChoice === "true";
    }

    if (Object.keys(payload).length === 0) {
        showToast("No fields to update", true);
        return;
    }

    try {
        await api("/api/delivery/profile", {
            method: "PUT",
            body: JSON.stringify(payload),
        });
        showToast("Profile updated");
        await loadProfileAndStats();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleDeleteProfile() {
    if (!window.confirm("Delete your delivery partner profile?")) {
        return;
    }

    try {
        await api("/api/delivery/profile", { method: "DELETE" });
        localStorage.removeItem("qb_token");
        localStorage.removeItem("qb_portal");
        showToast("Profile deleted");
        window.location.href = "/";
    } catch (error) {
        showToast(error.message, true);
    }
}

function getLocationErrorMessage(error) {
    if (!error) return "Unable to detect location";
    if (error.code === error.PERMISSION_DENIED) return "Location permission denied";
    if (error.code === error.POSITION_UNAVAILABLE) return "Location unavailable";
    if (error.code === error.TIMEOUT) return "Location timeout";
    return "Unable to detect location";
}

async function pushLiveLocation(latitude, longitude) {
    const now = Date.now();
    if (now - state.locationPushAt < 1500) {
        return;
    }
    state.locationPushAt = now;

    try {
        await api("/api/delivery/location", {
            method: "PUT",
            body: JSON.stringify({
                latitude,
                longitude,
                isOnline: Boolean(state.partner?.isOnline),
            }),
        });
    } catch (error) {
        // Keep tracker running even if a periodic update fails.
    }
}

function startLocationTracking() {
    if (!navigator.geolocation) {
        showToast("Geolocation not supported", true);
        return;
    }

    if (state.positionWatchId !== null) {
        return;
    }

    state.positionWatchId = navigator.geolocation.watchPosition(
        (position) => {
            const lat = Number(position.coords.latitude);
            const lng = Number(position.coords.longitude);
            selectors.heroMetricLocation.textContent = `Live Location: ${lat}, ${lng}`;
            pushLiveLocation(lat, lng);
        },
        (error) => {
            showToast(getLocationErrorMessage(error), true);
        },
        {
            enableHighAccuracy: true,
            timeout: 12000,
            maximumAge: 2000,
        },
    );
}

async function handleLogout() {
    try {
        await api("/api/auth/logout", { method: "POST" });
    } catch (error) {
        showToast(error.message, true);
    } finally {
        localStorage.removeItem("qb_token");
        localStorage.removeItem("qb_portal");
        window.location.href = "/";
    }
}

function bindEvents() {
    selectors.navButtons.forEach((button) => {
        button.addEventListener("click", () => switchTab(button.dataset.tab));
    });

    selectors.featureCards.forEach((card) => {
        card.addEventListener("click", () => switchTab(card.dataset.tab));
    });

    selectors.refreshBtn.addEventListener("click", async () => {
        try {
            await loadAll();
            showToast("Dashboard refreshed");
        } catch (error) {
            showToast(error.message, true);
        }
    });

    selectors.logoutBtn.addEventListener("click", handleLogout);
    selectors.reloadLiveOrdersBtn.addEventListener("click", () => loadLiveOrders().catch((error) => showToast(error.message, true)));
    selectors.reloadActiveOrderBtn.addEventListener("click", () => loadActiveOrder().catch((error) => showToast(error.message, true)));
    selectors.liveOrdersBody.addEventListener("click", handleLiveOrderActions);
    selectors.statusSaveBtn.addEventListener("click", handleSaveStatus);
    selectors.paymentCollectedBtn.addEventListener("click", handlePaymentCollected);
    selectors.profileForm.addEventListener("submit", handleProfileUpdate);
    selectors.profileDeleteBtn.addEventListener("click", handleDeleteProfile);
}

async function bootstrap() {
    bindEvents();

    try {
        const allowed = await ensureDeliveryAuth();
        if (!allowed) {
            return;
        }
        await loadAll();
        startLocationTracking();
    } catch (error) {
        showToast(error.message, true);
        window.location.href = "/";
    }
}

bootstrap();
