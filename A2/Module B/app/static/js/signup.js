const selectors = {
    signupForm: document.getElementById("signup-form"),
    signupAs: document.getElementById("signup-as"),
    signupMemberFields: document.getElementById("signup-member-fields"),
    signupDeliveryFields: document.getElementById("signup-delivery-fields"),
    signupRestaurantFields: document.getElementById("signup-restaurant-fields"),
    detectDeliveryLocationBtn: document.getElementById("signup-detect-delivery-location"),
    detectRestaurantLocationBtn: document.getElementById("signup-detect-restaurant-location"),
    deliveryLocationText: document.getElementById("signup-delivery-location-text"),
    restaurantLocationText: document.getElementById("signup-restaurant-location-text"),
    toast: document.getElementById("toast"),
};

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
    selectors.signupMemberFields.classList.toggle("hidden", signupAs === "");
    selectors.signupDeliveryFields.classList.toggle("hidden", signupAs !== "DeliveryPartner");
    selectors.signupRestaurantFields.classList.toggle("hidden", signupAs !== "Restaurant");
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
            const lat = Number(position.coords.latitude).toFixed(6);
            const lng = Number(position.coords.longitude).toFixed(6);
            latInput.value = lat;
            lngInput.value = lng;
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

async function handleSignup(event) {
    event.preventDefault();
    const signupAs = selectors.signupAs.value;

    if (!signupAs) {
        showToast("Please select signup type", true);
        return;
    }

    const member = {
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
        if (!restaurantLat || !restaurantLng) {
            showToast("Please detect location for Restaurant signup", true);
            return;
        }

        const ratingRaw = document.getElementById("signup-restaurant-rating").value;
        payload.restaurant = {
            name: document.getElementById("signup-restaurant-name").value.trim(),
            contactPhone: document.getElementById("signup-restaurant-phone").value.trim(),
            isOpen: document.getElementById("signup-restaurant-open").checked,
            isVerified: document.getElementById("signup-restaurant-verified").checked,
            averageRating: ratingRaw ? Number(ratingRaw) : null,
            addressLine: document.getElementById("signup-restaurant-address").value.trim(),
            city: document.getElementById("signup-restaurant-city").value.trim(),
            zipCode: document.getElementById("signup-restaurant-zip").value.trim(),
            latitude: Number(restaurantLat),
            longitude: Number(restaurantLng),
            discontinued: document.getElementById("signup-restaurant-discontinued").checked,
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
            window.location.href = activeRole === "Customer" ? "/customer" : "/";
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
}

bindEvents();
renderSignupFields();
