/**
 * Sales Filters Management
 * Handles filtering for Sales Dashboard by Market, Agreement Type, and Account Type
 */
(() => {
    'use strict';

    // Filter state
    const salesFilterState = {
        markets: new Set(),
        agreementTypes: new Set(),
        accountTypes: new Set(),
    };

    // DOM elements
    const marketFilterButtons = document.querySelectorAll("[data-sales-filter='market']");
    const agreementFilterButtons = document.querySelectorAll("[data-sales-filter='agreement']");
    const accountFilterButtons = document.querySelectorAll("[data-sales-filter='account']");
    const filterResetButton = document.querySelector("[data-sales-filter-reset]");

    /**
     * Normalize market name for comparison
     * @param {string} marketName - Market name to normalize
     * @returns {string} Normalized market name (ksa, uae, or original lowercase)
     */
    const normalizeMarketName = (marketName) => {
        if (!marketName) return null;
        const normalized = String(marketName).trim().toLowerCase();
        if (normalized === "ksa" || normalized.includes("ksa")) return "ksa";
        if (normalized === "uae" || normalized.includes("uae")) return "uae";
        return normalized;
    };

    /**
     * Normalize agreement type for comparison
     * @param {string} agreementType - Agreement type to normalize
     * @returns {string} Normalized agreement type
     */
    const normalizeAgreementType = (agreementType) => {
        if (!agreementType) return null;
        const normalized = String(agreementType).trim().toLowerCase();
        // Map variations to standard values (must match filter button values exactly)
        if (normalized.includes("ad hoc") || normalized.includes("adhoc") || normalized === "ad-hoc") return "ad hoc";
        if (normalized.includes("framework")) return "framework";
        if (normalized.includes("retainer") || normalized.includes("subscription")) return "retainer";
        return normalized;
    };

    /**
     * Infer account type from tags
     * @param {Array<string>} tags - Array of tag strings
     * @returns {string} Account type: "key" or "non-key"
     */
    const inferAccountType = (tags) => {
        if (!Array.isArray(tags) || tags.length === 0) return "non-key";
        
        const normalizedTags = tags
            .filter(tag => typeof tag === "string")
            .map(tag => tag.trim().toLowerCase());
        
        // Check for non-key first (more specific)
        for (const tag of normalizedTags) {
            if (tag.includes("non-key") || tag.includes("non key")) {
                return "non-key";
            }
        }
        
        // Check for key account
        for (const tag of normalizedTags) {
            if (tag.includes("key account")) {
                return "key";
            }
        }
        
        return "non-key";
    };

    /**
     * Check if an item matches the current filters
     * @param {Object} item - Item to check (sales order, invoice, subscription, etc.)
     * @returns {boolean} True if item matches all active filters
     */
    const matchesFilters = (item) => {
        // Market filter
        if (salesFilterState.markets.size > 0) {
            const itemMarket = normalizeMarketName(item.market || item.project_market);
            if (!itemMarket) {
                return false; // Item has no market, exclude it
            }
            // Normalize filter values and check if any match
            let marketMatches = false;
            for (const filterMarket of salesFilterState.markets) {
                const normalizedFilter = normalizeMarketName(filterMarket);
                if (itemMarket === normalizedFilter) {
                    marketMatches = true;
                    break;
                }
            }
            if (!marketMatches) {
                return false;
            }
        }

        // Agreement type filter
        if (salesFilterState.agreementTypes.size > 0) {
            const itemAgreement = normalizeAgreementType(item.agreement_type);
            if (!itemAgreement) {
                return false; // Item has no agreement type, exclude it
            }
            // Normalize filter values and check if any match
            let agreementMatches = false;
            for (const filterAgreement of salesFilterState.agreementTypes) {
                const normalizedFilter = normalizeAgreementType(filterAgreement);
                if (itemAgreement === normalizedFilter) {
                    agreementMatches = true;
                    break;
                }
            }
            if (!agreementMatches) {
                return false;
            }
        }

        // Account type filter
        if (salesFilterState.accountTypes.size > 0) {
            const tags = Array.isArray(item.tags) ? item.tags : [];
            const itemAccountType = inferAccountType(tags);
            if (!salesFilterState.accountTypes.has(itemAccountType)) {
                return false;
            }
        }

        return true;
    };

    /**
     * Update filter button UI state
     */
    const updateFilterButtons = () => {
        // Update market buttons
        marketFilterButtons.forEach(button => {
            const value = button.getAttribute("data-filter-value");
            if (salesFilterState.markets.has(value)) {
                button.classList.add("border-sky-500", "bg-sky-50", "text-sky-700");
                button.classList.remove("border-slate-200", "bg-white", "text-slate-700");
            } else {
                button.classList.remove("border-sky-500", "bg-sky-50", "text-sky-700");
                button.classList.add("border-slate-200", "bg-white", "text-slate-700");
            }
        });

        // Update agreement type buttons
        agreementFilterButtons.forEach(button => {
            const value = button.getAttribute("data-filter-value");
            if (salesFilterState.agreementTypes.has(value)) {
                button.classList.add("border-sky-500", "bg-sky-50", "text-sky-700");
                button.classList.remove("border-slate-200", "bg-white", "text-slate-700");
            } else {
                button.classList.remove("border-sky-500", "bg-sky-50", "text-sky-700");
                button.classList.add("border-slate-200", "bg-white", "text-slate-700");
            }
        });

        // Update account type buttons
        accountFilterButtons.forEach(button => {
            const value = button.getAttribute("data-filter-value");
            if (salesFilterState.accountTypes.has(value)) {
                button.classList.add("border-sky-500", "bg-sky-50", "text-sky-700");
                button.classList.remove("border-slate-200", "bg-white", "text-slate-700");
            } else {
                button.classList.remove("border-sky-500", "bg-sky-50", "text-sky-700");
                button.classList.add("border-slate-200", "bg-white", "text-slate-700");
            }
        });
    };

    /**
     * Toggle a filter value
     * @param {string} filterType - Type of filter: "market", "agreement", or "account"
     * @param {string} value - Filter value to toggle
     */
    const toggleFilter = (filterType, value) => {
        let filterSet;
        switch (filterType) {
            case "market":
                filterSet = salesFilterState.markets;
                break;
            case "agreement":
                filterSet = salesFilterState.agreementTypes;
                break;
            case "account":
                filterSet = salesFilterState.accountTypes;
                break;
            default:
                return;
        }

        if (filterSet.has(value)) {
            filterSet.delete(value);
        } else {
            filterSet.add(value);
        }

        updateFilterButtons();
        dispatchFilterChange();
    };

    /**
     * Clear all filters
     */
    const clearFilters = () => {
        salesFilterState.markets.clear();
        salesFilterState.agreementTypes.clear();
        salesFilterState.accountTypes.clear();
        updateFilterButtons();
        dispatchFilterChange();
    };

    /**
     * Check if any filters are active
     * @returns {boolean} True if any filter is active
     */
    const hasActiveFilters = () => {
        return salesFilterState.markets.size > 0 ||
               salesFilterState.agreementTypes.size > 0 ||
               salesFilterState.accountTypes.size > 0;
    };

    /**
     * Get current filter state
     * @returns {Object} Current filter state
     */
    const getFilterState = () => {
        return {
            markets: Array.from(salesFilterState.markets),
            agreementTypes: Array.from(salesFilterState.agreementTypes),
            accountTypes: Array.from(salesFilterState.accountTypes),
            hasActiveFilters: hasActiveFilters(),
        };
    };

    /**
     * Dispatch filter change event
     */
    const dispatchFilterChange = () => {
        const event = new CustomEvent("salesFiltersChanged", {
            detail: getFilterState(),
        });
        document.dispatchEvent(event);
    };

    /**
     * Initialize event listeners
     */
    const init = () => {
        // Market filter buttons
        marketFilterButtons.forEach(button => {
            button.addEventListener("click", () => {
                const value = button.getAttribute("data-filter-value");
                toggleFilter("market", value);
            });
        });

        // Agreement type filter buttons
        agreementFilterButtons.forEach(button => {
            button.addEventListener("click", () => {
                const value = button.getAttribute("data-filter-value");
                toggleFilter("agreement", value);
            });
        });

        // Account type filter buttons
        accountFilterButtons.forEach(button => {
            button.addEventListener("click", () => {
                const value = button.getAttribute("data-filter-value");
                toggleFilter("account", value);
            });
        });

        // Reset button
        if (filterResetButton) {
            filterResetButton.addEventListener("click", clearFilters);
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    // Export public API
    window.SalesFilters = {
        matchesFilters,
        getFilterState,
        hasActiveFilters,
        clearFilters,
        normalizeMarketName,
        normalizeAgreementType,
        inferAccountType,
    };
})();

