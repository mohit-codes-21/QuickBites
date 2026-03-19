const state = {
    token: localStorage.getItem("qb_token") || null,
    user: null,
    restaurant: null,
    stats: null,
    menu: [],
    orders: [],
    activeTab: "overview",
};

let restaurantProfileMap = null;
let restaurantProfileMarker = null;

const ORDER_STATUS = ["Preparing", "ReadyForPickup"];

const selectors = {
    navButtons: document.querySelectorAll(".nav-tab-btn"),
    featureCards: document.querySelectorAll(".feature-card"),
    tabPanes: {
        overview: document.getElementById("tab-overview"),
        menu: document.getElementById("tab-menu"),
        orders: document.getElementById("tab-orders"),
        profile: document.getElementById("tab-profile"),
    },
    userChip: document.getElementById("restaurant-user-chip"),
    refreshBtn: document.getElementById("restaurant-refresh-btn"),
    logoutBtn: document.getElementById("restaurant-logout-btn"),
    heroName: document.getElementById("restaurant-hero-name"),
    heroAddress: document.getElementById("restaurant-hero-address"),
    heroMetricRating: document.getElementById("hero-metric-rating"),
    heroMetricOpen: document.getElementById("hero-metric-open"),
    heroMetricVerified: document.getElementById("hero-metric-verified"),
    heroMetricCity: document.getElementById("hero-metric-city"),
    statMenuTotal: document.getElementById("stat-menu-total"),
    statMenuAvailable: document.getElementById("stat-menu-available"),
    statOrderTotal: document.getElementById("stat-order-total"),
    statOrderProgress: document.getElementById("stat-order-progress"),
    statOrderDelivered: document.getElementById("stat-order-delivered"),
    reloadMenuBtn: document.getElementById("reload-menu-btn"),
    menuBody: document.getElementById("restaurant-menu-body"),
    addMenuForm: document.getElementById("restaurant-add-menu-form"),
    updateMenuForm: document.getElementById("restaurant-update-menu-form"),
    reloadOrdersBtn: document.getElementById("reload-orders-btn"),
    ordersBody: document.getElementById("restaurant-orders-body"),
    profileView: document.getElementById("restaurant-profile-view"),
    profileForm: document.getElementById("restaurant-profile-form"),
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

    if (tabName === "profile") {
        ensureProfileMapReady();
    }
}

function ensureProfileMapReady() {
    if (!selectors.tabPanes.profile) {
        return;
    }

    if (typeof L === "undefined") {
        return;
    }

    if (!restaurantProfileMap) {
        const mapContainer = document.getElementById("restaurant-address-map");
        if (!mapContainer) {
            return;
        }

        restaurantProfileMap = L.map("restaurant-address-map").setView([23.0225, 72.5714], 13);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap contributors",
            maxZoom: 19,
        }).addTo(restaurantProfileMap);

        restaurantProfileMap.on("click", (e) => {
            const { lat, lng } = e.latlng;
            setRestaurantProfileMarker(lat, lng);
        });
    }

    setTimeout(() => {
        restaurantProfileMap.invalidateSize();
        if (state.restaurant?.latitude != null && state.restaurant?.longitude != null) {
            setRestaurantProfileMarker(Number(state.restaurant.latitude), Number(state.restaurant.longitude), false);
        }
    }, 120);
}

function setRestaurantProfileMarker(lat, lng, center = true) {
    const latInput = document.getElementById("restaurant-profile-latitude");
    const lngInput = document.getElementById("restaurant-profile-longitude");

    if (latInput) latInput.value = String(lat);
    if (lngInput) lngInput.value = String(lng);

    if (!restaurantProfileMap) {
        return;
    }

    if (restaurantProfileMarker) {
        restaurantProfileMap.removeLayer(restaurantProfileMarker);
    }

    restaurantProfileMarker = L.marker([lat, lng]).addTo(restaurantProfileMap);
    if (center) {
        restaurantProfileMap.setView([lat, lng], 15);
    }
}

function clearRestaurantProfileMarker() {
    if (restaurantProfileMarker && restaurantProfileMap) {
        restaurantProfileMap.removeLayer(restaurantProfileMarker);
        restaurantProfileMarker = null;
    }
}

