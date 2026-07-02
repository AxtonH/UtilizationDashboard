// Sales filter state: owns currentFilterState plus the filter-application
// wrappers that read it. Function bodies are verbatim from main.js (original
// indentation kept); main.js mutates the state via setCurrentFilterState().
import { monthsInCalendarQuarter, recalculateAgreementTypeTotals, recalculateSalesOrdersAgreementTotals, recalculateSalesOrdersProjectTotals } from "./period-utils.js";

let currentFilterState = { hasActiveFilters: false }; // Current filter state (default to no filters)

export const getCurrentFilterState = () => currentFilterState;
export const setCurrentFilterState = (value) => {
  currentFilterState = value;
};

    export const applyFilters = (items) => {
        try {
            if (!Array.isArray(items)) {
                return items;
            }
            
            // If no filters are active, return items as-is
            if (!currentFilterState || !currentFilterState.hasActiveFilters) {
                return items;
            }
            
            // If SalesFilters is not available, return items as-is
            if (!window.SalesFilters || typeof window.SalesFilters.matchesFilters !== 'function') {
                return items;
            }
            
            return items.filter(item => {
                try {
                    return window.SalesFilters.matchesFilters(item);
                } catch (error) {
                    console.warn('Error filtering item:', error, item);
                    // If filtering fails, include the item to be safe
                    return true;
                }
            });
        } catch (error) {
            console.error('Error in applyFilters:', error);
            // If filtering completely fails, return items as-is
            return items;
        }
    };

    export const getSalesStatsForCurrentFilters = (baseStats) => {
        if (!baseStats) return null;
        if (!currentFilterState || !currentFilterState.hasActiveFilters) {
            return baseStats;
        }

        const filteredInvoices = Array.isArray(baseStats.invoices)
            ? applyFilters(baseStats.invoices)
            : baseStats.invoices;
        const filteredSalesOrders = Array.isArray(baseStats.sales_orders)
            ? applyFilters(baseStats.sales_orders)
            : baseStats.sales_orders;

        return {
            ...baseStats,
            invoices: filteredInvoices,
            sales_orders: filteredSalesOrders,
            invoice_count: Array.isArray(filteredInvoices)
                ? filteredInvoices.length
                : baseStats.invoice_count,
            sales_order_count: Array.isArray(filteredSalesOrders)
                ? filteredSalesOrders.length
                : baseStats.sales_order_count,
        };
    };

    export const getAgreementTotalsForCurrentFilters = (baseTotals, invoices) => {
        if (!currentFilterState || !currentFilterState.hasActiveFilters) {
            return baseTotals;
        }
        const filteredInvoices = Array.isArray(invoices) ? applyFilters(invoices) : invoices;
        return recalculateAgreementTypeTotals(filteredInvoices, baseTotals);
    };

    export const getInvoicedSeriesForCurrentFilters = (baseSeries, breakdownRows) => {
        if (!Array.isArray(baseSeries) || baseSeries.length === 0) return baseSeries;
        if (!currentFilterState || !currentFilterState.hasActiveFilters) return baseSeries;
        if (!Array.isArray(breakdownRows) || breakdownRows.length === 0) return baseSeries;

        // Normalize filter sets for faster lookups
        const activeMarkets = new Set(
            (currentFilterState.markets || []).map((m) => (m || '').toString().trim().toLowerCase())
        );
        const activeAgreements = new Set(
            (currentFilterState.agreementTypes || []).map((a) => (a || '').toString().trim().toLowerCase())
        );
        const activeAccountTypes = new Set(
            (currentFilterState.accountTypes || []).map((a) => (a || '').toString().trim().toLowerCase())
        );

        const matchesFilters = (row) => {
            const market = (row.market || '').toString().trim().toLowerCase();
            const agreement = (row.agreement_type || '').toString().trim().toLowerCase();
            const account = (row.account_type || '').toString().trim().toLowerCase();

            if (activeMarkets.size > 0 && !activeMarkets.has(market)) return false;
            if (activeAgreements.size > 0 && !activeAgreements.has(agreement)) return false;
            if (activeAccountTypes.size > 0 && !activeAccountTypes.has(account)) return false;
            return true;
        };

        const monthTotals = new Map(); // `${year}-${month}` -> amount
        breakdownRows.forEach((row) => {
            if (!matchesFilters(row)) return;
            const month = Number(row.month);
            const year = Number(row.year);
            if (!Number.isFinite(year)) return;
            const amount = Number(row.amount_aed) || 0;
            if (!Number.isFinite(month) || month < 1 || month > 12) return;
            const key = `${year}-${month}`;
            const prev = monthTotals.get(key) || 0;
            monthTotals.set(key, prev + amount);
        });

        const isQuarterlySeries = baseSeries.some(
            (item) => item.quarter != null && Number(item.quarter) >= 1
        );
        if (isQuarterlySeries) {
            return baseSeries.map((item) => {
                const q = Number(item.quarter);
                const itemYear = Number(item.year);
                if (!Number.isFinite(q) || !Number.isFinite(itemYear)) return item;
                const mths = monthsInCalendarQuarter(q);
                let filteredAmount = 0;
                for (const m of mths) {
                    const keyCurrent = `${itemYear}-${m}`;
                    filteredAmount += monthTotals.has(keyCurrent) ? monthTotals.get(keyCurrent) : 0;
                }
                let prevYearAmount = item.previous_year_amount_aed;
                const prevYearValue = Number(item.previous_year) || (itemYear - 1);
                if (item.previous_year_amount_aed !== undefined && Number.isFinite(prevYearValue)) {
                    let py = 0;
                    for (const m of mths) {
                        const keyPrev = `${prevYearValue}-${m}`;
                        py += monthTotals.has(keyPrev) ? monthTotals.get(keyPrev) : 0;
                    }
                    prevYearAmount = py;
                }
                return {
                    ...item,
                    amount_aed: filteredAmount,
                    previous_year_amount_aed: prevYearAmount,
                    amount_display: `AED ${Number(filteredAmount || 0).toLocaleString('en-AE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
                    previous_year_amount_display: prevYearAmount !== undefined
                        ? `AED ${Number(prevYearAmount || 0).toLocaleString('en-AE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        : item.previous_year_amount_display,
                };
            });
        }

        return baseSeries.map((item) => {
            const monthNum = Number(item.month);
            const itemYear = Number(item.year);
            if (!Number.isFinite(monthNum) || !Number.isFinite(itemYear)) return item;

            // Current year amount
            const keyCurrent = `${itemYear}-${monthNum}`;
            const filteredAmount = monthTotals.has(keyCurrent) ? monthTotals.get(keyCurrent) : 0;

            // Previous year amount (if present on the item)
            let prevYearAmount = item.previous_year_amount_aed;
            const prevYearValue = Number(item.previous_year) || (itemYear - 1);
            if (item.previous_year_amount_aed !== undefined && Number.isFinite(prevYearValue)) {
                const keyPrev = `${prevYearValue}-${monthNum}`;
                prevYearAmount = monthTotals.has(keyPrev) ? monthTotals.get(keyPrev) : 0;
            }

            return {
                ...item,
                amount_aed: filteredAmount,
                previous_year_amount_aed: prevYearAmount,
                amount_display: `AED ${Number(filteredAmount || 0).toLocaleString('en-AE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
                previous_year_amount_display: prevYearAmount !== undefined
                    ? `AED ${Number(prevYearAmount || 0).toLocaleString('en-AE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : item.previous_year_amount_display,
            };
        });
    };

    export const getSalesOrdersSeriesForCurrentFilters = (baseSeries, breakdownRows) => {
        if (!Array.isArray(baseSeries) || baseSeries.length === 0) return baseSeries;
        if (!currentFilterState || !currentFilterState.hasActiveFilters) return baseSeries;
        if (!Array.isArray(breakdownRows) || breakdownRows.length === 0) return baseSeries;

        const activeMarkets = new Set(
            (currentFilterState.markets || []).map((m) => (m || '').toString().trim().toLowerCase())
        );
        const activeAgreements = new Set(
            (currentFilterState.agreementTypes || []).map((a) => (a || '').toString().trim().toLowerCase())
        );
        const activeAccountTypes = new Set(
            (currentFilterState.accountTypes || []).map((a) => (a || '').toString().trim().toLowerCase())
        );

        const matchesFilters = (row) => {
            const market = (row.market || '').toString().trim().toLowerCase();
            const agreement = (row.agreement_type || '').toString().trim().toLowerCase();
            const account = (row.account_type || '').toString().trim().toLowerCase();

            if (activeMarkets.size > 0 && !activeMarkets.has(market)) return false;
            if (activeAgreements.size > 0 && !activeAgreements.has(agreement)) return false;
            if (activeAccountTypes.size > 0 && !activeAccountTypes.has(account)) return false;
            return true;
        };

        const monthTotals = new Map(); // `${year}-${month}` -> amount
        breakdownRows.forEach((row) => {
            if (!matchesFilters(row)) return;
            const month = Number(row.month);
            const year = Number(row.year);
            if (!Number.isFinite(year)) return;
            const amount = Number(row.amount_aed) || 0;
            if (!Number.isFinite(month) || month < 1 || month > 12) return;
            const key = `${year}-${month}`;
            const prev = monthTotals.get(key) || 0;
            monthTotals.set(key, prev + amount);
        });

        const isQuarterlySeriesSo = baseSeries.some(
            (item) => item.quarter != null && Number(item.quarter) >= 1
        );
        if (isQuarterlySeriesSo) {
            return baseSeries.map((item) => {
                const q = Number(item.quarter);
                const itemYear = Number(item.year);
                if (!Number.isFinite(q) || !Number.isFinite(itemYear)) return item;
                const mths = monthsInCalendarQuarter(q);
                let filteredAmount = 0;
                for (const m of mths) {
                    const keyCurrent = `${itemYear}-${m}`;
                    filteredAmount += monthTotals.has(keyCurrent) ? monthTotals.get(keyCurrent) : 0;
                }
                let prevYearAmount = item.previous_year_amount_aed;
                const prevYearValue = Number(item.previous_year) || (itemYear - 1);
                if (item.previous_year_amount_aed !== undefined && Number.isFinite(prevYearValue)) {
                    let py = 0;
                    for (const m of mths) {
                        const keyPrev = `${prevYearValue}-${m}`;
                        py += monthTotals.has(keyPrev) ? monthTotals.get(keyPrev) : 0;
                    }
                    prevYearAmount = py;
                }
                return {
                    ...item,
                    amount_aed: filteredAmount,
                    previous_year_amount_aed: prevYearAmount,
                };
            });
        }

        return baseSeries.map((item) => {
            const monthNum = Number(item.month);
            const itemYear = Number(item.year);
            if (!Number.isFinite(monthNum) || !Number.isFinite(itemYear)) return item;

            const keyCurrent = `${itemYear}-${monthNum}`;
            const filteredAmount = monthTotals.has(keyCurrent) ? monthTotals.get(keyCurrent) : 0;

            let prevYearAmount = item.previous_year_amount_aed;
            const prevYearValue = Number(item.previous_year) || (itemYear - 1);
            if (item.previous_year_amount_aed !== undefined && Number.isFinite(prevYearValue)) {
                const keyPrev = `${prevYearValue}-${monthNum}`;
                prevYearAmount = monthTotals.has(keyPrev) ? monthTotals.get(keyPrev) : 0;
            }

            return {
                ...item,
                amount_aed: filteredAmount,
                previous_year_amount_aed: prevYearAmount,
            };
        });
    };

    export const getSalesOrdersAgreementTotalsForCurrentFilters = (baseTotals, salesOrders) => {
        if (!currentFilterState || !currentFilterState.hasActiveFilters) {
            return baseTotals;
        }
        const filteredOrders = Array.isArray(salesOrders) ? applyFilters(salesOrders) : salesOrders;
        return recalculateSalesOrdersAgreementTotals(filteredOrders, baseTotals);
    };

    export const getSalesOrdersProjectTotalsForCurrentFilters = (baseTotals, salesOrders) => {
        if (!currentFilterState || !currentFilterState.hasActiveFilters) {
            return baseTotals;
        }
        const filteredOrders = Array.isArray(salesOrders) ? applyFilters(salesOrders) : salesOrders;
        return recalculateSalesOrdersProjectTotals(filteredOrders, baseTotals);
    };
