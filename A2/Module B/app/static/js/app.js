const state = {
    token: localStorage.getItem("qb_token") || null,
    activePortal: localStorage.getItem("qb_portal") || null,
    user: null,
    isAdmin: false,
    menuItems: [],
    customerOrders: [],
    deliveryAssignments: [],
    restaurants: [],
};

const TAB_ACCESS = {
    Customer: ["portfolio", "customer", "menu"],
    DeliveryPartner: ["portfolio", "delivery"],
    RestaurantManager: ["portfolio", "restaurant", "menu"],
    Admin: ["portfolio", "customer", "delivery", "restaurant", "menu", "admin"],
};

const selectors = {
    authPanel: document.getElementById("auth-panel"),
    appPanel: document.getElementById("app-panel"),
    loginForm: document.getElementById("login-form"),
    logoutBtn: document.getElementById("logout-btn"),
    refreshBtn: document.getElementById("refresh-btn"),
    welcomeLine: document.getElementById("welcome-line"),
    roleLine: document.getElementById("role-line"),
    statMemberId: document.getElementById("stat-member-id"),
    statExpiry: document.getElementById("stat-expiry"),
    statMenuCount: document.getElementById("stat-menu-count"),
    tabs: document.querySelectorAll(".tab"),
    tabContents: document.querySelectorAll(".tab-content"),
    loadPortfolioBtn: document.getElementById("load-portfolio-btn"),
    portfolioInput: document.getElementById("portfolio-member-id"),
    portfolioOutput: document.getElementById("portfolio-output"),
    filterRestaurantId: document.getElementById("filter-restaurant-id"),
    filterMenuSearch: document.getElementById("filter-menu-search"),
    filterMenuBtn: document.getElementById("filter-menu-btn"),
    menuTableBody: document.getElementById("menu-table-body"),
    menuCreatePanel: document.getElementById("menu-create-panel"),
    menuCreateForm: document.getElementById("menu-create-form"),
    customerOrdersBody: document.getElementById("customer-orders-body"),
    refreshCustomerOrdersBtn: document.getElementById("refresh-customer-orders-btn"),
    deliveryAssignmentsBody: document.getElementById("delivery-assignments-body"),
    refreshDeliveryBtn: document.getElementById("refresh-delivery-btn"),
    restaurantsTableBody: document.getElementById("restaurants-table-body"),
    refreshRestaurantsBtn: document.getElementById("refresh-restaurants-btn"),
    adminBlock: document.getElementById("admin-block"),
    adminNoAccess: document.getElementById("admin-no-access"),
    createMemberForm: document.getElementById("create-member-form"),
    deleteMemberForm: document.getElementById("delete-member-form"),
    toast: document.getElementById("toast"),
};

function showToast(message, isError = false) {
    selectors.toast.textContent = message;
    selectors.toast.style.background = isError ? "#7f1d1d" : "#0f172a";
    selectors.toast.classList.remove("hidden");
    setTimeout(() => selectors.toast.classList.add("hidden"), 2600);
}

function setAuthToken(token) {
    state.token = token;
    if (token) {
        localStorage.setItem("qb_token", token);
    } else {
        localStorage.removeItem("qb_token");
    }
}

function setActivePortal(roleName) {
    state.activePortal = roleName || null;
    if (roleName) {
        localStorage.setItem("qb_portal", roleName);
    } else {
        localStorage.removeItem("qb_portal");
    }
}

function hasRole(roleName) {
    return Boolean(state.user && state.user.roles.includes(roleName));
}

function canAccessTab(tabName) {
    if (!state.activePortal) {
        return tabName === "portfolio";
    }
    const allowedTabs = TAB_ACCESS[state.activePortal] || [];
    return allowedTabs.includes(tabName);
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
    if (!canAccessTab(tabName)) {
        return;
    }

    selectors.tabs.forEach((tab) => {
        const isActive = tab.dataset.tab === tabName;
        tab.classList.toggle("active", isActive);
    });

    selectors.tabContents.forEach((content) => {
        const contentTabName = content.id.replace("tab-", "");
        const isTarget = contentTabName === tabName;
        const accessible = canAccessTab(contentTabName);
        content.classList.toggle("hidden", !accessible);
        content.classList.toggle("active", isTarget && accessible);
    });
}

