const selectors = {
    signupForm: document.getElementById("signup-form"),
    signupAs: document.getElementById("signup-as"),
    signupMemberFields: document.getElementById("signup-member-fields"),
    signupDeliveryFields: document.getElementById("signup-delivery-fields"),
    signupRestaurantFields: document.getElementById("signup-restaurant-fields"),
    detectDeliveryLocationBtn: document.getElementById("signup-detect-delivery-location"),
    detectRestaurantLocationBtn: document.getElementById("signup-detect-restaurant-location"),
    clearRestaurantLocationBtn: document.getElementById("signup-clear-restaurant-location"),
    deliveryLocationText: document.getElementById("signup-delivery-location-text"),
    restaurantLocationText: document.getElementById("signup-restaurant-location-text"),
    restaurantLatInput: document.getElementById("signup-restaurant-lat"),
    restaurantLngInput: document.getElementById("signup-restaurant-lng"),
    restaurantLatitudeInput: document.getElementById("signup-restaurant-latitude"),
    restaurantLongitudeInput: document.getElementById("signup-restaurant-longitude"),
    toast: document.getElementById("toast"),
};

let restaurantMap = null;
let restaurantMarker = null;

function showToast(message, isError = false) {
    selectors.toast.textContent = message;
    selectors.toast.style.background = isError ? "#7f1d1d" : "#0f172a";
    selectors.toast.classList.remove("hidden");
    setTimeout(() => selectors.toast.classList.add("hidden"), 2600);
}

async function api(path, options = {}) {
    const headers = options.headers || {};
    headers["Content-Type"] = "application/json";

    const response = await fetch(path, { ...options, headers });
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(payload.message || "Request failed");
    }

    return payload;
}

function renderSignupFields() {
    const signupAs = selectors.signupAs.value;
    const showMemberFields = signupAs === "Member" || signupAs === "DeliveryPartner";
    selectors.signupMemberFields.classList.toggle("hidden", !showMemberFields);
    selectors.signupDeliveryFields.classList.toggle("hidden", signupAs !== "DeliveryPartner");
    selectors.signupRestaurantFields.classList.toggle("hidden", signupAs !== "Restaurant");

    if (signupAs === "Restaurant") {
        initializeRestaurantMap();
    }
}

function getLocationErrorMessage(error) {
    if (!error) {
        return "Unable to detect location.";
    }
    if (error.code === error.PERMISSION_DENIED) {
        return "Location permission denied. Please allow location access.";
    }
    if (error.code === error.POSITION_UNAVAILABLE) {
        return "Location information is unavailable.";
    }
    if (error.code === error.TIMEOUT) {
        return "Location request timed out. Try again.";
    }
    return "Unable to detect location.";
}

