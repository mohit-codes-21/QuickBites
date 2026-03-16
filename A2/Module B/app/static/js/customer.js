const state = {
    token: localStorage.getItem("qb_token") || null,
    activePortal: localStorage.getItem("qb_portal") || null,
    user: null,
    restaurants: [],
    menuItems: [],
    cart: JSON.parse(localStorage.getItem("qb_cart") || "[]"),
};

const pageName = document.body.dataset.page;

const selectors = {
    toast: document.getElementById("toast"),
    navCartCount: document.getElementById("nav-cart-count"),
    customerUserChip: document.getElementById("customer-user-chip"),
    logoutBtn: document.getElementById("customer-logout-btn"),
    heroSearchForm: document.getElementById("hero-search-form"),
    heroSearchInput: document.getElementById("hero-search-input"),
    heroSearchType: document.getElementById("hero-search-type"),
    featuredRestaurants: document.getElementById("featured-restaurants"),
    featuredMenuItems: document.getElementById("featured-menu-items"),
    restaurantFilterInput: document.getElementById("restaurant-filter-input"),
    refreshRestaurantsPage: document.getElementById("refresh-restaurants-page"),
    restaurantsPageGrid: document.getElementById("restaurants-page-grid"),
    browseForm: document.getElementById("browse-form"),
    browseSearchInput: document.getElementById("browse-search-input"),
    browseRestaurantInput: document.getElementById("browse-restaurant-input"),
    browseResults: document.getElementById("browse-results"),
    profileMemberDetails: document.getElementById("profile-member-details"),
    profileCustomerDetails: document.getElementById("profile-customer-details"),
    cartItems: document.getElementById("cart-items"),
    cartItemCount: document.getElementById("cart-item-count"),
    cartTotal: document.getElementById("cart-total"),
    clearCartBtn: document.getElementById("clear-cart-btn"),
    searchChips: document.querySelectorAll("[data-search-chip]"),
};

function showToast(message, isError = false) {
    if (!selectors.toast) {
        return;
    }
    selectors.toast.textContent = message;
    selectors.toast.style.background = isError ? "#7f1d1d" : "#0f172a";
    selectors.toast.classList.remove("hidden");
    setTimeout(() => selectors.toast.classList.add("hidden"), 2600);
}

function persistCart() {
    localStorage.setItem("qb_cart", JSON.stringify(state.cart));
}

function updateCartBadge() {
    const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
    if (selectors.navCartCount) {
        selectors.navCartCount.textContent = String(count);
    }
    if (selectors.cartItemCount) {
        selectors.cartItemCount.textContent = String(count);
    }
    if (selectors.cartTotal) {
        const total = state.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        selectors.cartTotal.textContent = `Rs ${total.toFixed(2)}`;
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
        throw new Error(payload.message || "Request failed");
    }
    return payload;
}

function renderEmptyState(target, message) {
    if (!target) {
        return;
    }
    target.innerHTML = `<div class="empty-state">${message}</div>`;
}

function renderRestaurantCards(target, restaurants) {
    if (!target) {
        return;
    }
    if (!restaurants.length) {
        renderEmptyState(target, "No restaurants matched your search.");
        return;
    }

    target.innerHTML = restaurants.map((restaurant) => `
        <article class="restaurant-card">
            <p class="section-kicker">${restaurant.city}</p>
            <h3>${restaurant.name}</h3>
            <p>${restaurant.isOpen ? "Open now" : "Currently closed"} • ${restaurant.isVerified ? "Verified" : "Pending verification"}</p>
            <div class="card-tags">
                <span class="tag">ID ${restaurant.restaurantID}</span>
                <span class="tag">Rating ${restaurant.averageRating || "-"}</span>
            </div>
            <div class="card-meta">
                <span>${restaurant.isOpen ? "Ordering available" : "Check back later"}</span>
                <a class="text-link" href="/customer/browse?restaurantID=${restaurant.restaurantID}">Browse menu</a>
            </div>
        </article>
    `).join("");
}

function addToCart(item) {
    const existing = state.cart.find((entry) => entry.restaurantID === item.restaurantID && entry.itemID === item.itemID);
    if (existing) {
        existing.quantity += 1;
    } else {
        state.cart.push({
            restaurantID: item.restaurantID,
            itemID: item.itemID,
            name: item.name,
            restaurantName: item.restaurantName,
            price: Number(item.appPrice),
            quantity: 1,
        });
    }
    persistCart();
    updateCartBadge();
    showToast(`${item.name} added to cart`);
}

