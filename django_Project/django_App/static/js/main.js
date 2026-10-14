/* ==========================================================================
DJGO — storefront JavaScript (vanilla, no framework)
Handles: quantity steppers, wishlist toggles via fetch, confirm dialogs,
coupon apply, mobile nav, filter auto-submit and reveal animations.
   ========================================================================== */
(function () {
    "use strict";

    const csrf = () => {
        const el = document.querySelector("[name=csrfmiddlewaretoken]");
        return el ? el.value : "";
    };

    /* ---- quantity steppers ------------------------------------------------ */
    function bindSteppers() {
        document.querySelectorAll("[data-stepper]").forEach((box) => {
            const input = box.querySelector("input[name=quantity]");
            const form = box.closest("form");
            const minus = box.querySelector("[data-step='-1']");
            const plus = box.querySelector("[data-step='1']");
            if (!input || !minus || !plus) return;

            const max = parseInt(input.getAttribute("max") || "99", 10);
            const sync = () => {
                minus.disabled = parseInt(input.value, 10) <= 1;
                plus.disabled = parseInt(input.value, 10) >= max;
            };

            const step = (delta) => () => {
                const next = Math.min(Math.max(parseInt(input.value, 10) + delta, 1), max);
                input.value = next;
                sync();
                if (form && form.dataset.autosubmit === "1") form.requestSubmit();
            };
            minus.addEventListener("click", step(-1));
            plus.addEventListener("click", step(1));
            input.addEventListener("change", sync);
            sync();
        });
    }

    /* ---- wishlist toggle without a full page reload ----------------------- */
    function bindWishlist() {
        document.querySelectorAll("form[data-wishlist]").forEach((form) => {
            form.addEventListener("submit", async (event) => {
                event.preventDefault();
                const btn = form.querySelector("button");
                const icon = btn ? btn.querySelector("i") : null;
                const data = new FormData(form);

                try {
                    const res = await fetch(form.action, {
                        method: "POST",
                        body: data,
                        headers: { "X-CSRFToken": csrf(), "X-Requested-With": "fetch" },
                    });
                    if (!res.ok) throw new Error("request failed");
                    const payload = await res.json().catch(() => ({}));

                    if (btn) btn.classList.toggle("on", !!payload.saved);
                    if (icon) {
                        icon.classList.toggle("bi-heart-fill", !!payload.saved);
                        icon.classList.toggle("bi-heart", !payload.saved);
                    }
                    const label = btn ? btn.querySelector(".wishlist-label") : null;
                    if (label) {
                        label.textContent = payload.saved ? "Saved" : "Wishlist";
                    }
                    const badge = document.querySelector("[data-wishlist-count]");
                    if (badge && typeof payload.count === "number") {
                        badge.textContent = payload.count;
                        badge.style.display = payload.count ? "flex" : "none";
                    }
                } catch (err) {
                    form.submit(); // graceful fallback to a normal POST
                }
            });
        });
    }

    /* ---- destructive-action confirmation ---------------------------------- */
    function bindConfirms() {
        document.querySelectorAll("form[data-confirm]").forEach((form) => {
            form.addEventListener("submit", (event) => {
                if (!window.confirm(form.dataset.confirm)) event.preventDefault();
            });
        });
    }

    /* ---- auto-submitting filter selects ----------------------------------- */
    function bindAutoFilters() {
        document.querySelectorAll("select[data-auto-submit]").forEach((select) => {
            select.addEventListener("change", () => select.form.requestSubmit());
        });
    }

    /* ---- address book: copy a saved address into checkout ------------------ */
    function bindAddressPick() {
        const select = document.querySelector("[data-address-picker]");
        const form = select ? select.closest("form") : null;
        if (!select || !form) return;

        const store = JSON.parse(select.dataset.addresses || "[]");
        select.addEventListener("change", () => {
            const found = store.find((a) => String(a.id) === select.value);
            if (!found) return;
            const map = {
                full_name: found.full_name, phone: found.phone, line1: found.line1,
                line2: found.line2, city: found.city, state: found.state,
                postal_code: found.postal_code,
            };
            Object.entries(map).forEach(([key, value]) => {
                const field = form.querySelector(`[name=${key}]`);
                if (field) field.value = value || "";
            });
        });
    }

    /* ---- checkout: payment method copy ------------------------------------ */
    function bindPaymentTabs() {
        document.querySelectorAll("[data-payment-option]").forEach((option) => {
            option.addEventListener("change", () => {
                document.querySelectorAll("[data-payment-option]").forEach((o) => {
                    o.closest(".pay-card").classList.toggle("selected", o.checked);
                });
            });
        });
    }

    /* ---- scroll reveal ---------------------------------------------------- */
    function bindReveal() {
        const targets = document.querySelectorAll("[data-reveal]");
        if (!targets.length || !("IntersectionObserver" in window)) return;
        const io = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12 });
        targets.forEach((t) => io.observe(t));
    }

    /* ---- auto-dismiss messages -------------------------------------------- */
    function bindAlerts() {
        document.querySelectorAll(".alert-dismissible").forEach((alert) => {
            setTimeout(() => {
                if (window.bootstrap && bootstrap.Alert) {
                    bootstrap.Alert.getOrCreateInstance(alert).close();
                }
            }, 6000);
        });
    }

    function init() {
        bindSteppers();
        bindWishlist();
        bindConfirms();
        bindAutoFilters();
        bindAddressPick();
        bindPaymentTabs();
        bindReveal();
        bindAlerts();
    }

    document.addEventListener("DOMContentLoaded", init);
})();