function detectLocation(target) {
    if (!navigator.geolocation) {
        showToast("Geolocation is not supported by this browser.", true);
        return;
    }

    const latInput = document.getElementById(target === "delivery" ? "signup-delivery-lat" : "signup-restaurant-lat");
    const lngInput = document.getElementById(target === "delivery" ? "signup-delivery-lng" : "signup-restaurant-lng");
    const locationText = target === "delivery" ? selectors.deliveryLocationText : selectors.restaurantLocationText;

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = Number(position.coords.latitude);
            const lng = Number(position.coords.longitude);
            latInput.value = lat;
            lngInput.value = lng;

            if (target === "restaurant") {
                setRestaurantLocation(lat, lng, true);
            }

            locationText.textContent = `Location detected: ${lat}, ${lng}`;
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

function setRestaurantLocation(lat, lng, centerMap = false) {
    const parsedLat = Number(lat);
    const parsedLng = Number(lng);

    if (!Number.isFinite(parsedLat) || !Number.isFinite(parsedLng)) {
        return;
    }

    selectors.restaurantLatInput.value = String(parsedLat);
    selectors.restaurantLngInput.value = String(parsedLng);
    selectors.restaurantLatitudeInput.value = String(parsedLat);
    selectors.restaurantLongitudeInput.value = String(parsedLng);
    selectors.restaurantLocationText.textContent = `Location selected: ${parsedLat}, ${parsedLng}`;

    if (!restaurantMap || !window.L) {
        return;
    }

    if (!restaurantMarker) {
        restaurantMarker = window.L.marker([parsedLat, parsedLng]).addTo(restaurantMap);
    } else {
        restaurantMarker.setLatLng([parsedLat, parsedLng]);
    }

    if (centerMap) {
        restaurantMap.setView([parsedLat, parsedLng], 16);
    }
}

function clearRestaurantLocation() {
    selectors.restaurantLatInput.value = "";
    selectors.restaurantLngInput.value = "";
    selectors.restaurantLatitudeInput.value = "";
    selectors.restaurantLongitudeInput.value = "";
    selectors.restaurantLocationText.textContent = "Location not detected yet.";

    if (restaurantMap && restaurantMarker) {
        restaurantMap.removeLayer(restaurantMarker);
        restaurantMarker = null;
    }
}

function initializeRestaurantMap() {
    if (restaurantMap || !window.L) {
        return;
    }

    const mapElement = document.getElementById("signup-restaurant-map");
    if (!mapElement) {
        return;
    }

    restaurantMap = window.L.map(mapElement).setView([23.0225, 72.5714], 12);

    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(restaurantMap);

    restaurantMap.on("click", (event) => {
        const lat = Number(event.latlng.lat);
        const lng = Number(event.latlng.lng);
        setRestaurantLocation(lat, lng, false);
    });

    // Ensure Leaflet sizes correctly when map appears after section unhide.
    setTimeout(() => {
        if (restaurantMap) {
            restaurantMap.invalidateSize();
        }
    }, 120);
}

async function handleSignup(event) {
    event.preventDefault();
    const signupAs = selectors.signupAs.value;

    if (!signupAs) {
        showToast("Please select signup type", true);
        return;
    }

    let member = {
        name: document.getElementById("signup-member-name").value.trim(),
        email: document.getElementById("signup-member-email").value.trim(),
        password: document.getElementById("signup-member-password").value,
        phoneNumber: document.getElementById("signup-member-phone").value.trim(),
    };

    const payload = {
        signupAs,
        member,
    };

    if (signupAs === "DeliveryPartner") {
        const deliveryLat = document.getElementById("signup-delivery-lat").value;
        const deliveryLng = document.getElementById("signup-delivery-lng").value;
        if (!deliveryLat || !deliveryLng) {
            showToast("Please detect location for Delivery Agent signup", true);
            return;
        }

        payload.deliveryPartner = {
            vehicleNumber: document.getElementById("signup-delivery-vehicle").value.trim(),
            licenseID: document.getElementById("signup-delivery-license").value.trim(),
            dateOfBirth: document.getElementById("signup-delivery-dob").value,
            currentLatitude: Number(deliveryLat),
            currentLongitude: Number(deliveryLng),
            isOnline: document.getElementById("signup-delivery-online").checked,
        };
    }

    if (signupAs === "Restaurant") {
        const restaurantLat = document.getElementById("signup-restaurant-lat").value;
        const restaurantLng = document.getElementById("signup-restaurant-lng").value;
        const restaurantName = document.getElementById("signup-restaurant-name").value.trim();
        const restaurantPhone = document.getElementById("signup-restaurant-phone").value.trim();
        const restaurantEmail = document.getElementById("signup-restaurant-email").value.trim();
        const restaurantPassword = document.getElementById("signup-restaurant-password").value;

        member = {
            name: restaurantName,
            email: restaurantEmail,
            password: restaurantPassword,
            phoneNumber: restaurantPhone,
        };
        payload.member = member;

        if (!restaurantLat || !restaurantLng) {
            showToast("Please choose restaurant location using map or geolocation", true);
            return;
        }

        payload.restaurant = {
            name: restaurantName,
            contactPhone: restaurantPhone,
            email: restaurantEmail,
            password: restaurantPassword,
            addressLine: document.getElementById("signup-restaurant-address").value.trim(),
            city: document.getElementById("signup-restaurant-city").value.trim(),
            zipCode: document.getElementById("signup-restaurant-zip").value.trim(),
            latitude: Number(restaurantLat),
            longitude: Number(restaurantLng),
        };
    }

    try {
        const response = await api("/api/auth/signup", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        const activeRole = response.data.member?.activeRole || response.data.roleAssigned;
        localStorage.setItem("qb_token", response.data.token);
        localStorage.setItem("qb_portal", activeRole);
        showToast("Signup successful. Redirecting to dashboard...");
        setTimeout(() => {
            if (activeRole === "Customer") {
                window.location.href = "/customer";
                return;
            }
            if (activeRole === "RestaurantManager") {
                window.location.href = "/restaurant";
                return;
            }
            if (activeRole === "DeliveryPartner") {
                window.location.href = "/delivery";
                return;
            }
            window.location.href = "/";
        }, 500);
    } catch (err) {
        showToast(err.message, true);
    }
}

function bindEvents() {
    selectors.signupForm.addEventListener("submit", handleSignup);
    selectors.signupAs.addEventListener("change", renderSignupFields);
    selectors.detectDeliveryLocationBtn.addEventListener("click", () => detectLocation("delivery"));
    selectors.detectRestaurantLocationBtn.addEventListener("click", () => detectLocation("restaurant"));
    selectors.clearRestaurantLocationBtn.addEventListener("click", clearRestaurantLocation);
    selectors.restaurantLatitudeInput.addEventListener("input", () => {
        const lat = Number(selectors.restaurantLatitudeInput.value);
        const lng = Number(selectors.restaurantLongitudeInput.value);
        if (Number.isFinite(lat) && Number.isFinite(lng)) {
            setRestaurantLocation(lat, lng, true);
        }
    });
    selectors.restaurantLongitudeInput.addEventListener("input", () => {
        const lat = Number(selectors.restaurantLatitudeInput.value);
        const lng = Number(selectors.restaurantLongitudeInput.value);
        if (Number.isFinite(lat) && Number.isFinite(lng)) {
            setRestaurantLocation(lat, lng, true);
        }
    });
}

bindEvents();
renderSignupFields();