function renderMenuCards(target, items) {
    if (!target) {
        return;
    }
    if (!items.length) {
        renderEmptyState(target, "No dishes matched your search.");
        return;
    }

    target.innerHTML = items.map((item) => `
        <article class="menu-card">
            <p class="section-kicker">${item.restaurantName}</p>
            <h3>${item.name}</h3>
            <p>${item.menuCategory || "Chef special"}</p>
            <div class="card-tags">
                <span class="tag">Item ${item.itemID}</span>
                <span class="tag">${item.isAvailable ? "Available" : "Unavailable"}</span>
            </div>
            <div class="price-row">
                <strong>Rs ${Number(item.appPrice).toFixed(2)}</strong>
                <button type="button" data-add-item="${item.restaurantID}:${item.itemID}">Add to cart</button>
            </div>
        </article>
    `).join("");
}

function renderDefinitionList(target, dataMap) {
    if (!target) {
        return;
    }
    const entries = Object.entries(dataMap || {});
    if (!entries.length) {
        renderEmptyState(target, "No profile data available.");
        return;
    }

    target.innerHTML = entries.map(([label, value]) => `
        <div>
            <dt>${label}</dt>
            <dd>${value ?? "-"}</dd>
        </div>
    `).join("");
}

function renderCart() {
    if (!selectors.cartItems) {
        updateCartBadge();
        return;
    }
    if (!state.cart.length) {
        renderEmptyState(selectors.cartItems, "Your cart is empty. Add items from Browse or Home.");
        updateCartBadge();
        return;
    }

    selectors.cartItems.innerHTML = state.cart.map((item) => `
        <article class="cart-item">
            <p class="section-kicker">${item.restaurantName}</p>
            <h3>${item.name}</h3>
            <div class="price-row">
                <span>Qty ${item.quantity}</span>
                <strong>Rs ${(item.price * item.quantity).toFixed(2)}</strong>
            </div>
            <div class="row-inline">
                <button type="button" class="btn-secondary" data-cart-action="decrease" data-cart-id="${item.restaurantID}:${item.itemID}">-</button>
                <button type="button" data-cart-action="increase" data-cart-id="${item.restaurantID}:${item.itemID}">+</button>
                <button type="button" class="btn-danger" data-cart-action="remove" data-cart-id="${item.restaurantID}:${item.itemID}">Remove</button>
            </div>
        </article>
    `).join("");
    updateCartBadge();
}

async function ensureCustomerSession() {
    if (!state.token) {
        window.location.href = "/";
        return false;
    }

    try {
        const payload = await api("/api/auth/me");
        state.user = payload.data;
        if (!state.user.roles.includes("Customer")) {
            showToast("Customer access required", true);
            window.location.href = "/";
            return false;
        }
        state.activePortal = "Customer";
        localStorage.setItem("qb_portal", "Customer");
        if (selectors.customerUserChip) {
            selectors.customerUserChip.textContent = state.user.name;
        }
        return true;
    } catch (error) {
        localStorage.removeItem("qb_token");
        localStorage.removeItem("qb_portal");
        window.location.href = "/";
        return false;
    }
}

async function loadRestaurants() {
    const payload = await api("/api/restaurants");
    state.restaurants = payload.data || [];
}

async function loadMenuItems(search = "", restaurantID = "") {
    const query = new URLSearchParams();
    if (search) {
        query.set("search", search);
    }
    if (restaurantID) {
        query.set("restaurantID", restaurantID);
    }
    const suffix = query.toString();
    const payload = await api(`/api/menu-items${suffix ? `?${suffix}` : ""}`);
    state.menuItems = payload.data || [];
}

async function loadProfile() {
    const payload = await api(`/api/portfolio/${state.user.memberID}`);
    const member = payload.data.member || {};
    const customerProfile = payload.data.customerProfile || {};
    renderDefinitionList(selectors.profileMemberDetails, {
        "Member ID": member.memberID,
        Name: member.name,
        Email: member.email,
        Phone: member.phoneNumber,
        "Created At": member.createdAt,
    });
    renderDefinitionList(selectors.profileCustomerDetails, {
        "Loyalty Tier": customerProfile.loyaltyTier,
        Membership: customerProfile.membership ? "Active" : "Inactive",
        Discount: customerProfile.membershipDiscount,
        "Cart Total": customerProfile.cartTotalAmount,
        "Membership Due": customerProfile.membershipDueDate,
    });
}

async function populateHome() {
    await Promise.all([loadRestaurants(), loadMenuItems()]);
    renderRestaurantCards(selectors.featuredRestaurants, state.restaurants.slice(0, 3));
    renderMenuCards(selectors.featuredMenuItems, state.menuItems.slice(0, 6));
}

function applyRestaurantFilter() {
    const term = (selectors.restaurantFilterInput?.value || "").trim().toLowerCase();
    const filtered = state.restaurants.filter((restaurant) => {
        if (!term) {
            return true;
        }
        return restaurant.name.toLowerCase().includes(term) || restaurant.city.toLowerCase().includes(term);
    });
    renderRestaurantCards(selectors.restaurantsPageGrid, filtered);
}

async function populateRestaurantsPage() {
    await loadRestaurants();
    applyRestaurantFilter();
}