function getLocationErrorMessage(error) {
    if (error.code === error.NETWORK_ERROR) {
        return "Network error. Please check your internet connection.";
    }
    if (error.code === error.PERMISSION_DENIED) {
        return "Location permission denied. Please allow location access in your browser settings.";
    }
    if (error.code === error.POSITION_UNAVAILABLE) {
        return "Location information is unavailable in your area.";
    }
    if (error.code === error.TIMEOUT) {
        return "Location request timed out. Try again.";
    }
    return "Unable to detect location.";
}

function setRestaurantProfileGeolocation() {
    if (!navigator.geolocation) {
        showToast("Geolocation is not supported by your browser", true);
        return;
    }

    navigator.geolocation.getCurrentPosition(
        (position) => {
            setRestaurantProfileMarker(Number(position.coords.latitude), Number(position.coords.longitude));
            showToast("Location detected successfully");
        },
        (error) => {
            showToast(getLocationErrorMessage(error), true);
        },
        {
            enableHighAccuracy: true,
            timeout: 12000,
            maximumAge: 60000,
        },
    );
}

function renderHero() {
    if (!state.restaurant) {
        return;
    }

    selectors.heroName.textContent = state.restaurant.name;
    selectors.heroAddress.textContent = `${state.restaurant.addressLine}, ${state.restaurant.city} ${state.restaurant.zipCode}`;
    selectors.heroMetricRating.textContent = `Rating: ${state.restaurant.averageRating || "-"}`;
    selectors.heroMetricOpen.textContent = `Open: ${state.restaurant.isOpen ? "Yes" : "No"}`;
    selectors.heroMetricVerified.textContent = `Verified: ${state.restaurant.isVerified ? "Yes" : "No"}`;
    selectors.heroMetricCity.textContent = `City: ${state.restaurant.city}`;
}

function renderStats() {
    const menuStats = state.stats?.menu || { totalItems: 0, availableItems: 0 };
    const orderStats = state.stats?.orders || {
        totalOrders: 0,
        createdOrders: 0,
        preparingOrders: 0,
        readyOrders: 0,
        outOrders: 0,
        deliveredOrders: 0,
    };

    selectors.statMenuTotal.textContent = String(menuStats.totalItems || 0);
    selectors.statMenuAvailable.textContent = String(menuStats.availableItems || 0);
    selectors.statOrderTotal.textContent = String(orderStats.totalOrders || 0);
    const progress = Number(orderStats.createdOrders || 0)
        + Number(orderStats.preparingOrders || 0)
        + Number(orderStats.readyOrders || 0)
        + Number(orderStats.outOrders || 0);
    selectors.statOrderProgress.textContent = String(progress);
    selectors.statOrderDelivered.textContent = String(orderStats.deliveredOrders || 0);
}

