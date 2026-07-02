// Pure period/comparison/recompute helpers for the sales dashboard.
// Extracted verbatim from main.js (original indentation kept); no DOM access
// and no dashboard state. window.SalesFilters is accessed defensively where
// noted (same behavior as before the split).

    /**
     * Format decimal hours to hh:mm format (e.g., 17.33 -> "17:20")
     * @param {number} decimalHours - Hours as decimal (e.g., 17.33)
     * @returns {string} Formatted string (e.g., "17:20")
     */
    export const formatHoursToMinutes = (decimalHours) => {
        const hours = parseFloat(decimalHours) || 0;
        const totalMinutes = Math.round(hours * 60);
        const h = Math.floor(totalMinutes / 60);
        const m = totalMinutes % 60;
        return `${h}:${m.toString().padStart(2, '0')}`;
    };

    export const isStrategyAndProject = (projectName, tags) => {
        if (projectName && String(projectName).toLowerCase().includes('strategy&')) {
            return true;
        }
        if (Array.isArray(tags)) {
            for (let i = 0; i < tags.length; i += 1) {
                const t = tags[i];
                if (typeof t === 'string' && t.toLowerCase().includes('strategy&')) {
                    return true;
                }
            }
        }
        return false;
    };

    export const isQuarterPeriodKey = (key) =>
        typeof key === 'string' && /-Q[1-4]$/.test(key);

    export const monthsInCalendarQuarter = (q) => {
        const start = (q - 1) * 3 + 1;
        return [start, start + 1, start + 2];
    };

    export const previousCalendarQuarterMonths = (year, q) => {
        if (q === 1) {
            return { year: year - 1, months: [10, 11, 12] };
        }
        const start = (q - 2) * 3 + 1;
        return { year, months: [start, start + 1, start + 2] };
    };

    export const getPrevQuarterKey = (key) => {
        if (!isQuarterPeriodKey(key)) {
            return null;
        }
        const [ys, qPart] = key.split('-Q');
        const y = Number(ys);
        const q = Number(qPart);
        if (!y || !q) {
            return null;
        }
        if (q === 1) {
            return `${y - 1}-Q4`;
        }
        return `${y}-Q${q - 1}`;
    };

    /** Inclusive date range for API selected_month (YYYY-MM or YYYY-Qn). */
    export const boundsFromSelectedPeriod = (selectedMonth, periodKind) => {
        if (!selectedMonth || typeof selectedMonth !== 'string') {
            return null;
        }
        if (periodKind === 'quarter' && isQuarterPeriodKey(selectedMonth)) {
            const dash = selectedMonth.indexOf('-');
            const y = Number(selectedMonth.slice(0, dash));
            const q = Number(selectedMonth.slice(dash + 2));
            if (!y || !q) {
                return null;
            }
            const mths = monthsInCalendarQuarter(q);
            const monthStart = new Date(y, mths[0] - 1, 1);
            const monthEnd = new Date(y, mths[2], 0);
            return { monthStart, monthEnd };
        }
        const parts = selectedMonth.split('-');
        if (parts.length < 2) {
            return null;
        }
        const year = Number(parts[0]);
        const monthNum = Number(parts[1]);
        if (!year || !monthNum) {
            return null;
        }
        const monthStart = new Date(year, monthNum - 1, 1);
        const lastDay = new Date(year, monthNum, 0).getDate();
        const monthEnd = new Date(year, monthNum - 1, lastDay);
        return { monthStart, monthEnd };
    };

    export const comparisonLabelForPeriod = (periodKind) =>
        periodKind === 'quarter' ? 'last quarter' : 'last month';

    export const getPrevPeriodKey = (monthKey) =>
        isQuarterPeriodKey(String(monthKey || ''))
            ? getPrevQuarterKey(String(monthKey))
            : getPrevMonthKey(monthKey);

    /**
     * Normalize agreement type using SalesFilters helper when available
     */
    export const normalizeAgreementTypeSafe = (value) => {
        if (!value) return null;
        try {
            if (window.SalesFilters && typeof window.SalesFilters.normalizeAgreementType === 'function') {
                return window.SalesFilters.normalizeAgreementType(value);
            }
        } catch (error) {
            console.warn('Error normalizing agreement type via SalesFilters:', error);
        }
        const normalized = String(value).trim().toLowerCase();
        if (normalized.includes('ad hoc') || normalized.includes('adhoc') || normalized === 'ad-hoc') return 'ad hoc';
        if (normalized.includes('framework')) return 'framework';
        if (normalized.includes('retainer') || normalized.includes('subscription')) return 'retainer';
        return normalized || null;
    };

    /**
     * Recalculate agreement type totals from invoices, respecting filters
     * @param {Array} invoices - Array of invoices (filtered or unfiltered)
     * @param {Object} fallbackTotals - Optional fallback totals
     * @returns {Object} Totals grouped by agreement type
     */
    export const recalculateAgreementTypeTotals = (invoices, fallbackTotals = null) => {
        const totals = {
            'Retainer': 0,
            'Framework': 0,
            'Ad Hoc': 0,
            'Unknown': 0,
        };

        if (!Array.isArray(invoices)) {
            return fallbackTotals || totals;
        }

        invoices.forEach((invoice) => {
            try {
                const normalized = normalizeAgreementTypeSafe(invoice.agreement_type);
                let key = 'Unknown';
                if (normalized === 'retainer') key = 'Retainer';
                else if (normalized === 'framework') key = 'Framework';
                else if (normalized === 'ad hoc') key = 'Ad Hoc';

                const amount = invoice.x_studio_aed_total ? parseFloat(invoice.x_studio_aed_total) : 0;
                if (!Number.isNaN(amount)) {
                    totals[key] += amount;
                }
            } catch (error) {
                console.warn('Error processing invoice for agreement totals:', error, invoice);
            }
        });

        return totals;
    };

    /**
     * Recalculate sales orders agreement totals from filtered orders
     */
    export const recalculateSalesOrdersAgreementTotals = (salesOrders, fallbackTotals = null) => {
        const totals = {
            'Retainer': 0,
            'Framework': 0,
            'Ad Hoc': 0,
            'Unknown': 0,
        };

        if (!Array.isArray(salesOrders)) {
            return fallbackTotals || totals;
        }

        salesOrders.forEach((order) => {
            try {
                const normalized = normalizeAgreementTypeSafe(order.agreement_type);
                let key = 'Unknown';
                if (normalized === 'retainer') key = 'Retainer';
                else if (normalized === 'framework') key = 'Framework';
                else if (normalized === 'ad hoc') key = 'Ad Hoc';

                const amount = order.x_studio_aed_total ? parseFloat(order.x_studio_aed_total) : 0;
                if (!Number.isNaN(amount)) {
                    totals[key] += amount;
                }
            } catch (error) {
                console.warn('Error processing sales order for agreement totals:', error, order);
            }
        });

        return totals;
    };

    /**
     * Recalculate sales orders project totals from filtered orders
     */
    export const recalculateSalesOrdersProjectTotals = (salesOrders, fallbackTotals = null) => {
        const projectMap = new Map();

        if (!Array.isArray(salesOrders)) {
            return fallbackTotals || [];
        }

        salesOrders.forEach((order) => {
            try {
                const projectName = order.project_name || 'Unknown Project';
                const amount = order.x_studio_aed_total ? parseFloat(order.x_studio_aed_total) : 0;
                if (Number.isNaN(amount)) {
                    return;
                }
                const current = projectMap.get(projectName) || 0;
                projectMap.set(projectName, current + amount);
            } catch (error) {
                console.warn('Error processing sales order for project totals:', error, order);
            }
        });

        const totalsArray = Array.from(projectMap.entries()).map(([project_name, total_amount_aed]) => ({
            project_name,
            total_amount_aed,
        }));

        totalsArray.sort((a, b) => b.total_amount_aed - a.total_amount_aed);
        return totalsArray.length > 0 ? totalsArray : (fallbackTotals || []);
    };

    export const calculateComparison = (current, previous) => {
        if (previous === 0) {
            if (current > 0) return { change_percentage: 100.0, trend: "up" };
            if (current === 0) return { change_percentage: 0.0, trend: "flat" };
            return { change_percentage: 100.0, trend: "down" };
        }
        const change = ((current - previous) / previous) * 100;
        const pct = Math.abs(change);
        if (Math.abs(pct) < 1e-6) return { change_percentage: 0.0, trend: "flat" };
        return { change_percentage: pct, trend: change > 0 ? "up" : "down" };
    };

    export const computeFilterComparisonFromBreakdown = (breakdown, monthKey, filterState) => {
        if (!Array.isArray(breakdown) || !filterState || !filterState.hasActiveFilters) return null;
        if (!monthKey) return null;

        const normalize = (val) => (val || "").toString().trim().toLowerCase();

        const matchesFilters = (row) => {
            const markets = Array.isArray(filterState.markets) ? filterState.markets : [];
            const agreements = Array.isArray(filterState.agreementTypes) ? filterState.agreementTypes : [];
            const accounts = Array.isArray(filterState.accountTypes) ? filterState.accountTypes : [];

            if (markets.length > 0) {
                const rowMarket = normalize(row.market);
                const match = markets.some((m) => normalize(m) === rowMarket);
                if (!match) return false;
            }

            if (agreements.length > 0) {
                const rowAgreement = normalize(row.agreement_type);
                const match = agreements.some((a) => normalize(a) === rowAgreement);
                if (!match) return false;
            }

            if (accounts.length > 0) {
                const rowAccount = normalize(row.account_type);
                if (!rowAccount) return false;
                const match = accounts.some((a) => normalize(a) === rowAccount);
                if (!match) return false;
            }

            return true;
        };

        const sumForMonth = (year, month) => {
            return breakdown.reduce((acc, row) => {
                const ry = Number(row.year);
                const rm = Number(row.month);
                if (ry !== year || rm !== month) return acc;
                if (!matchesFilters(row)) return acc;
                const count = Number(row.invoice_count ?? row.order_count ?? 0);
                if (!Number.isNaN(count)) {
                    return acc + count;
                }
                return acc;
            }, 0);
        };

        const sumForMonths = (year, months) =>
            months.reduce((acc, m) => acc + sumForMonth(year, m), 0);

        if (isQuarterPeriodKey(String(monthKey))) {
            const [yStr, qStr] = String(monthKey).split("-Q");
            const targetYear = Number(yStr);
            const targetQ = Number(qStr);
            if (!targetYear || !targetQ) return null;
            const prevQ = previousCalendarQuarterMonths(targetYear, targetQ);
            const currentTotal = sumForMonths(targetYear, monthsInCalendarQuarter(targetQ));
            const previousTotal = sumForMonths(prevQ.year, prevQ.months);
            return calculateComparison(currentTotal, previousTotal);
        }

        const parts = String(monthKey).split("-");
        if (parts.length !== 2) return null;
        const targetYear = Number(parts[0]);
        const targetMonth = Number(parts[1]);
        if (!targetYear || !targetMonth) return null;

        const prevMonth = targetMonth === 1 ? 12 : targetMonth - 1;
        const prevYear = targetMonth === 1 ? targetYear - 1 : targetYear;

        const currentTotal = sumForMonth(targetYear, targetMonth);
        const previousTotal = sumForMonth(prevYear, prevMonth);
        return calculateComparison(currentTotal, previousTotal);
    };

    export const getPrevMonthKey = (monthKey) => {
        if (!monthKey) return null;
        const parts = String(monthKey).split("-");
        if (parts.length !== 2) return null;
        let year = Number(parts[0]);
        let month = Number(parts[1]);
        if (!year || !month) return null;
        month -= 1;
        if (month === 0) {
            month = 12;
            year -= 1;
        }
        return `${year}-${String(month).padStart(2, "0")}`;
    };

    /**
     * Recalculate subscription statistics from filtered subscriptions
     * @param {Array} subscriptions - Filtered subscriptions
     * @param {date} monthStart - Start of the month
     * @param {date} monthEnd - End of the month
     * @returns {Object} Recalculated subscription statistics
     */
    export const recalculateSubscriptionStats = (subscriptions, monthStart, monthEnd) => {
        let activeCount = 0;
        let churnedCount = 0;
        let newRenewCount = 0;
        let mrrTotal = 0.0;
        const activeOrderNames = [];

        if (!Array.isArray(subscriptions)) {
            return {
                active_count: 0,
                churned_count: 0,
                new_renew_count: 0,
                mrr: 0.0,
                mrr_display: "AED 0.00",
                active_order_names: [],
                total_subscriptions: 0,
                subscription_comparison: null,
            };
        }

        subscriptions.forEach(sub => {
            try {
                // Determine if subscription is churned based on end_date
                // Churned if: end_date exists AND end_date <= monthEnd
                const endDateStr = sub.end_date;
                let isChurned = false;
                
                if (endDateStr) {
                    const endDate = new Date(endDateStr);
                    if (!isNaN(endDate.getTime())) {
                        // Convert monthEnd to Date if it's not already
                        const monthEndDate = monthEnd instanceof Date ? monthEnd : new Date(monthEnd);
                        if (endDate <= monthEndDate) {
                            isChurned = true;
                        }
                    }
                }

                // Count churned
                if (isChurned) {
                    churnedCount++;
                } else {
                    // Count active (not churned) and collect order names
                    activeCount++;
                    const orderName = sub.order_name || sub.name || '';
                    if (orderName) {
                        activeOrderNames.push(orderName);
                    }

                    // Sum MRR (only for active/non-churned subscriptions)
                    const recurring = sub.monthly_recurring_payment || sub.recurring_monthly || 0;
                    if (recurring) {
                        try {
                            mrrTotal += parseFloat(recurring) || 0;
                        } catch (error) {
                            console.warn('Error parsing recurring payment:', error, sub);
                        }
                    }
                }

                // Check if new/renew (align with backend: start_date, else first_contract_date)
                const startDateStr = sub.start_date || sub.first_contract_date;
                if (startDateStr) {
                    const startDate = new Date(startDateStr);
                    if (!isNaN(startDate.getTime())) {
                        // Convert monthStart/monthEnd to Date if needed
                        const monthStartDate = monthStart instanceof Date ? monthStart : new Date(monthStart);
                        const monthEndDate = monthEnd instanceof Date ? monthEnd : new Date(monthEnd);
                        if (monthStartDate <= startDate && startDate <= monthEndDate) {
                            newRenewCount++;
                        }
                    }
                }
            } catch (error) {
                console.warn('Error processing subscription for stats:', error, sub);
            }
        });

        // Sort order names
        const sortedOrderNames = Array.from(new Set(activeOrderNames)).sort();

        // Format MRR display
        const mrrDisplay = mrrTotal.toLocaleString('en-AE', { style: 'currency', currency: 'AED' });

        const totalSubscriptions = activeCount + churnedCount;

        return {
            active_count: activeCount,
            churned_count: churnedCount,
            new_renew_count: newRenewCount,
            mrr: mrrTotal,
            mrr_display: mrrDisplay,
            active_order_names: sortedOrderNames,
            total_subscriptions: totalSubscriptions,
            subscription_comparison: null,
        };
    };

    /**
     * Recalculate external hours totals from filtered subscriptions and sales orders
     * @param {Array} subscriptions - Filtered subscriptions
     * @param {Array} salesOrders - Filtered sales orders
     * @param {Object} originalTotals - Original totals for comparison data
     * @returns {Object} Recalculated totals
     */
    export const recalculateExternalHoursTotals = (subscriptions, salesOrders, originalTotals) => {
        let subscriptionSoldTotal = 0.0;
        let subscriptionUsedTotal = 0.0;
        let salesOrderTotal = 0.0;

        // Sum from filtered subscriptions
        if (Array.isArray(subscriptions)) {
            subscriptions.forEach(sub => {
                try {
                    if (isStrategyAndProject(sub.project_name, sub.tags || [])) {
                        return;
                    }
                    const sold = sub.external_sold_hours || 0;
                    const used = sub.external_hours_used || 0;
                    if (sold) subscriptionSoldTotal += parseFloat(sold) || 0;
                    if (used) subscriptionUsedTotal += parseFloat(used) || 0;
                } catch (error) {
                    console.warn('Error processing subscription:', error, sub);
                }
            });
        }

        // Sum from filtered sales orders
        if (Array.isArray(salesOrders)) {
            salesOrders.forEach(order => {
                try {
                    if (isStrategyAndProject(order.project_name, order.tags || [])) {
                        return;
                    }
                    const hours = order.external_hours || 0;
                    if (hours) salesOrderTotal += parseFloat(hours) || 0;
                } catch (error) {
                    console.warn('Error processing sales order:', error, order);
                }
            });
        }

        const stratSold = parseFloat(originalTotals?.strategy_and_external_hours_sold) || 0;
        const stratUsed = parseFloat(originalTotals?.strategy_and_external_hours_used) || 0;
        const totalSold = subscriptionSoldTotal + salesOrderTotal + stratSold;
        const totalUsed = subscriptionUsedTotal + salesOrderTotal + stratUsed;

        return {
            external_hours_sold: totalSold,
            external_hours_used: totalUsed,
            strategy_and_external_hours_sold: stratSold,
            strategy_and_external_hours_used: stratUsed,
            comparison_sold: originalTotals?.comparison_sold || null,
            comparison_used: originalTotals?.comparison_used || null,
        };
    };

    /**
     * Recalculate external hours by agreement type from filtered data
     * @param {Array} subscriptions - Filtered subscriptions
     * @param {Array} salesOrders - Filtered sales orders
     * @returns {Object} Recalculated totals by agreement type
     */
    export const recalculateExternalHoursByAgreement = (subscriptions, salesOrders, strategySoldAdj, strategyUsedAdj) => {
        const ss = parseFloat(strategySoldAdj) || 0;
        const su = parseFloat(strategyUsedAdj) || 0;
        const soldTotals = {
            Retainer: 0.0,
            Framework: 0.0,
            'Ad Hoc': 0.0,
            Unknown: 0.0,
            'Strategy&': ss,
        };
        const usedTotals = {
            Retainer: 0.0,
            Framework: 0.0,
            'Ad Hoc': 0.0,
            Unknown: 0.0,
            'Strategy&': su,
        };

        // Helper to categorize agreement type
        const categorizeAgreement = (agreementType, tags) => {
            if (!agreementType) return 'Unknown';
            const normalized = String(agreementType).trim().toLowerCase();
            if (normalized.includes('retainer') || normalized.includes('subscription')) return 'Retainer';
            if (normalized.includes('framework')) return 'Framework';
            if (normalized.includes('ad hoc') || normalized.includes('adhoc')) return 'Ad Hoc';
            return 'Unknown';
        };

        // Process filtered subscriptions
        if (Array.isArray(subscriptions)) {
            subscriptions.forEach(sub => {
                try {
                    if (isStrategyAndProject(sub.project_name, sub.tags || [])) {
                        return;
                    }
                    const agreementType = sub.agreement_type || 'Unknown';
                    const tags = Array.isArray(sub.tags) ? sub.tags : [];
                    const category = categorizeAgreement(agreementType, tags);

                    const sold = sub.external_sold_hours || 0;
                    const used = sub.external_hours_used || 0;
                    if (sold) soldTotals[category] += parseFloat(sold) || 0;
                    if (used) usedTotals[category] += parseFloat(used) || 0;
                } catch (error) {
                    console.warn('Error processing subscription for agreement totals:', error, sub);
                }
            });
        }

        // Process filtered sales orders
        if (Array.isArray(salesOrders)) {
            salesOrders.forEach(order => {
                try {
                    if (isStrategyAndProject(order.project_name, order.tags || [])) {
                        return;
                    }
                    const agreementType = order.agreement_type || 'Unknown';
                    const tags = Array.isArray(order.tags) ? order.tags : [];
                    const category = categorizeAgreement(agreementType, tags);

                    const hours = order.external_hours || 0;
                    if (hours) {
                        const hoursValue = parseFloat(hours) || 0;
                        soldTotals[category] += hoursValue;
                        usedTotals[category] += hoursValue;
                    }
                } catch (error) {
                    console.warn('Error processing sales order for agreement totals:', error, order);
                }
            });
        }

        return { sold: soldTotals, used: usedTotals };
    };