function applyRoleBasedTabVisibility() {
    selectors.tabs.forEach((tab) => {
        const tabName = tab.dataset.tab;
        const visible = canAccessTab(tabName);
        tab.classList.toggle("hidden", !visible);
    });

    let activeTab = Array.from(selectors.tabs).find((tab) => tab.classList.contains("active") && !tab.classList.contains("hidden"));
    if (!activeTab) {
        activeTab = Array.from(selectors.tabs).find((tab) => !tab.classList.contains("hidden"));
    }

    if (activeTab) {
        switchTab(activeTab.dataset.tab);
    }
}

function renderAuthState() {
    const loggedIn = Boolean(state.user);
    selectors.authPanel.classList.toggle("hidden", loggedIn);
    selectors.appPanel.classList.toggle("hidden", !loggedIn);

    if (!loggedIn) {
        return;
    }

    selectors.welcomeLine.textContent = `Welcome, ${state.user.name}`;
    selectors.roleLine.textContent = `Roles: ${state.user.roles.join(", ") || "No role"}`;
    selectors.statMemberId.textContent = state.user.memberID;
    selectors.statExpiry.textContent = new Date(state.user.sessionExpires).toLocaleString();

    if (!state.activePortal || !hasRole(state.activePortal)) {
        const fallbackRole = state.user.roles.includes("Customer")
            ? "Customer"
            : (state.user.roles[0] || null);
        setActivePortal(fallbackRole);
    }

    state.isAdmin = state.activePortal === "Admin";
    const canManageMenu = state.activePortal === "Admin" || state.activePortal === "RestaurantManager";

    selectors.menuCreatePanel.classList.toggle("hidden", !canManageMenu);
    selectors.adminBlock.classList.toggle("hidden", !state.isAdmin);
    selectors.adminNoAccess.classList.toggle("hidden", state.isAdmin);
    applyRoleBasedTabVisibility();
}

function renderMenuTable() {
    selectors.menuTableBody.innerHTML = "";

    for (const item of state.menuItems) {
        const row = document.createElement("tr");
        const canManageMenu = state.activePortal === "Admin" || state.activePortal === "RestaurantManager";

        row.innerHTML = `
            <td>${item.restaurantName} (${item.restaurantID})</td>
            <td>${item.itemID}</td>
            <td>${item.name}</td>
            <td>${item.menuCategory || "-"}</td>
            <td>${item.appPrice}</td>
            <td>${item.isAvailable ? "Yes" : "No"}</td>
            <td>
                ${canManageMenu ? `<button class="btn-secondary" data-edit="${item.restaurantID}:${item.itemID}">Quick Update</button>` : "-"}
                ${canManageMenu ? `<button class="btn-danger" data-delete="${item.restaurantID}:${item.itemID}">Delete</button>` : ""}
            </td>
        `;

        selectors.menuTableBody.appendChild(row);
    }

    selectors.statMenuCount.textContent = String(state.menuItems.length);
}

function renderCustomerOrders() {
    selectors.customerOrdersBody.innerHTML = "";
    for (const rowData of state.customerOrders) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${rowData.orderID}</td>
            <td>${new Date(rowData.orderTime).toLocaleString()}</td>
            <td>${rowData.orderStatus}</td>
            <td>${rowData.restaurantName}</td>
            <td>${rowData.totalAmount}</td>
            <td>${rowData.paymentStatus || "-"}</td>
        `;
        selectors.customerOrdersBody.appendChild(row);
    }
}

function renderDeliveryAssignments() {
    selectors.deliveryAssignmentsBody.innerHTML = "";
    for (const rowData of state.deliveryAssignments) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${rowData.AssignmentID}</td>
            <td>${rowData.OrderID}</td>
            <td>${rowData.restaurantName}</td>
            <td>${rowData.orderStatus}</td>
            <td>${new Date(rowData.acceptanceTime).toLocaleString()}</td>
            <td>${new Date(rowData.pickupTime).toLocaleString()}</td>
            <td>${new Date(rowData.deliveryTime).toLocaleString()}</td>
        `;
        selectors.deliveryAssignmentsBody.appendChild(row);
    }
}