async function populateBrowsePage(initialSearch = "", initialRestaurant = "") {
    const search = initialSearch || selectors.browseSearchInput?.value.trim() || "";
    const restaurantID = initialRestaurant || selectors.browseRestaurantInput?.value.trim() || "";
    if (selectors.browseSearchInput) {
        selectors.browseSearchInput.value = search;
    }
    if (selectors.browseRestaurantInput) {
        selectors.browseRestaurantInput.value = restaurantID;
    }
    await loadMenuItems(search, restaurantID);
    renderMenuCards(selectors.browseResults, state.menuItems);
}

function handleHeroSearch(event) {
    event.preventDefault();
    const query = selectors.heroSearchInput.value.trim();
    const type = selectors.heroSearchType.value;
    if (!query) {
        showToast("Enter a search term", true);
        return;
    }
    if (type === "restaurants") {
        window.location.href = `/customer/restaurants?search=${encodeURIComponent(query)}`;
        return;
    }
    window.location.href = `/customer/browse?search=${encodeURIComponent(query)}`;
}

async function handleLogout() {
    try {
        if (state.token) {
            await api("/api/auth/logout", { method: "POST" });
        }
    } catch (error) {
        showToast(error.message, true);
    } finally {
        localStorage.removeItem("qb_token");
        localStorage.removeItem("qb_portal");
        window.location.href = "/";
    }
}

function handleMenuGridClick(event) {
    const addButton = event.target.closest("[data-add-item]");
    if (!addButton) {
        return;
    }
    const [restaurantID, itemID] = addButton.dataset.addItem.split(":").map(Number);
    const item = state.menuItems.find((entry) => entry.restaurantID === restaurantID && entry.itemID === itemID)
        || state.menuItems.find((entry) => String(entry.restaurantID) === String(restaurantID) && String(entry.itemID) === String(itemID));
    if (!item) {
        showToast("Item not found", true);
        return;
    }
    addToCart(item);
}

function handleCartClick(event) {
    const button = event.target.closest("[data-cart-action]");
    if (!button) {
        return;
    }
    const [restaurantID, itemID] = button.dataset.cartId.split(":").map(Number);
    const item = state.cart.find((entry) => entry.restaurantID === restaurantID && entry.itemID === itemID);
    if (!item) {
        return;
    }
    if (button.dataset.cartAction === "increase") {
        item.quantity += 1;
    } else if (button.dataset.cartAction === "decrease") {
        item.quantity -= 1;
        if (item.quantity <= 0) {
            state.cart = state.cart.filter((entry) => !(entry.restaurantID === restaurantID && entry.itemID === itemID));
        }
    } else if (button.dataset.cartAction === "remove") {
        state.cart = state.cart.filter((entry) => !(entry.restaurantID === restaurantID && entry.itemID === itemID));
    }
    persistCart();
    renderCart();
}

function bindEvents() {
    selectors.logoutBtn?.addEventListener("click", handleLogout);
    selectors.heroSearchForm?.addEventListener("submit", handleHeroSearch);
    selectors.searchChips.forEach((chip) => {
        chip.addEventListener("click", () => {
            const value = chip.dataset.searchChip || "";
            if (selectors.heroSearchInput) {
                selectors.heroSearchInput.value = value;
            }
            if (selectors.heroSearchType) {
                selectors.heroSearchType.value = value === "Ahmedabad" ? "restaurants" : "menu";
            }
        });
    });

    selectors.restaurantFilterInput?.addEventListener("input", applyRestaurantFilter);
    selectors.refreshRestaurantsPage?.addEventListener("click", async () => {
        await populateRestaurantsPage();
        showToast("Restaurants refreshed");
    });
    selectors.browseForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        await populateBrowsePage();
    });
    selectors.featuredMenuItems?.addEventListener("click", handleMenuGridClick);
    selectors.browseResults?.addEventListener("click", handleMenuGridClick);
    selectors.clearCartBtn?.addEventListener("click", () => {
        state.cart = [];
        persistCart();
        renderCart();
        showToast("Cart cleared");
    });
    selectors.cartItems?.addEventListener("click", handleCartClick);
}

async function bootstrap() {
    updateCartBadge();
    bindEvents();

    const authorized = await ensureCustomerSession();
    if (!authorized) {
        return;
    }

    const params = new URLSearchParams(window.location.search);

    try {
        if (pageName === "home") {
            await populateHome();
        } else if (pageName === "restaurants") {
            await populateRestaurantsPage();
            const searchTerm = params.get("search");
            if (searchTerm && selectors.restaurantFilterInput) {
                selectors.restaurantFilterInput.value = searchTerm;
                applyRestaurantFilter();
            }
        } else if (pageName === "browse") {
            await populateBrowsePage(params.get("search") || "", params.get("restaurantID") || "");
        } else if (pageName === "profile") {
            await loadProfile();
        } else if (pageName === "cart") {
            renderCart();
        }
    } catch (error) {
        showToast(error.message, true);
    }
}

bootstrap();
