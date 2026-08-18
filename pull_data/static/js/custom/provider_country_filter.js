/**
 * Filters a "Country" <select> down to only the countries supported by
 * the currently-selected "SMS Provider" <select>, using
 * GET /api/countries-by-provider/<provider_id>/.
 *
 * Works on both:
 *   - The UserConfig admin change form (#id_sms_provider / #id_default_country)
 *   - The "Customize Automation Job" form (#id_sms_provider / #id_country)
 *
 * If no provider is selected, the full (unfiltered) country list is
 * restored, since there's nothing to filter by yet.
 */
(function () {
    "use strict";

    var COUNTRIES_BY_PROVIDER_URL = "/api/countries-by-provider/";

    function init() {
        var providerSelect = document.getElementById("id_sms_provider");
        var countrySelect = document.getElementById("id_country") || document.getElementById("id_default_country");
        if (!providerSelect || !countrySelect) {
            return;
        }

        var allCountryOptions = Array.prototype.slice.call(countrySelect.options).map(function (opt) {
            return opt.cloneNode(true);
        });

        function render(options, previousValue) {
            countrySelect.innerHTML = "";
            options.forEach(function (opt) {
                countrySelect.appendChild(opt);
            });
            var values = options.map(function (opt) { return opt.value; });
            if (values.indexOf(previousValue) !== -1) {
                countrySelect.value = previousValue;
            }
        }

        function restoreAllCountries() {
            var previousValue = countrySelect.value;
            render(allCountryOptions.map(function (opt) { return opt.cloneNode(true); }), previousValue);
        }

        function filterByProvider(providerId) {
            if (!providerId) {
                restoreAllCountries();
                return;
            }

            var previousValue = countrySelect.value;

            fetch(COUNTRIES_BY_PROVIDER_URL + providerId + "/", {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    var blankOption = allCountryOptions.find(function (opt) { return opt.value === ""; });
                    var options = [];
                    if (blankOption) {
                        options.push(blankOption.cloneNode(true));
                    }
                    (data.countries || []).forEach(function (country) {
                        var opt = document.createElement("option");
                        opt.value = country.id;
                        opt.textContent = country.name;
                        options.push(opt);
                    });
                    render(options, previousValue);
                })
                .catch(function () {
                    // If the lookup fails for any reason, fall back to showing
                    // every country rather than leaving the field empty/stuck.
                    restoreAllCountries();
                });
        }

        providerSelect.addEventListener("change", function () {
            filterByProvider(providerSelect.value);
        });

        // Handle the case where the form is redisplayed with a provider
        // already selected (e.g. after a validation error, or when
        // Django admin loads the change form for an existing UserConfig).
        if (providerSelect.value) {
            filterByProvider(providerSelect.value);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