function renderRestaurants() {
    selectors.restaurantsTableBody.innerHTML = "";
    for (const restaurant of state.restaurants) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${restaurant.restaurantID}</td>
            <td>${restaurant.name}</td>
            <td>${restaurant.city}</td>
            <td>${restaurant.isOpen ? "Yes" : "No"}</td>
            <td>${restaurant.isVerified ? "Yes" : "No"}</td>
            <td>${restaurant.averageRating || "-"}</td>
        `;
        selectors.restaurantsTableBody.appendChild(row);
    }
}

async function loadCurrentUser() {
    const payload = await api("/api/auth/me");
    state.user = payload.data;
    renderAuthState();
}

async function loadPortfolio(memberId) {
    const payload = await api(`/api/portfolio/${memberId}`);
    selectors.portfolioOutput.textContent = JSON.stringify(payload.data, null, 2);
}

async function loadMenuItems() {
    const qs = new URLSearchParams();
    if (selectors.filterRestaurantId.value.trim()) {
        qs.append("restaurantID", selectors.filterRestaurantId.value.trim());
    }
    if (selectors.filterMenuSearch.value.trim()) {
        qs.append("search", selectors.filterMenuSearch.value.trim());
    }

    const payload = await api(`/api/menu-items?${qs.toString()}`);
    state.menuItems = payload.data;
    renderMenuTable();
}

async function loadCustomerOrders() {
    const payload = await api("/api/customer/orders");
    state.customerOrders = payload.data;
    renderCustomerOrders();
}

async function loadDeliveryAssignments() {
    const payload = await api("/api/delivery/assignments");
    state.deliveryAssignments = payload.data;
    renderDeliveryAssignments();
}

async function loadRestaurants() {
    const payload = await api("/api/restaurants");
    state.restaurants = payload.data;
    renderRestaurants();
}

async function loadRoleSpecificData() {
    const loaders = [];

    if (canAccessTab("menu")) {
        loaders.push(loadMenuItems());
    }
    if (canAccessTab("customer")) {
        loaders.push(loadCustomerOrders());
    }
    if (canAccessTab("delivery")) {
        loaders.push(loadDeliveryAssignments());
    }
    if (canAccessTab("restaurant")) {
        loaders.push(loadRestaurants());
    }

    await Promise.all(loaders);
}

async function handleLogin(event) {
    event.preventDefault();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const loginAsSelect = document.getElementById("login-as");
    const loginAsFixed = document.getElementById("login-as-fixed");
    const loginAs = loginAsSelect ? loginAsSelect.value : (loginAsFixed ? loginAsFixed.value : "");

    if (!loginAs) {
        showToast("Please choose a login portal", true);
        return;
    }

    try {
        const payload = await api("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ email, password, loginAs }),
        });

        setAuthToken(payload.data.token);
        setActivePortal(payload.data.member.activeRole || loginAs);
        await loadCurrentUser();
        selectors.portfolioInput.value = state.user.memberID;
        await loadPortfolio(state.user.memberID);
        await loadRoleSpecificData();
        showToast("Login successful");
    } catch (err) {
        showToast(err.message, true);
    }
}

async function handleLogout() {
    try {
        if (state.token) {
            await api("/api/auth/logout", { method: "POST" });
        }
    } catch (err) {
        showToast(err.message, true);
    } finally {
        state.user = null;
        setAuthToken(null);
        setActivePortal(null);
        selectors.portfolioOutput.textContent = "";
        state.menuItems = [];
        state.customerOrders = [];
        state.deliveryAssignments = [];
        state.restaurants = [];
        renderMenuTable();
        renderCustomerOrders();
        renderDeliveryAssignments();
        renderRestaurants();
        renderAuthState();
    }
}

async function handleMenuCreate(event) {
    event.preventDefault();
    const formData = new FormData(event.target);

    const payload = {
        restaurantID: Number(formData.get("restaurantID")),
        itemID: Number(formData.get("itemID")),
        name: formData.get("name"),
        menuCategory: formData.get("menuCategory") || null,
        restaurantPrice: Number(formData.get("restaurantPrice")),
        appPrice: Number(formData.get("appPrice")),
        preparationTime: Number(formData.get("preparationTime")),
        isVegetarian: formData.get("isVegetarian") === "on",
        isAvailable: formData.get("isAvailable") === "on",
    };

    try {
        await api("/api/menu-items", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        event.target.reset();
        showToast("Menu item created");
        await loadMenuItems();
    } catch (err) {
        showToast(err.message, true);
    }
}

async function handleMenuActions(event) {
    const deleteId = event.target.dataset.delete;
    const editId = event.target.dataset.edit;

    if (!deleteId && !editId) {
        return;
    }

    const [restaurantID, itemID] = (deleteId || editId).split(":").map(Number);

    if (deleteId) {
        if (!window.confirm(`Delete menu item ${restaurantID}:${itemID}?`)) {
            return;
        }

        try {
            await api(`/api/menu-items/${restaurantID}/${itemID}`, { method: "DELETE" });
            showToast("Menu item deleted");
            await loadMenuItems();
        } catch (err) {
            showToast(err.message, true);
        }
    }

    if (editId) {
        const newPrice = window.prompt("Enter updated appPrice:");
        if (!newPrice) {
            return;
        }

        try {
            await api(`/api/menu-items/${restaurantID}/${itemID}`, {
                method: "PUT",
                body: JSON.stringify({ appPrice: Number(newPrice) }),
            });
            showToast("Menu item updated");
            await loadMenuItems();
        } catch (err) {
            showToast(err.message, true);
        }
    }
}

async function handleCreateMember(event) {
    event.preventDefault();
    const formData = new FormData(event.target);

    const payload = {
        name: formData.get("name"),
        email: formData.get("email"),
        phoneNumber: formData.get("phoneNumber"),
        password: formData.get("password"),
        roleID: Number(formData.get("roleID")),
        profileType: formData.get("profileType") || null,
    };

    try {
        const response = await api("/api/admin/members", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        showToast(`Member created with ID ${response.data.memberID}`);
        event.target.reset();
    } catch (err) {
        showToast(err.message, true);
    }
}

async function handleDeleteMember(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const memberID = Number(formData.get("memberID"));

    if (!window.confirm(`Delete member ${memberID}?`)) {
        return;
    }

    try {
        await api(`/api/admin/members/${memberID}`, { method: "DELETE" });
        showToast("Member deleted");
        event.target.reset();
    } catch (err) {
        showToast(err.message, true);
    }
}

function bindEvents() {
    selectors.loginForm.addEventListener("submit", handleLogin);
    selectors.logoutBtn.addEventListener("click", handleLogout);
    selectors.refreshBtn.addEventListener("click", async () => {
        try {
            await loadCurrentUser();
            await loadPortfolio(state.user.memberID);
            await loadRoleSpecificData();
            showToast("Data refreshed");
        } catch (err) {
            showToast(err.message, true);
        }
    });

    selectors.tabs.forEach((tabButton) => {
        tabButton.addEventListener("click", () => switchTab(tabButton.dataset.tab));
    });

    selectors.loadPortfolioBtn.addEventListener("click", async () => {
        const requested = Number(selectors.portfolioInput.value || state.user.memberID);
        try {
            await loadPortfolio(requested);
            showToast("Portfolio loaded");
        } catch (err) {
            showToast(err.message, true);
        }
    });

    selectors.filterMenuBtn.addEventListener("click", async () => {
        try {
            await loadMenuItems();
        } catch (err) {
            showToast(err.message, true);
        }
    });

    selectors.refreshCustomerOrdersBtn.addEventListener("click", async () => {
        try {
            await loadCustomerOrders();
            showToast("Customer orders refreshed");
        } catch (err) {
            showToast(err.message, true);
        }
    });

    selectors.refreshDeliveryBtn.addEventListener("click", async () => {
        try {
            await loadDeliveryAssignments();
            showToast("Delivery assignments refreshed");
        } catch (err) {
            showToast(err.message, true);
        }
    });

    selectors.refreshRestaurantsBtn.addEventListener("click", async () => {
        try {
            await loadRestaurants();
            showToast("Restaurants refreshed");
        } catch (err) {
            showToast(err.message, true);
        }
    });

    selectors.menuCreateForm.addEventListener("submit", handleMenuCreate);
    selectors.menuTableBody.addEventListener("click", handleMenuActions);
    selectors.createMemberForm.addEventListener("submit", handleCreateMember);
    selectors.deleteMemberForm.addEventListener("submit", handleDeleteMember);
}

async function bootstrap() {
    bindEvents();

    if (!state.token) {
        renderAuthState();
        return;
    }

    try {
        await loadCurrentUser();
        if (!state.activePortal && state.user.roles.length > 0) {
            setActivePortal(state.user.roles[0]);
        }
        selectors.portfolioInput.value = state.user.memberID;
        await loadPortfolio(state.user.memberID);
        await loadRoleSpecificData();
    } catch (err) {
        showToast("Session expired. Please login again.", true);
        setAuthToken(null);
        setActivePortal(null);
        state.user = null;
        renderAuthState();
    }
}

bootstrap();