function renderMenu() {
    selectors.menuBody.innerHTML = "";

    for (const item of state.menu) {
        const discontinued = Boolean(item.discontinued);
        const actionButton = discontinued
            ? `<button class="btn-secondary" type="button" data-restore-item="${item.itemID}">Re-enable</button>`
            : `<button class="btn-danger" type="button" data-delete-item="${item.itemID}">Discontinue</button>`;

        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${item.itemID}</td>
            <td>${item.name}</td>
            <td>${item.menuCategory || "-"}</td>
            <td>${item.appPrice}</td>
            <td>${item.restaurantPrice ?? "-"}</td>
            <td>${item.preparationTime ?? "-"}</td>
            <td>${item.isVegetarian ? "Yes" : "No"}</td>
            <td>${item.isAvailable ? "Yes" : "No"}</td>
            <td><span class="status-pill ${discontinued ? "status-pill-off" : "status-pill-on"}">${discontinued ? "Yes" : "No"}</span></td>
            <td>
                ${actionButton}
            </td>
        `;
        selectors.menuBody.appendChild(row);
    }
}

function formatDate(value) {
    if (!value) {
        return "-";
    }
    return new Date(value).toLocaleString();
}

function formatItems(items) {
    if (!items || items.length === 0) {
        return "-";
    }

    return `<div class="order-items-list">${items
        .map((item) => `<span>${item.itemName} x ${item.quantity} (Rs ${item.priceAtPurchase})</span>`)
        .join("")}</div>`;
}

function formatAssignment(order) {
    if (!order.AssignmentID) {
        return "Not assigned";
    }

    return `
        <div class="order-items-list">
            <span>ID: ${order.AssignmentID}</span>
            <span>Partner: ${order.PartnerID || "-"}</span>
            <span>Accepted: ${formatDate(order.acceptanceTime)}</span>
            <span>Pickup: ${formatDate(order.pickupTime)}</span>
            <span>Delivered: ${formatDate(order.deliveryTime)}</span>
        </div>
    `;
}

function renderOrders() {
    selectors.ordersBody.innerHTML = "";

    for (const order of state.orders) {
        const baseOptions = ORDER_STATUS
            .map((status) => `<option value="${status}" ${status === order.orderStatus ? "selected" : ""}>${status}</option>`)
            .join("");
        const statusLockedForRestaurant = order.orderStatus === "OutForDelivery" || order.orderStatus === "Delivered";
        const options = ORDER_STATUS.includes(order.orderStatus)
            ? baseOptions
            : `<option value="${order.orderStatus}" selected disabled>Current: ${order.orderStatus}</option>${baseOptions}`;
        const saveDisabled = statusLockedForRestaurant ? "disabled" : "";

        const row = document.createElement("tr");
        row.innerHTML = `
            <td>#${order.orderID}<br /><small>Address ID: ${order.addressID}</small></td>
            <td>${formatDate(order.orderTime)}</td>
            <td>${order.customerID}</td>
            <td>Rs ${order.totalAmount}</td>
            <td>${order.paymentStatus || "-"}</td>
            <td>${formatItems(order.items)}</td>
            <td>${formatAssignment(order)}</td>
            <td>
                <div class="order-status-row">
                    <select data-order-status-select="${order.orderID}" ${saveDisabled}>${options}</select>
                    <button type="button" data-order-status-save="${order.orderID}" ${saveDisabled}>Save</button>
                </div>
            </td>
        `;
        selectors.ordersBody.appendChild(row);
    }
}

function renderProfile() {
    if (!state.restaurant) {
        return;
    }

    selectors.profileView.innerHTML = `
        <dt>Restaurant ID</dt><dd>${state.restaurant.restaurantID}</dd>
        <dt>Name</dt><dd>${state.restaurant.name}</dd>
        <dt>Contact</dt><dd>${state.restaurant.contactPhone}</dd>
        <dt>Email</dt><dd>${state.restaurant.email}</dd>
        <dt>Rating</dt><dd>${state.restaurant.averageRating || "-"}</dd>
        <dt>Open</dt><dd>${state.restaurant.isOpen ? "Yes" : "No"}</dd>
        <dt>Verified</dt><dd>${state.restaurant.isVerified ? "Yes" : "No"}</dd>
        <dt>City</dt><dd>${state.restaurant.city}</dd>
        <dt>Address</dt><dd>${state.restaurant.addressLine}</dd>
        <dt>Zip</dt><dd>${state.restaurant.zipCode}</dd>
        <dt>Latitude</dt><dd>${state.restaurant.latitude}</dd>
        <dt>Longitude</dt><dd>${state.restaurant.longitude}</dd>
        <dt>Discontinued</dt><dd>${state.restaurant.discontinued ? "Yes" : "No"}</dd>
    `;

    const latInput = document.getElementById("restaurant-profile-latitude");
    const lngInput = document.getElementById("restaurant-profile-longitude");
    if (latInput && (latInput.value === "" || !Number.isFinite(Number(latInput.value)))) {
        latInput.value = state.restaurant.latitude ?? "";
    }
    if (lngInput && (lngInput.value === "" || !Number.isFinite(Number(lngInput.value)))) {
        lngInput.value = state.restaurant.longitude ?? "";
    }

    if (restaurantProfileMap && state.restaurant.latitude != null && state.restaurant.longitude != null) {
        setRestaurantProfileMarker(Number(state.restaurant.latitude), Number(state.restaurant.longitude), false);
    }
}

async function loadRestaurantProfile() {
    const payload = await api("/api/restaurant/me");
    state.restaurant = payload.data.restaurant;
    state.stats = payload.data.stats;
    renderHero();
    renderStats();
    renderProfile();
}

async function loadMenu() {
    const payload = await api(`/api/menu-items?restaurantID=${state.restaurant.restaurantID}&includeDiscontinued=true`);
    state.menu = payload.data;
    renderMenu();
}

async function loadOrders() {
    const payload = await api("/api/restaurant/orders");
    state.orders = payload.data.orders || [];
    renderOrders();
}

async function loadAll() {
    await loadRestaurantProfile();
    await Promise.all([loadMenu(), loadOrders()]);
}

async function ensureRestaurantAuth() {
    if (!state.token) {
        window.location.href = "/";
        return false;
    }

    const mePayload = await api("/api/auth/me");
    state.user = mePayload.data;

    const roles = state.user.roles || [];
    if (!roles.includes("RestaurantManager") && !roles.includes("Admin")) {
        showToast("Restaurant access denied", true);
        window.location.href = "/";
        return false;
    }

    selectors.userChip.textContent = state.user.name;
    return true;
}

async function handleAddMenuItem(event) {
    event.preventDefault();
    const formData = new FormData(event.target);

    const payload = {
        restaurantID: Number(state.restaurant.restaurantID),
        name: String(formData.get("name") || "").trim(),
        description: String(formData.get("description") || "").trim() || null,
        menuCategory: String(formData.get("menuCategory") || "").trim() || null,
        restaurantPrice: Number(formData.get("restaurantPrice")),
        isVegetarian: String(formData.get("isVegetarian")) === "true",
        preparationTime: Number(formData.get("preparationTime")),
        isAvailable: String(formData.get("isAvailable")) === "true",
    };

    try {
        await api("/api/menu-items", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        event.target.reset();
        showToast("Menu item added");
        await Promise.all([loadMenu(), loadRestaurantProfile()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleUpdateMenuItem(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const itemID = Number(formData.get("itemID"));

    if (!itemID) {
        showToast("itemID is required", true);
        return;
    }

    const payload = {};
    const name = String(formData.get("name") || "").trim();
    const description = String(formData.get("description") || "").trim();
    const category = String(formData.get("menuCategory") || "").trim();
    const restaurantPrice = String(formData.get("restaurantPrice") || "").trim();
    const prepTime = String(formData.get("preparationTime") || "").trim();

    if (name) payload.name = name;
    if (description) payload.description = description;
    if (category) payload.menuCategory = category;
    if (restaurantPrice) payload.restaurantPrice = Number(restaurantPrice);
    if (prepTime) payload.preparationTime = Number(prepTime);

    const isVegChoice = String(formData.get("isVegetarian") || "").trim();
    const isAvailableChoice = String(formData.get("isAvailable") || "").trim();
    if (isVegChoice !== "") {
        payload.isVegetarian = isVegChoice === "true";
    }
    if (isAvailableChoice !== "") {
        payload.isAvailable = isAvailableChoice === "true";
    }

    if (Object.keys(payload).length === 0) {
        showToast("Provide at least one field to update", true);
        return;
    }

    try {
        await api(`/api/menu-items/${state.restaurant.restaurantID}/${itemID}`, {
            method: "PUT",
            body: JSON.stringify(payload),
        });
        showToast("Menu item updated");
        await loadMenu();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleMenuActions(event) {
    const deleteItemID = event.target.dataset.deleteItem;
    const restoreItemID = event.target.dataset.restoreItem;

    if (!deleteItemID && !restoreItemID) {
        return;
    }

    if (deleteItemID) {
        if (!window.confirm(`Discontinue menu item ${deleteItemID}?`)) {
            return;
        }

        try {
            await api(`/api/menu-items/${state.restaurant.restaurantID}/${Number(deleteItemID)}`, {
                method: "DELETE",
            });
            showToast("Menu item marked as discontinued");
            await Promise.all([loadMenu(), loadRestaurantProfile()]);
        } catch (error) {
            showToast(error.message, true);
        }
        return;
    }

    if (restoreItemID) {
        try {
            await api(`/api/menu-items/${state.restaurant.restaurantID}/${Number(restoreItemID)}/restore`, {
                method: "POST",
            });
            showToast("Menu item re-enabled");
            await Promise.all([loadMenu(), loadRestaurantProfile()]);
        } catch (error) {
            showToast(error.message, true);
        }
    }
}

async function handleOrderStatusSave(orderID) {
    const select = document.querySelector(`[data-order-status-select="${orderID}"]`);
    if (!select) {
        return;
    }

    try {
        await api(`/api/restaurant/orders/${orderID}/status`, {
            method: "PUT",
            body: JSON.stringify({ orderStatus: select.value }),
        });
        showToast("Order status updated");
        await Promise.all([loadOrders(), loadRestaurantProfile()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleOrdersActions(event) {
    const saveOrderID = event.target.dataset.orderStatusSave;
    if (!saveOrderID) {
        return;
    }
    await handleOrderStatusSave(Number(saveOrderID));
}

async function handleProfileUpdate(event) {
    event.preventDefault();
    const formData = new FormData(event.target);

    const payload = {};
    const stringFields = ["name", "contactPhone", "addressLine", "city", "zipCode", "email"];
    for (const field of stringFields) {
        const value = String(formData.get(field) || "").trim();
        if (value) {
            payload[field] = value;
        }
    }

    const newPassword = String(formData.get("password") || "").trim();
    if (newPassword) {
        payload.password = newPassword;
    }

    const latitude = String(formData.get("latitude") || "").trim();
    const longitude = String(formData.get("longitude") || "").trim();
    if (latitude) payload.latitude = Number(latitude);
    if (longitude) payload.longitude = Number(longitude);

    const isOpenChoice = String(formData.get("isOpenChoice") || "").trim();
    if (isOpenChoice !== "") {
        payload.isOpen = isOpenChoice === "true";
    }

    if (Object.keys(payload).length === 0) {
        showToast("No profile fields to update", true);
        return;
    }

    try {
        await api("/api/restaurant/me", {
            method: "PUT",
            body: JSON.stringify(payload),
        });
        showToast("Restaurant profile updated");
        await loadRestaurantProfile();
    } catch (error) {
        showToast(error.message, true);
    }
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
    selectors.reloadMenuBtn.addEventListener("click", () => loadMenu().catch((error) => showToast(error.message, true)));
    selectors.reloadOrdersBtn.addEventListener("click", () => loadOrders().catch((error) => showToast(error.message, true)));

    selectors.addMenuForm.addEventListener("submit", handleAddMenuItem);
    selectors.updateMenuForm.addEventListener("submit", handleUpdateMenuItem);
    selectors.menuBody.addEventListener("click", handleMenuActions);
    selectors.ordersBody.addEventListener("click", handleOrdersActions);
    selectors.profileForm.addEventListener("submit", handleProfileUpdate);

    const geolocationBtn = document.getElementById("restaurant-use-geolocation-btn");
    const clearMapBtn = document.getElementById("restaurant-clear-map-btn");
    const latInput = document.getElementById("restaurant-profile-latitude");
    const lngInput = document.getElementById("restaurant-profile-longitude");

    geolocationBtn?.addEventListener("click", (event) => {
        event.preventDefault();
        ensureProfileMapReady();
        setRestaurantProfileGeolocation();
    });

    clearMapBtn?.addEventListener("click", (event) => {
        event.preventDefault();
        clearRestaurantProfileMarker();
        if (latInput) latInput.value = "";
        if (lngInput) lngInput.value = "";
    });

    const syncCoordinatesToMap = () => {
        const lat = Number(latInput?.value);
        const lng = Number(lngInput?.value);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
            return;
        }
        ensureProfileMapReady();
        setRestaurantProfileMarker(lat, lng);
    };

    latInput?.addEventListener("change", syncCoordinatesToMap);
    lngInput?.addEventListener("change", syncCoordinatesToMap);
}

async function bootstrap() {
    bindEvents();

    try {
        const allowed = await ensureRestaurantAuth();
        if (!allowed) {
            return;
        }
        await loadAll();
        ensureProfileMapReady();
    } catch (error) {
        showToast(error.message, true);
        window.location.href = "/";
    }
}

bootstrap();
