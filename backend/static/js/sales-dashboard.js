// Sales Dashboard Tab Functionality
document.addEventListener("DOMContentLoaded", () => {
    /**
     * Format decimal hours to hh:mm format (e.g., 17.33 -> "17:20")
     * @param {number} decimalHours - Hours as decimal (e.g., 17.33)
     * @returns {string} Formatted string (e.g., "17:20")
     */
    const formatHoursToMinutes = (decimalHours) => {
        const hours = parseFloat(decimalHours) || 0;
        const totalMinutes = Math.round(hours * 60);
        const h = Math.floor(totalMinutes / 60);
        const m = totalMinutes % 60;
        return `${h}:${m.toString().padStart(2, '0')}`;
    };

    // Sales dashboard elements
    const salesInvoiceCount = document.querySelector('[data-sales-invoice-count]');
    const salesTrendContainer = document.querySelector('[data-sales-trend-container]');
    const salesComparison = document.querySelector('[data-sales-comparison]');
    const salesTrendIcon = document.querySelector('[data-sales-trend-icon]');
    const salesTrendText = document.querySelector('[data-sales-trend-text]');

    // Sales Order elements
    const salesOrderCount = document.querySelector('[data-sales-order-count]');
    const salesOrderTrend = document.querySelector('[data-sales-order-trend]');
    const salesOrderListBody = document.querySelector('[data-sales-order-list]');

    // Subscription elements
    const salesSubscriptionCount = document.querySelector('[data-sales-subscription-count]');
    const salesSubscriptionTrend = document.querySelector('[data-sales-subscription-trend]');

    const monthSelect = document.querySelector('[data-month-select]');
    const tabButtons = document.querySelectorAll('[data-dashboard-tab]');

    // Invoice list elements
    const toggleInvoiceListBtn = document.querySelector('[data-toggle-invoice-list]');
    const invoiceListContainer = document.querySelector('[data-invoice-list-container]');
    const invoiceListBody = document.querySelector('[data-invoice-list-body]');
    const debugInvoiceCount = document.querySelector('[data-debug-invoice-count]');
    const toggleSalesOrderListBtn = document.querySelector('[data-toggle-sales-order-list]');
    const salesOrderListContainer = document.querySelector('[data-sales-order-list-container]');

    let salesDataCache = {}; // Cache by month
    let currentMonth = monthSelect ? monthSelect.value : null;
    let isLoading = false;
    let salesDataLoadingPromise = null; // Track loading promise to avoid duplicate requests
    let currentFilterState = { hasActiveFilters: false }; // Current filter state (default to no filters)

    // Toggle invoice list visibility
    if (toggleInvoiceListBtn && invoiceListContainer) {
        toggleInvoiceListBtn.addEventListener('click', () => {
            const isHidden = invoiceListContainer.classList.contains('hidden');
            if (isHidden) {
                invoiceListContainer.classList.remove('hidden');
                toggleInvoiceListBtn.textContent = 'Hide Details';
            } else {
                invoiceListContainer.classList.add('hidden');
                toggleInvoiceListBtn.textContent = 'Show Details';
            }
        });
    }

    // Toggle sales order list visibility
    if (toggleSalesOrderListBtn && salesOrderListContainer) {
        toggleSalesOrderListBtn.addEventListener('click', () => {
            const isHidden = salesOrderListContainer.classList.contains('hidden');
            if (isHidden) {
                salesOrderListContainer.classList.remove('hidden');
                toggleSalesOrderListBtn.textContent = 'Hide Details';
            } else {
                salesOrderListContainer.classList.add('hidden');
                toggleSalesOrderListBtn.textContent = 'Show Details';
            }
        });
    }

    /**
     * Apply filters to a list of items
     * @param {Array} items - Array of items to filter
     * @returns {Array} Filtered array
     */
    const applyFilters = (items) => {
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

    /**
     * Build a sales stats object that reflects the current filters by overriding
     * invoice_count and sales_order_count (and their arrays) with filtered values.
     * @param {Object} baseStats - Original sales stats from the API/cache
     * @returns {Object|null} New stats object with filtered counts applied
     */
    const getSalesStatsForCurrentFilters = (baseStats) => {
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

    /**
     * Normalize agreement type using SalesFilters helper when available
     */
    const normalizeAgreementTypeSafe = (value) => {
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
    const recalculateAgreementTypeTotals = (invoices, fallbackTotals = null) => {
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
     * Get agreement totals adjusted for current filters
     * @param {Object} baseTotals - Totals from the API/cache
     * @param {Array} invoices - Invoice list to recalc from if filtered
     * @returns {Object|null} Totals respecting current filters
     */
    const getAgreementTotalsForCurrentFilters = (baseTotals, invoices) => {
        if (!currentFilterState || !currentFilterState.hasActiveFilters) {
            return baseTotals;
        }
        const filteredInvoices = Array.isArray(invoices) ? applyFilters(invoices) : invoices;
        return recalculateAgreementTypeTotals(filteredInvoices, baseTotals);
    };

    /**
     * Build filtered monthly invoiced series using breakdown rows (by month/market/agreement/account).
     * Falls back to the base series if filters are not active or breakdown data is missing.
     */
    const getInvoicedSeriesForCurrentFilters = (baseSeries, breakdownRows) => {
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

    /**
     * Build filtered monthly sales orders series using breakdown rows (by month/market/agreement/account).
     * Falls back to the base series if filters are not active or breakdown data is missing.
     */
    const getSalesOrdersSeriesForCurrentFilters = (baseSeries, breakdownRows) => {
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

    /**
     * Recalculate sales orders agreement totals from filtered orders
     */
    const recalculateSalesOrdersAgreementTotals = (salesOrders, fallbackTotals = null) => {
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
    const recalculateSalesOrdersProjectTotals = (salesOrders, fallbackTotals = null) => {
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

    /**
     * Get sales orders agreement totals adjusted for current filters
     */
    const getSalesOrdersAgreementTotalsForCurrentFilters = (baseTotals, salesOrders) => {
        if (!currentFilterState || !currentFilterState.hasActiveFilters) {
            return baseTotals;
        }
        const filteredOrders = Array.isArray(salesOrders) ? applyFilters(salesOrders) : salesOrders;
        return recalculateSalesOrdersAgreementTotals(filteredOrders, baseTotals);
    };

    /**
     * Get sales orders project totals adjusted for current filters
     */
    const getSalesOrdersProjectTotalsForCurrentFilters = (baseTotals, salesOrders) => {
        if (!currentFilterState || !currentFilterState.hasActiveFilters) {
            return baseTotals;
        }
        const filteredOrders = Array.isArray(salesOrders) ? applyFilters(salesOrders) : salesOrders;
        return recalculateSalesOrdersProjectTotals(filteredOrders, baseTotals);
    };

    // Function to render invoice list
    const renderInvoiceList = (invoices) => {
        if (!invoiceListBody || !Array.isArray(invoices)) return;
        
        // Apply filters
        const filteredInvoices = applyFilters(invoices);

        // Update table header
        const tableHead = document.querySelector('[data-invoice-list-container] thead tr');
        if (tableHead) {
            tableHead.innerHTML = `
        <th class="px-4 py-3 font-semibold text-slate-700">#</th>
        <th class="px-4 py-3 font-semibold text-slate-700">Invoice Number</th>
        <th class="px-4 py-3 font-semibold text-slate-700">Date</th>
        <th class="px-4 py-3 font-semibold text-slate-700">Partner</th>
        <th class="px-4 py-3 font-semibold text-slate-700">Project</th>
        <th class="px-4 py-3 font-semibold text-slate-700">Market</th>
        <th class="px-4 py-3 font-semibold text-slate-700">Agreement</th>
        <th class="px-4 py-3 font-semibold text-slate-700">Tags</th>
        <th class="px-4 py-3 font-semibold text-slate-700">AED Total</th>
        <th class="px-4 py-3 font-semibold text-slate-700">State</th>
        <th class="px-4 py-3 font-semibold text-slate-700">Payment</th>
      `;
        }

        if (invoices.length === 0) {
            invoiceListBody.innerHTML = `
        <tr>
          <td colspan="11" class="px-4 py-8 text-center text-slate-500">
            ${invoices.length === 0 ? 'No invoices found for selected month' : 'No invoices match the selected filters'}
          </td>
        </tr>
      `;
            if (debugInvoiceCount) {
                debugInvoiceCount.textContent = String(filteredInvoices.length);
            }
            return;
        }

        invoiceListBody.innerHTML = filteredInvoices.map((invoice, index) => {
            const partnerName = Array.isArray(invoice.partner_id) ? invoice.partner_id[1] : 'N/A';
            const aedTotal = invoice.x_studio_aed_total ? parseFloat(invoice.x_studio_aed_total).toLocaleString('en-AE', { style: 'currency', currency: 'AED' }) : '0.00 AED';
            const tags = Array.isArray(invoice.tags) ? invoice.tags.join(', ') : '';

            return `
        <tr class="hover:bg-slate-50">
          <td class="px-4 py-3 text-slate-600">${index + 1}</td>
          <td class="px-4 py-3 font-medium text-slate-900">${invoice.name || 'N/A'}</td>
          <td class="px-4 py-3 text-slate-600">${invoice.invoice_date || 'N/A'}</td>
          <td class="px-4 py-3 text-slate-600 max-w-xs truncate" title="${partnerName}">${partnerName}</td>
          <td class="px-4 py-3 text-slate-600 max-w-xs truncate" title="${invoice.project_name}">${invoice.project_name}</td>
          <td class="px-4 py-3 text-slate-600">${invoice.market}</td>
          <td class="px-4 py-3 text-slate-600">${invoice.agreement_type}</td>
          <td class="px-4 py-3 text-slate-600 max-w-xs truncate" title="${tags}">${tags}</td>
          <td class="px-4 py-3 font-medium text-slate-900">${aedTotal}</td>
          <td class="px-4 py-3">
            <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${invoice.state === 'posted' ? 'bg-green-100 text-green-800' :
                    invoice.state === 'draft' ? 'bg-gray-100 text-gray-800' :
                        'bg-red-100 text-red-800'
                }">
              ${invoice.state || 'N/A'}
            </span>
          </td>
          <td class="px-4 py-3">
            <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${invoice.payment_state === 'paid' ? 'bg-blue-100 text-blue-800' :
                    invoice.payment_state === 'reversed' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'
                }">
              ${invoice.payment_state || 'N/A'}
            </span>
          </td>
        </tr>
      `;
        }).join('');

        if (debugInvoiceCount) {
            debugInvoiceCount.textContent = invoices.length.toString();
        }
    };

    // Function to render sales orders grouped by project
    const renderSalesOrdersGroupedByProject = (orders) => {
        const tbody = document.getElementById('salesOrdersGroupedTableBody');
        if (!tbody || !Array.isArray(orders)) return;
        
        // Apply filters
        const filteredOrders = applyFilters(orders);

        if (filteredOrders.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="px-4 py-8 text-center text-slate-500">
                        No sales orders found for selected month
                    </td>
                </tr>
            `;
            return;
        }

        // Group orders by project and sum Ext. Hrs, Int. Hrs, and Total (AED)
        const groupedByProject = {};
        filteredOrders.forEach(order => {
            const projectName = order.project_name || 'Unassigned Project';
            const projectId = order.project_id || `unassigned-${projectName}`;
            
            if (!groupedByProject[projectId]) {
                groupedByProject[projectId] = {
                    project_id: order.project_id,
                    project_name: projectName,
                    market: order.market || 'Unassigned Market',
                    agreement_type: order.agreement_type || 'Unknown',
                    tags: order.tags || [],
                    total_ext_hrs: 0.0,
                    total_int_hrs: 0.0,
                    total_aed: 0.0
                };
            }
            
            // Sum external hours
            const extHrs = order.external_hours || 0;
            if (extHrs) {
                try {
                    groupedByProject[projectId].total_ext_hrs += parseFloat(extHrs);
                } catch (e) {
                    // Ignore invalid values
                }
            }
            
            // Sum internal hours
            const intHrs = order.internal_hours || 0;
            if (intHrs) {
                try {
                    groupedByProject[projectId].total_int_hrs += parseFloat(intHrs);
                } catch (e) {
                    // Ignore invalid values
                }
            }
            
            // Sum AED total
            const aedTotal = order.x_studio_aed_total || 0;
            if (aedTotal) {
                try {
                    groupedByProject[projectId].total_aed += parseFloat(aedTotal);
                } catch (e) {
                    // Ignore invalid values
                }
            }
        });

        // Convert to array and sort by project name
        const projectGroups = Object.values(groupedByProject).sort((a, b) => 
            a.project_name.localeCompare(b.project_name)
        );

        // Build table HTML
        let html = '';
        projectGroups.forEach((group) => {
            const tagsDisplay = Array.isArray(group.tags) ? group.tags.join(', ') : '';
            const extHrsFormatted = group.total_ext_hrs.toFixed(2);
            const intHrsFormatted = formatHoursToMinutes(group.total_int_hrs);
            const aedTotalFormatted = group.total_aed.toLocaleString('en-AE', { style: 'currency', currency: 'AED' });
            
            html += `
                <tr class="hover:bg-slate-50">
                    <td class="px-4 py-3 font-medium text-slate-900">${group.project_name}</td>
                    <td class="px-4 py-3 text-slate-600">${group.market}</td>
                    <td class="px-4 py-3 text-slate-600">${group.agreement_type}</td>
                    <td class="px-4 py-3 text-slate-600 max-w-xs truncate" title="${tagsDisplay}">${tagsDisplay || '-'}</td>
                    <td class="px-4 py-3 font-medium text-slate-900 text-right">${extHrsFormatted}</td>
                    <td class="px-4 py-3 font-medium text-slate-900 text-right">${intHrsFormatted}</td>
                    <td class="px-4 py-3 font-medium text-slate-900 text-right">${aedTotalFormatted}</td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    };

    // Function to render sales order list
    const renderSalesOrderList = (orders) => {
        if (!salesOrderListBody || !Array.isArray(orders)) return;
        
        // Apply filters
        const filteredOrders = applyFilters(orders);

        if (filteredOrders.length === 0) {
            salesOrderListBody.innerHTML = `
        <tr>
          <td colspan="9" class="px-4 py-8 text-center text-slate-500">
            No sales orders found for selected month
          </td>
        </tr>
      `;
            return;
        }

        salesOrderListBody.innerHTML = orders.map((order, index) => {
            const aedTotal = order.x_studio_aed_total ? parseFloat(order.x_studio_aed_total).toLocaleString('en-AE', { style: 'currency', currency: 'AED' }) : '0.00 AED';
            const tags = Array.isArray(order.tags) ? order.tags.join(', ') : '';
            const externalHours = order.external_hours !== undefined ? parseFloat(order.external_hours).toFixed(2) : '0.00';
            const internalHours = order.internal_hours !== undefined ? formatHoursToMinutes(order.internal_hours) : '0:00';

            return `
        <tr class="hover:bg-slate-50">
          <td class="px-4 py-3 font-medium text-slate-900">${order.name || 'N/A'}</td>
          <td class="px-4 py-3 text-slate-600">${order.date_order ? order.date_order.split(' ')[0] : 'N/A'}</td>
          <td class="px-4 py-3 text-slate-600 max-w-xs truncate" title="${order.project_name}">${order.project_name}</td>
          <td class="px-4 py-3 text-slate-600">${order.market}</td>
          <td class="px-4 py-3 text-slate-600">${order.agreement_type}</td>
          <td class="px-4 py-3 text-slate-600 max-w-xs truncate" title="${tags}">${tags}</td>
          <td class="px-4 py-3 font-medium text-slate-900 text-right">${externalHours}</td>
          <td class="px-4 py-3 font-medium text-slate-900 text-right">${internalHours}</td>
          <td class="px-4 py-3 font-medium text-slate-900 text-right">${aedTotal}</td>
        </tr>
      `;
        }).join('');
    };

    const calculateComparison = (current, previous) => {
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

    const computeFilterComparisonFromBreakdown = (breakdown, monthKey, filterState) => {
        if (!Array.isArray(breakdown) || !filterState || !filterState.hasActiveFilters) return null;
        if (!monthKey) return null;

        const parts = String(monthKey).split("-");
        if (parts.length !== 2) return null;
        const targetYear = Number(parts[0]);
        const targetMonth = Number(parts[1]);
        if (!targetYear || !targetMonth) return null;

        const prevMonth = targetMonth === 1 ? 12 : targetMonth - 1;
        const prevYear = targetMonth === 1 ? targetYear - 1 : targetYear;

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

        const sumFor = (year, month) => {
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

        const currentTotal = sumFor(targetYear, targetMonth);
        const previousTotal = sumFor(prevYear, prevMonth);
        return calculateComparison(currentTotal, previousTotal);
    };

    const getPrevMonthKey = (monthKey) => {
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

    // Function to update sales UI with data
    const updateSalesUI = (salesStats, subscriptionStats, comparisonOverrides = {}) => {
        const {
            invoiceComparisonOverride = null,
            salesOrderComparisonOverride = null,
            subscriptionComparisonOverride = null,
        } = comparisonOverrides;
        if (!salesStats) return;

        // Update invoice count
        if (salesInvoiceCount) {
            salesInvoiceCount.textContent = salesStats.invoice_count.toLocaleString();
        }

        // Update sales order count
        if (salesOrderCount && salesStats.sales_order_count !== undefined) {
            salesOrderCount.textContent = salesStats.sales_order_count.toLocaleString();
        }

        // Update subscription count + trend
        let totalSubscriptions = null;
        if (salesSubscriptionCount) {
            if (subscriptionStats && typeof subscriptionStats === 'object') {
                const totalFromStats = Number(subscriptionStats.total_subscriptions);
                if (!Number.isNaN(totalFromStats)) {
                    totalSubscriptions = totalFromStats;
                } else {
                    const activeCount = Number(subscriptionStats.active_count);
                    const churnedCount = Number(subscriptionStats.churned_count);
                    if (!Number.isNaN(activeCount) && !Number.isNaN(churnedCount)) {
                        totalSubscriptions = activeCount + churnedCount;
                    }
                }

                if (totalSubscriptions !== null) {
                    salesSubscriptionCount.textContent = totalSubscriptions.toLocaleString();
                    salesSubscriptionCount.classList.remove('opacity-50');
                }
            }
        }

        // Subscription trend removed per user request

        // Update invoice trend comparison
        const invoiceComp = invoiceComparisonOverride || salesStats.comparison;
        if (invoiceComp && salesComparison) {
            const { change_percentage, trend } = invoiceComp;

            // Show comparison container
            salesComparison.classList.remove('opacity-0');

            // Update trend icon
            if (salesTrendIcon) {
                const isFlat = trend === 'flat' || change_percentage === 0;
                salesTrendIcon.textContent = isFlat ? 'trending_flat' : (trend === 'up' ? 'trending_up' : 'trending_down');
            }

            // Update trend text
            if (salesTrendText) {
                salesTrendText.textContent = `${change_percentage.toFixed(1)}% vs last month`;
            }

            // Update colors based on trend
            const isFlat = trend === 'flat' || change_percentage === 0;
            salesComparison.classList.remove('text-rose-600', 'text-emerald-600', 'text-slate-500');
            if (isFlat) {
                salesComparison.classList.add('text-slate-500');
            } else if (trend === 'up') {
                salesComparison.classList.add('text-emerald-600');
            } else {
                salesComparison.classList.add('text-rose-600');
            }
        } else {
            // Hide comparison if no data
            if (salesComparison) {
                salesComparison.classList.add('opacity-0');
            }
        }

        // Update sales order trend comparison
        const salesOrderComp = salesOrderComparisonOverride || salesStats.sales_order_comparison;
        if (salesOrderComp && salesOrderTrend) {
            const { change_percentage, trend } = salesOrderComp;

            const isFlat = trend === 'flat' || change_percentage === 0;
            const icon = isFlat ? 'trending_flat' : (trend === 'up' ? 'trending_up' : 'trending_down');
            const colorClass = isFlat ? 'text-slate-500' : (trend === 'up' ? 'text-emerald-600' : 'text-rose-600');

            salesOrderTrend.innerHTML = `
                <span class="material-symbols-rounded align-bottom text-lg ${colorClass}">${icon}</span>
                <span class="${colorClass}">${change_percentage.toFixed(1)}% vs last month</span>
            `;
        } else if (salesOrderTrend) {
            salesOrderTrend.innerHTML = '';
        }
    };

    // Chart instances
    let invoicedChart = null;
    let agreementTypeChart = null;
    let salesOrdersChart = null;
    let salesOrdersAgreementTypeChart = null;

    // Register the datalabels plugin
    Chart.register(ChartDataLabels);

    // Function to init/update agreement type chart (horizontal bar chart)
    const updateAgreementTypeChart = (agreementTotals) => {
        const ctx = document.getElementById('agreementTypeChart');
        if (!ctx) return;

        // Ensure we have all required agreement types
        const totals = {
            'Retainer': agreementTotals?.Retainer || 0,
            'Framework': agreementTotals?.Framework || 0,
            'Ad Hoc': agreementTotals?.['Ad Hoc'] || 0,
            'Unknown': agreementTotals?.Unknown || 0,
        };

        // Filter out agreement types with zero or no invoices
        const filteredTotals = {};
        Object.keys(totals).forEach(key => {
            const value = totals[key];
            if (value !== null && value !== undefined && value > 0) {
                filteredTotals[key] = value;
            }
        });

        // If no data, don't render chart
        if (Object.keys(filteredTotals).length === 0) {
            if (agreementTypeChart) {
                agreementTypeChart.destroy();
                agreementTypeChart = null;
            }
            return;
        }

        const labels = Object.keys(filteredTotals);
        const data = Object.values(filteredTotals);

        // Match the monthly invoiced chart style but keep horizontal bars
        const barColor = '#5AA0F9'; // Same blue as monthly invoiced chart
        const hoverColor = '#4a8ee6'; // Slightly darker blue on hover

        if (agreementTypeChart) {
            // If chart exists but no data, destroy it
            if (labels.length === 0) {
                agreementTypeChart.destroy();
                agreementTypeChart = null;
                return;
            }
            agreementTypeChart.data.labels = labels;
            agreementTypeChart.data.datasets[0].data = data;
            agreementTypeChart.update('active');
        } else {
            agreementTypeChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Invoiced Amount (AED)',
                        data: data,
                        backgroundColor: barColor,
                        borderColor: barColor,
                        borderWidth: 0,
                        borderRadius: 4,
                        borderSkipped: false,
                        barThickness: 'flex',
                        maxBarThickness: 50,
                        hoverBackgroundColor: hoverColor,
                    }]
                },
                options: {
                    indexAxis: 'y', // Horizontal bars - agreement types on Y-axis
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: {
                        padding: {
                            right: 20 // Add padding for value labels
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            backgroundColor: 'rgba(15, 23, 42, 0.9)', // slate-900
                            titleColor: '#fff',
                            bodyColor: '#fff',
                            padding: 12,
                            cornerRadius: 8,
                            displayColors: false,
                            callbacks: {
                                label: function (context) {
                                    if (context.parsed.x !== null) {
                                        return new Intl.NumberFormat('en-AE', { style: 'currency', currency: 'AED' }).format(context.parsed.x);
                                    }
                                    return '';
                                }
                            }
                        },
                        datalabels: {
                            anchor: 'end',
                            align: 'end',
                            color: '#64748b',
                            font: {
                                weight: 'bold',
                                size: 11
                            },
                            formatter: function (value) {
                                if (value >= 1000000) {
                                    return (value / 1000000).toFixed(1) + 'M';
                                } else if (value >= 1000) {
                                    return (value / 1000).toFixed(0) + 'k';
                                }
                                return value;
                            }
                        },
                        y: {
                            grid: {
                                display: false,
                                drawBorder: false
                            },
                            ticks: {
                                color: '#64748b', // slate-500 - keep agreement type labels
                                font: {
                                    size: 12,
                                    weight: 500
                                },
                                padding: 12
                            }
                        }
                    }
                }
            });
        }
    };

    // Function to init/update chart
    const updateInvoicedChart = (seriesData) => {
        const ctx = document.getElementById('invoicedChart');
        if (!ctx) return;

        const labels = seriesData.map(d => d.label);
        const currentYearData = seriesData.map(d => d.amount_aed);
        const previousYearData = seriesData.map(d => d.previous_year_amount_aed || 0);
        const hasPreviousYear = seriesData.some(d => d.previous_year_amount_aed !== undefined);
        const currentYear = seriesData.length > 0 ? seriesData[0].year : new Date().getFullYear();
        const previousYear = currentYear - 1;

        if (invoicedChart) {
            invoicedChart.data.labels = labels;

            // Update datasets maintaining order: previous year first, current year second
            if (hasPreviousYear) {
                if (invoicedChart.data.datasets.length >= 2) {
                    // Update existing datasets
                    invoicedChart.data.datasets[0].data = previousYearData; // Previous year (yellow) - behind
                    invoicedChart.data.datasets[1].data = currentYearData; // Current year (blue) - in front
                } else if (invoicedChart.data.datasets.length === 1) {
                    // Add previous year dataset before current year
                    invoicedChart.data.datasets.unshift({
                        label: `${previousYear}`,
                        data: previousYearData,
                        backgroundColor: '#fbbf24', // Yellow-400
                        borderColor: '#fbbf24',
                        borderWidth: 0,
                        borderRadius: 6,
                        borderSkipped: false,
                        barThickness: 40,
                        hoverBackgroundColor: '#f59e0b', // Yellow-500 on hover
                    });
                    invoicedChart.data.datasets[1].label = `${currentYear}`;
                }
            } else {
                // No previous year data, just update current year
                if (invoicedChart.data.datasets.length > 0) {
                    invoicedChart.data.datasets[0].data = currentYearData;
                    invoicedChart.data.datasets[0].label = `${currentYear}`;
                }
                // Remove previous year dataset if it exists
                if (invoicedChart.data.datasets.length > 1) {
                    invoicedChart.data.datasets.shift();
                }
            }
            invoicedChart.update('active');
        } else {
            // Order: previous year first (behind), current year second (in front)
            const datasets = [];

            // Add previous year dataset first (will be behind)
            if (hasPreviousYear) {
                datasets.push({
                    label: `${previousYear}`,
                    data: previousYearData,
                    backgroundColor: '#fbbf24', // Yellow-400
                    borderColor: '#fbbf24',
                    borderWidth: 0,
                    borderRadius: 6,
                    borderSkipped: false,
                    barThickness: 40,
                    hoverBackgroundColor: '#f59e0b', // Yellow-500 on hover
                });
            }

            // Add current year dataset second (will be in front)
            datasets.push({
                label: `${currentYear}`,
                data: currentYearData,
                backgroundColor: '#5AA0F9', // Custom blue
                borderColor: '#5AA0F9',
                borderWidth: 0,
                borderRadius: 6,
                borderSkipped: false,
                barThickness: 40,
                hoverBackgroundColor: '#4a8ee6', // Slightly darker blue on hover
            });

            invoicedChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    // Make bars wider for better overlap visibility
                    barPercentage: 0.8,
                    categoryPercentage: 0.9,
                    layout: {
                        padding: {
                            top: 20,
                            bottom: 6
                        }
                    },
                    plugins: {
                        legend: {
                            display: hasPreviousYear,
                            position: 'bottom',
                            labels: {
                                usePointStyle: true,
                                padding: 15,
                                font: {
                                    size: 12,
                                    weight: 500
                                },
                                color: '#64748b'
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(15, 23, 42, 0.9)', // slate-900
                            titleColor: '#fff',
                            bodyColor: '#fff',
                            padding: 12,
                            cornerRadius: 8,
                            displayColors: true,
                            callbacks: {
                                label: function (context) {
                                    if (context.parsed.y !== null) {
                                        return `${context.dataset.label}: ${new Intl.NumberFormat('en-AE', { style: 'currency', currency: 'AED' }).format(context.parsed.y)}`;
                                    }
                                    return '';
                                }
                            }
                        },
                        datalabels: {
                            anchor: 'end',
                            align: 'top',
                            rotation: -90,
                            offset: 4,
                            color: '#475569',
                            font: {
                                family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                                weight: 'bold',
                                size: 12,
                                style: 'normal'
                            },
                            formatter: function (value) {
                                if (value >= 1000000) {
                                    return (value / 1000000).toFixed(1) + 'M';
                                } else if (value >= 1000) {
                                    return (value / 1000).toFixed(0) + 'k';
                                }
                                return value;
                            }
                        },
                        // Plugin to create overlapping effect - blue bars overlap yellow bars
                        afterLayout: function (chart) {
                            if (!hasPreviousYear || chart.data.datasets.length < 2) return;

                            const meta0 = chart.getDatasetMeta(0); // Previous year (yellow) - behind
                            const meta1 = chart.getDatasetMeta(1); // Current year (blue) - in front

                            // Calculate overlap: blue bars should overlap yellow bars
                            // Get the width of bars to calculate proper overlap
                            if (meta0.data.length === 0 || meta1.data.length === 0) return;

                            const yellowBar = meta0.data[0];
                            const blueBar = meta1.data[0];
                            if (!yellowBar || !blueBar) return;

                            const barWidth = yellowBar.width || blueBar.width || 30;
                            const overlapAmount = barWidth * 0.5; // Overlap by 50% of bar width for clear overlap

                            meta1.data.forEach((bar, index) => {
                                if (bar && meta0.data[index]) {
                                    // Position blue bar to overlap yellow bar from the left
                                    // Blue bar's center should be offset to the left to create overlap
                                    const yellowBarX = meta0.data[index].x;
                                    // Move blue bar to the left so it overlaps the yellow bar
                                    bar.x = yellowBarX - overlapAmount;
                                }
                            });
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            display: false, // Hide Y-axis completely
                            grid: {
                                display: false
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            },
                            ticks: {
                                color: '#64748b', // slate-500
                                font: {
                                    size: 12,
                                    weight: 500
                                }
                            }
                        }
                    }
                }
            });
        }
    };

    // Function to init/update Sales Orders agreement type chart (horizontal bar chart)
    const updateSalesOrdersAgreementTypeChart = (agreementTotals) => {
        const ctx = document.getElementById('salesOrdersAgreementTypeChart');
        if (!ctx) return;

        // Ensure we have all required agreement types
        const totals = {
            'Retainer': agreementTotals?.Retainer || 0,
            'Framework': agreementTotals?.Framework || 0,
            'Ad Hoc': agreementTotals?.['Ad Hoc'] || 0,
            'Unknown': agreementTotals?.Unknown || 0,
        };

        // Filter out agreement types with zero or no orders
        const filteredTotals = {};
        Object.keys(totals).forEach(key => {
            const value = totals[key];
            if (value !== null && value !== undefined && value > 0) {
                filteredTotals[key] = value;
            }
        });

        // If no data, don't render chart
        if (Object.keys(filteredTotals).length === 0) {
            if (salesOrdersAgreementTypeChart) {
                salesOrdersAgreementTypeChart.destroy();
                salesOrdersAgreementTypeChart = null;
            }
            return;
        }

        const labels = Object.keys(filteredTotals);
        const data = Object.values(filteredTotals);

        // Match the monthly invoiced chart style but keep horizontal bars
        const barColor = '#5AA0F9'; // Same blue as monthly invoiced chart
        const hoverColor = '#4a8ee6'; // Slightly darker blue on hover

        if (salesOrdersAgreementTypeChart) {
            // If chart exists but no data, destroy it
            if (labels.length === 0) {
                salesOrdersAgreementTypeChart.destroy();
                salesOrdersAgreementTypeChart = null;
                return;
            }
            salesOrdersAgreementTypeChart.data.labels = labels;
            salesOrdersAgreementTypeChart.data.datasets[0].data = data;
            salesOrdersAgreementTypeChart.update('active');
        } else {
            salesOrdersAgreementTypeChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Sales Orders Amount (AED)',
                        data: data,
                        backgroundColor: barColor,
                        borderColor: barColor,
                        borderWidth: 0,
                        borderRadius: 4,
                        borderSkipped: false,
                        barThickness: 'flex',
                        maxBarThickness: 50,
                        hoverBackgroundColor: hoverColor,
                    }]
                },
                options: {
                    indexAxis: 'y', // Horizontal bars - agreement types on Y-axis
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: {
                        padding: {
                            right: 20 // Add padding for value labels
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            backgroundColor: 'rgba(15, 23, 42, 0.9)', // slate-900
                            titleColor: '#fff',
                            bodyColor: '#fff',
                            padding: 12,
                            cornerRadius: 8,
                            displayColors: false,
                            callbacks: {
                                label: function (context) {
                                    if (context.parsed.x !== null) {
                                        return new Intl.NumberFormat('en-AE', { style: 'currency', currency: 'AED' }).format(context.parsed.x);
                                    }
                                    return '';
                                }
                            }
                        },
                        datalabels: {
                            anchor: 'end',
                            align: 'end',
                            color: '#64748b',
                            font: {
                                weight: 'bold',
                                size: 11
                            },
                            formatter: function (value) {
                                if (value >= 1000000) {
                                    return (value / 1000000).toFixed(1) + 'M';
                                } else if (value >= 1000) {
                                    return (value / 1000).toFixed(0) + 'k';
                                }
                                return value;
                            }
                        },
                        y: {
                            grid: {
                                display: false,
                                drawBorder: false
                            },
                            ticks: {
                                color: '#64748b', // slate-500 - keep agreement type labels
                                font: {
                                    size: 12,
                                    weight: 500
                                },
                                padding: 12
                            }
                        }
                    }
                }
            });
        }
    };

    // Function to render Sales Orders project cards
    const updateSalesOrdersProjectCards = (projectTotals) => {
        const container = document.getElementById('salesOrdersProjectCards');
        if (!container) return;

        // Ensure we have valid data
        if (!Array.isArray(projectTotals) || projectTotals.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center text-sm text-slate-500 py-8">No project data available for this month</div>';
            return;
        }

        // Filter out zero values and create cards
        const validProjects = projectTotals.filter(p => {
            const amount = p.total_amount_aed || 0;
            return amount > 0;
        });

        if (validProjects.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center text-sm text-slate-500 py-8">No project data available for this month</div>';
            return;
        }

        // Only show top 6 by amount (data is already sorted desc)
        const topProjects = validProjects.slice(0, 6);

        // Format currency helper
        const formatCurrency = (value) => {
            return new Intl.NumberFormat('en-AE', {
                style: 'currency',
                currency: 'AED',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        };

        // Create card HTML
        container.innerHTML = topProjects.map((project, index) => {
            const projectName = project.project_name || 'Unknown Project';
            const amount = project.total_amount_aed || 0;
            const formattedAmount = formatCurrency(amount);

            // Rank badge colors - gradient from gold to blue
            const rankColors = [
                'bg-gradient-to-br from-amber-400 to-amber-500', // 1st - Gold
                'bg-gradient-to-br from-slate-400 to-slate-500', // 2nd - Silver
                'bg-gradient-to-br from-amber-600 to-amber-700', // 3rd - Bronze
                'bg-gradient-to-br from-sky-400 to-sky-500',     // 4th - Blue
                'bg-gradient-to-br from-sky-500 to-sky-600',     // 5th - Darker Blue
                'bg-gradient-to-br from-slate-500 to-slate-600', // 6th - Slate
            ];

            const rankColor = rankColors[index] || 'bg-gradient-to-br from-slate-400 to-slate-500';

            return `
                <article class="group relative flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-sky-300 hover:shadow-md">
                    <div class="flex items-start justify-between gap-3">
                        <div class="flex-1 min-w-0">
                            <div class="mb-2 flex items-center gap-2">
                                <span class="inline-flex h-6 w-6 items-center justify-center rounded-full ${rankColor} text-xs font-bold text-white shadow-sm">
                                    ${index + 1}
                                </span>
                                <h4 class="truncate text-sm font-semibold text-slate-900" title="${projectName}">
                                    ${projectName}
                                </h4>
                            </div>
                            <p class="text-2xl font-bold text-emerald-600">
                                ${formattedAmount}
                            </p>
                        </div>
                    </div>
                </article>
            `;
        }).join('');
    };

    // Function to init/update Sales Orders chart
    const updateSalesOrdersChart = (seriesData) => {
        const ctx = document.getElementById('salesOrdersChart');
        if (!ctx) return;

        const labels = seriesData.map(d => d.label);
        const currentYearData = seriesData.map(d => d.amount_aed);
        const previousYearData = seriesData.map(d => d.previous_year_amount_aed || 0);
        const hasPreviousYear = seriesData.some(d => d.previous_year_amount_aed !== undefined);
        const currentYear = seriesData.length > 0 ? seriesData[0].year : new Date().getFullYear();
        const previousYear = currentYear - 1;

        if (salesOrdersChart) {
            salesOrdersChart.data.labels = labels;

            // Update datasets maintaining order: previous year first, current year second
            if (hasPreviousYear) {
                if (salesOrdersChart.data.datasets.length >= 2) {
                    // Update existing datasets
                    salesOrdersChart.data.datasets[0].data = previousYearData; // Previous year (yellow) - behind
                    salesOrdersChart.data.datasets[1].data = currentYearData; // Current year (blue) - in front
                } else if (salesOrdersChart.data.datasets.length === 1) {
                    // Add previous year dataset before current year
                    salesOrdersChart.data.datasets.unshift({
                        label: `${previousYear}`,
                        data: previousYearData,
                        backgroundColor: '#fbbf24', // Yellow-400
                        borderColor: '#fbbf24',
                        borderWidth: 0,
                        borderRadius: 6,
                        borderSkipped: false,
                        barThickness: 40,
                        hoverBackgroundColor: '#f59e0b', // Yellow-500 on hover
                    });
                    salesOrdersChart.data.datasets[1].label = `${currentYear}`;
                }
            } else {
                // No previous year data, just update current year
                if (salesOrdersChart.data.datasets.length > 0) {
                    salesOrdersChart.data.datasets[0].data = currentYearData;
                    salesOrdersChart.data.datasets[0].label = `${currentYear}`;
                }
                // Remove previous year dataset if it exists
                if (salesOrdersChart.data.datasets.length > 1) {
                    salesOrdersChart.data.datasets.shift();
                }
            }
            salesOrdersChart.update('active');
        } else {
            // Order: previous year first (behind), current year second (in front)
            const datasets = [];

            // Add previous year dataset first (will be behind)
            if (hasPreviousYear) {
                datasets.push({
                    label: `${previousYear}`,
                    data: previousYearData,
                    backgroundColor: '#fbbf24', // Yellow-400
                    borderColor: '#fbbf24',
                    borderWidth: 0,
                    borderRadius: 6,
                    borderSkipped: false,
                    barThickness: 40,
                    hoverBackgroundColor: '#f59e0b', // Yellow-500 on hover
                });
            }

            // Add current year dataset second (will be in front)
            datasets.push({
                label: `${currentYear}`,
                data: currentYearData,
                backgroundColor: '#5AA0F9', // Custom blue
                borderColor: '#5AA0F9',
                borderWidth: 0,
                borderRadius: 6,
                borderSkipped: false,
                barThickness: 40,
                hoverBackgroundColor: '#4a8ee6', // Slightly darker blue on hover
            });

            salesOrdersChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    // Make bars wider for better overlap visibility
                    barPercentage: 0.8,
                    categoryPercentage: 0.9,
                    layout: {
                        padding: {
                            top: 20,
                            bottom: 6
                        }
                    },
                    plugins: {
                        legend: {
                            display: hasPreviousYear,
                            position: 'bottom',
                            labels: {
                                usePointStyle: true,
                                padding: 15,
                                font: {
                                    size: 12,
                                    weight: 500
                                },
                                color: '#64748b'
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(15, 23, 42, 0.9)', // slate-900
                            titleColor: '#fff',
                            bodyColor: '#fff',
                            padding: 12,
                            cornerRadius: 8,
                            displayColors: true,
                            callbacks: {
                                label: function (context) {
                                    if (context.parsed.y !== null) {
                                        return `${context.dataset.label}: ${new Intl.NumberFormat('en-AE', { style: 'currency', currency: 'AED' }).format(context.parsed.y)}`;
                                    }
                                    return '';
                                }
                            }
                        },
                        datalabels: {
                            anchor: 'end',
                            align: 'top',
                            rotation: -90,
                            offset: 4,
                            color: '#475569',
                            font: {
                                family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                                weight: 'bold',
                                size: 12,
                                style: 'normal'
                            },
                            formatter: function (value) {
                                if (value >= 1000000) {
                                    return (value / 1000000).toFixed(1) + 'M';
                                } else if (value >= 1000) {
                                    return (value / 1000).toFixed(0) + 'k';
                                }
                                return value;
                            }
                        },
                        // Plugin to create overlapping effect - blue bars overlap yellow bars
                        afterLayout: function (chart) {
                            if (!hasPreviousYear || chart.data.datasets.length < 2) return;

                            const meta0 = chart.getDatasetMeta(0); // Previous year (yellow) - behind
                            const meta1 = chart.getDatasetMeta(1); // Current year (blue) - in front

                            // Calculate overlap: blue bars should overlap yellow bars
                            // Get the width of bars to calculate proper overlap
                            if (meta0.data.length === 0 || meta1.data.length === 0) return;

                            const yellowBar = meta0.data[0];
                            const blueBar = meta1.data[0];
                            if (!yellowBar || !blueBar) return;

                            const barWidth = yellowBar.width || blueBar.width || 30;
                            const overlapAmount = barWidth * 0.5; // Overlap by 50% of bar width for clear overlap

                            meta1.data.forEach((bar, index) => {
                                if (bar && meta0.data[index]) {
                                    // Position blue bar to overlap yellow bar from the left
                                    // Blue bar's center should be offset to the left to create overlap
                                    const yellowBarX = meta0.data[index].x;
                                    // Move blue bar to the left so it overlaps the yellow bar
                                    bar.x = yellowBarX - overlapAmount;
                                }
                            });
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            display: false, // Hide Y-axis completely
                            grid: {
                                display: false
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            },
                            ticks: {
                                color: '#64748b', // slate-500
                                font: {
                                    size: 12,
                                    weight: 500
                                }
                            }
                        }
                    }
                }
            });
        }
    };

    // Function to render subscription statistics card
    const updateSubscriptionStatsCard = (stats) => {
        const container = document.getElementById('subscriptionStatsCard');
        if (!container || !stats) return;

        const mrr = Number(stats.mrr) || 0;
        const activeCount = Number(stats.active_count) || 0;
        const churnedCount = Number(stats.churned_count) || 0;
        const newRenewCount = Number(stats.new_renew_count) || 0;
        const activeOrderNames = Array.isArray(stats.active_order_names) ? stats.active_order_names : [];

        // Format MRR for display (e.g., 5.2M)
        let mrrFormatted = '0';
        if (mrr >= 1000000) {
            mrrFormatted = (mrr / 1000000).toFixed(1) + 'M';
        } else if (mrr >= 1000) {
            mrrFormatted = (mrr / 1000).toFixed(1) + 'k';
        } else if (mrr > 0) {
            mrrFormatted = mrr.toLocaleString('en-US', { maximumFractionDigits: 1 });
        }

        // Format order names for tooltip
        const orderNamesTooltip = activeOrderNames.length > 0 
            ? activeOrderNames.join(', ')
            : 'No active orders';

        container.innerHTML = `
            <div class="flex flex-col items-center gap-6">
                <div class="text-center">
                    <div class="text-4xl font-bold text-slate-900">${mrrFormatted}</div>
                    <div class="mt-1 text-sm font-medium text-slate-600">MRR</div>
                </div>
                <div class="text-center">
                    <div class="text-4xl font-bold text-slate-900 relative group cursor-help" title="${orderNamesTooltip}" data-active-count>${activeCount}</div>
                    <div class="mt-1 text-sm font-medium text-slate-600">Active (In Progress)</div>
                </div>
                <div class="flex items-center justify-center gap-12">
                    <div class="text-center">
                        <div class="text-4xl font-bold text-slate-900">${newRenewCount}</div>
                        <div class="mt-1 text-sm font-medium text-slate-600">New Subs / Renewal</div>
                    </div>
                    <div class="text-center">
                        <div class="text-4xl font-bold text-slate-900" data-churned-count>${churnedCount}</div>
                        <div class="mt-1 text-sm font-medium text-slate-600">Churned</div>
                    </div>
                </div>
            </div>
        `;
    };

    /**
     * Re-render all filtered data when filters change
     */
    const reapplyFilters = () => {
        if (!currentMonth || !salesDataCache[currentMonth]) return;

        const data = salesDataCache[currentMonth];
        
        // Update filter state (safely)
        try {
            if (window.SalesFilters && typeof window.SalesFilters.getFilterState === 'function') {
                currentFilterState = window.SalesFilters.getFilterState();
            } else {
                currentFilterState = { hasActiveFilters: false };
            }
        } catch (error) {
            console.warn('Error getting filter state:', error);
            currentFilterState = { hasActiveFilters: false };
        }

        const salesStatsForFilters = data.sales_stats ? getSalesStatsForCurrentFilters(data.sales_stats) : null;
        const agreementTotalsForFilters = getAgreementTotalsForCurrentFilters(
            data.agreement_type_totals,
            salesStatsForFilters?.invoices || data.sales_stats?.invoices
        );
        const salesOrdersAgreementTotalsForFilters = getSalesOrdersAgreementTotalsForCurrentFilters(
            data.sales_orders_agreement_type_totals,
            salesStatsForFilters?.sales_orders || data.sales_stats?.sales_orders
        );
        const salesOrdersProjectTotalsForFilters = getSalesOrdersProjectTotalsForCurrentFilters(
            data.sales_orders_project_totals,
            salesStatsForFilters?.sales_orders || data.sales_stats?.sales_orders
        );
        const invoicedSeriesForFilters = getInvoicedSeriesForCurrentFilters(
            data.invoiced_series,
            data.invoiced_series_breakdown
        );
        const salesOrdersSeriesForFilters = getSalesOrdersSeriesForCurrentFilters(
            data.sales_orders_series,
            data.sales_orders_series_breakdown
        );
        const effectiveSalesStats = salesStatsForFilters || data.sales_stats;

        // Re-render filtered data
        if (effectiveSalesStats) {
            // Invoices
            if (effectiveSalesStats.invoices) {
                renderInvoiceList(effectiveSalesStats.invoices);
            }
            
            // Sales Orders
            if (effectiveSalesStats.sales_orders) {
                renderSalesOrderList(effectiveSalesStats.sales_orders);
                renderSalesOrdersGroupedByProject(effectiveSalesStats.sales_orders);
            }
        }

        // Subscriptions
        if (data.subscriptions) {
            updateSubscriptionsList(data.subscriptions);
            
            // Recalculate subscription stats from filtered data if filters are active
            if (currentFilterState && currentFilterState.hasActiveFilters) {
                const filteredSubscriptions = applyFilters(data.subscriptions);
                // Parse month from currentMonth (format: "YYYY-MM")
                let monthStart, monthEnd;
                if (currentMonth) {
                    const [year, month] = currentMonth.split('-').map(Number);
                    monthStart = new Date(year, month - 1, 1);
                    const lastDay = new Date(year, month, 0).getDate();
                    monthEnd = new Date(year, month - 1, lastDay);
                } else {
                    // Fallback to current month
                    const now = new Date();
                    monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
                    monthEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0);
                }
                const recalculatedStats = recalculateSubscriptionStats(filteredSubscriptions, monthStart, monthEnd);
                recalculatedStats.subscription_comparison = data.subscription_stats?.subscription_comparison || null;
                updateSubscriptionStatsCard(recalculatedStats);
                // Also update the total subscription count in the overview card
                if (salesSubscriptionCount) {
                    const totalSubscriptions = (Number(recalculatedStats.active_count) || 0) + (Number(recalculatedStats.churned_count) || 0);
                    salesSubscriptionCount.textContent = totalSubscriptions.toLocaleString();
                    salesSubscriptionCount.classList.remove('opacity-50');
                }
                // Update sales UI with filtered stats for total count
                let invoiceComparisonOverride = null;
                let salesOrderComparisonOverride = null;
                let subscriptionComparisonOverride = null;
                if (currentFilterState && currentFilterState.hasActiveFilters) {
                    invoiceComparisonOverride = computeFilterComparisonFromBreakdown(
                        data.invoiced_series_breakdown,
                        data.selected_month || currentMonth,
                        currentFilterState
                    );
                    salesOrderComparisonOverride = computeFilterComparisonFromBreakdown(
                        data.sales_orders_series_breakdown,
                        data.selected_month || currentMonth,
                        currentFilterState
                    );
                    
                    // Calculate subscription comparison using total_subscriptions from recalculated stats
                    console.log('[DEBUG] reapplyFilters: Recalculated subscription stats:', {
                        total_subscriptions: recalculatedStats.total_subscriptions,
                        active_count: recalculatedStats.active_count,
                        churned_count: recalculatedStats.churned_count
                    });
                    const monthKeyForComparison = data.selected_month || currentMonth;
                    const prevKey = getPrevMonthKey(monthKeyForComparison);
                    console.log('[DEBUG] reapplyFilters: Subscription comparison calculation:', {
                        monthKeyForComparison,
                        prevKey,
                        hasPrevMonthCache: !!(prevKey && salesDataCache[prevKey]),
                        hasPrevSubscriptions: !!(prevKey && salesDataCache[prevKey] && Array.isArray(salesDataCache[prevKey].subscriptions))
                    });
                    if (prevKey && salesDataCache[prevKey] && Array.isArray(salesDataCache[prevKey].subscriptions)) {
                        const prevSubsFiltered = applyFilters(salesDataCache[prevKey].subscriptions);
                        console.log('[DEBUG] reapplyFilters: Previous month filtered subscriptions count:', prevSubsFiltered.length);
                        // Calculate previous month bounds
                        const prevMonthParts = prevKey.split('-').map(Number);
                        const prevMonthStart = new Date(prevMonthParts[0], prevMonthParts[1] - 1, 1);
                        const prevLastDay = new Date(prevMonthParts[0], prevMonthParts[1], 0).getDate();
                        const prevMonthEnd = new Date(prevMonthParts[0], prevMonthParts[1] - 1, prevLastDay);
                        const prevStatsRecalculated = recalculateSubscriptionStats(prevSubsFiltered, prevMonthStart, prevMonthEnd);
                        console.log('[DEBUG] reapplyFilters: Previous month recalculated stats:', {
                            total_subscriptions: prevStatsRecalculated.total_subscriptions,
                            active_count: prevStatsRecalculated.active_count,
                            churned_count: prevStatsRecalculated.churned_count
                        });
                        
                        // Compare total_subscriptions from both recalculated stats
                        subscriptionComparisonOverride = calculateComparison(
                            recalculatedStats.total_subscriptions,
                            prevStatsRecalculated.total_subscriptions
                        );
                        console.log('[DEBUG] reapplyFilters: Calculated subscriptionComparisonOverride:', subscriptionComparisonOverride);
                    } else {
                        console.log('[DEBUG] reapplyFilters: Cannot calculate subscriptionComparisonOverride - previous month data not available');
                    }
                }

                console.log('[DEBUG] reapplyFilters: Calling updateSalesUI with comparison overrides:', {
                    invoiceComparisonOverride: invoiceComparisonOverride ? 'SET' : 'NULL',
                    salesOrderComparisonOverride: salesOrderComparisonOverride ? 'SET' : 'NULL',
                    subscriptionComparisonOverride: subscriptionComparisonOverride ? 'SET' : 'NULL',
                    subscriptionComparisonOverrideValue: subscriptionComparisonOverride
                });
                updateSalesUI(effectiveSalesStats, recalculatedStats, {
                    invoiceComparisonOverride,
                    salesOrderComparisonOverride,
                    subscriptionComparisonOverride,
                });
            } else if (data.subscription_stats) {
                // No filters active, use original stats and refresh the overview counts
                updateSubscriptionStatsCard(data.subscription_stats);
                updateSalesUI(effectiveSalesStats, data.subscription_stats, {
                    invoiceComparisonOverride: null,
                    salesOrderComparisonOverride: null,
                    subscriptionComparisonOverride: null,
                });
            }
        } else if (data.subscription_stats) {
            // No subscriptions but stats exist, use original
            updateSubscriptionStatsCard(data.subscription_stats);
            updateSalesUI(effectiveSalesStats, data.subscription_stats, {
                invoiceComparisonOverride: null,
                salesOrderComparisonOverride: null,
                subscriptionComparisonOverride: null,
            });
        }

        // External Hours - recalculate from filtered data if filters are active
        if (currentFilterState && currentFilterState.hasActiveFilters && data.external_hours_totals && data.subscriptions && data.sales_stats && data.sales_stats.sales_orders) {
            const filteredSubscriptions = applyFilters(data.subscriptions);
            const filteredSalesOrders = applyFilters(data.sales_stats.sales_orders);
            
            const recalculatedTotals = recalculateExternalHoursTotals(
                filteredSubscriptions,
                filteredSalesOrders,
                data.external_hours_totals
            );
            updateExternalHoursCard(recalculatedTotals);
            
            if (data.external_hours_by_agreement) {
                const recalculatedByAgreement = recalculateExternalHoursByAgreement(
                    filteredSubscriptions,
                    filteredSalesOrders
                );
                updateExternalHoursAgreementTable(recalculatedByAgreement);
            }
        } else if (data.external_hours_totals) {
            // No filters active, use original data
            updateExternalHoursCard(data.external_hours_totals);
            if (data.external_hours_by_agreement) {
                updateExternalHoursAgreementTable(data.external_hours_by_agreement);
            }
        }

        // Monthly invoiced chart (current year) - respond to filters
        if (Array.isArray(invoicedSeriesForFilters)) {
            updateInvoicedChart(invoicedSeriesForFilters);
        } else if (data.invoiced_series) {
            updateInvoicedChart(data.invoiced_series);
        }

        // Agreement type chart (invoiced) - respond to filters
        if (agreementTotalsForFilters) {
            updateAgreementTypeChart(agreementTotalsForFilters);
        } else if (data.agreement_type_totals) {
            updateAgreementTypeChart(data.agreement_type_totals);
        }

        // Sales Orders monthly chart - respond to filters
        if (Array.isArray(salesOrdersSeriesForFilters)) {
            updateSalesOrdersChart(salesOrdersSeriesForFilters);
        } else if (data.sales_orders_series) {
            updateSalesOrdersChart(data.sales_orders_series);
        }

        // Sales Orders agreement type chart - respond to filters
        if (salesOrdersAgreementTotalsForFilters) {
            updateSalesOrdersAgreementTypeChart(salesOrdersAgreementTotalsForFilters);
        } else if (data.sales_orders_agreement_type_totals) {
            updateSalesOrdersAgreementTypeChart(data.sales_orders_agreement_type_totals);
        }

        // Sales Orders project cards - respond to filters
        if (Array.isArray(salesOrdersProjectTotalsForFilters)) {
            updateSalesOrdersProjectCards(salesOrdersProjectTotalsForFilters);
        } else if (data.sales_orders_project_totals) {
            updateSalesOrdersProjectCards(data.sales_orders_project_totals);
        }
    };

    /**
     * Recalculate subscription statistics from filtered subscriptions
     * @param {Array} subscriptions - Filtered subscriptions
     * @param {date} monthStart - Start of the month
     * @param {date} monthEnd - End of the month
     * @returns {Object} Recalculated subscription statistics
     */
    const recalculateSubscriptionStats = (subscriptions, monthStart, monthEnd) => {
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

                // Check if new/renew (first_contract_date in the month)
                const startDateStr = sub.first_contract_date || sub.start_date;
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
    const recalculateExternalHoursTotals = (subscriptions, salesOrders, originalTotals) => {
        let subscriptionSoldTotal = 0.0;
        let subscriptionUsedTotal = 0.0;
        let salesOrderTotal = 0.0;

        // Sum from filtered subscriptions
        if (Array.isArray(subscriptions)) {
            subscriptions.forEach(sub => {
                try {
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
                    const hours = order.external_hours || 0;
                    if (hours) salesOrderTotal += parseFloat(hours) || 0;
                } catch (error) {
                    console.warn('Error processing sales order:', error, order);
                }
            });
        }

        const totalSold = subscriptionSoldTotal + salesOrderTotal;
        const totalUsed = subscriptionUsedTotal + salesOrderTotal;

        return {
            external_hours_sold: totalSold,
            external_hours_used: totalUsed,
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
    const recalculateExternalHoursByAgreement = (subscriptions, salesOrders) => {
        const soldTotals = { Retainer: 0.0, Framework: 0.0, 'Ad Hoc': 0.0, Unknown: 0.0 };
        const usedTotals = { Retainer: 0.0, Framework: 0.0, 'Ad Hoc': 0.0, Unknown: 0.0 };

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

    // Listen for filter changes (safely) - but don't let it block initial render
    // Use a flag to prevent reapplyFilters from running during initial load
    let filtersReady = false;
    
    document.addEventListener('salesFiltersChanged', (event) => {
        try {
            if (event && event.detail && filtersReady) {
                currentFilterState = event.detail;
                reapplyFilters();
            } else if (event && event.detail) {
                // Just update state, don't reapply yet
                currentFilterState = event.detail;
            }
        } catch (error) {
            console.error('Error handling filter change:', error);
        }
    });

    // Function to render external hours by agreement type table
    const updateExternalHoursAgreementTable = (externalHoursByAgreement) => {
        const tbody = document.getElementById('externalHoursAgreementTableBody');
        if (!tbody || !externalHoursByAgreement) return;

        const sold = externalHoursByAgreement.sold || {};
        const used = externalHoursByAgreement.used || {};

        // Format hours (remove decimals if whole number, otherwise show 1 decimal)
        const formatHours = (value) => {
            if (value === 0) return '0';
            if (Number.isInteger(value)) {
                return value.toLocaleString('en-US');
            }
            return value.toLocaleString('en-US', { maximumFractionDigits: 1 });
        };

        // Agreement types in order
        const agreementTypes = ['Retainer', 'Framework', 'Ad Hoc', 'Unknown'];
        
        let html = '';
        agreementTypes.forEach(type => {
            const soldValue = sold[type] || 0;
            const usedValue = used[type] || 0;
            
            // Only show rows with data
            if (soldValue > 0 || usedValue > 0) {
                html += `
                    <tr class="hover:bg-slate-50">
                        <td class="px-4 py-3 font-medium text-slate-900">${type}</td>
                        <td class="px-4 py-3 text-slate-600 text-right">${formatHours(soldValue)}</td>
                        <td class="px-4 py-3 text-slate-600 text-right">${formatHours(usedValue)}</td>
                    </tr>
                `;
            }
        });

        if (html === '') {
            tbody.innerHTML = '<tr><td colspan="3" class="px-4 py-8 text-center text-slate-500">No external hours data available</td></tr>';
        } else {
            tbody.innerHTML = html;
        }
    };

    // Function to render external hours metrics card
    const updateExternalHoursCard = (externalHoursTotals) => {
        const container = document.getElementById('externalHoursCard');
        if (!container || !externalHoursTotals) return;

        const sold = externalHoursTotals.external_hours_sold || 0;
        const used = externalHoursTotals.external_hours_used || 0;
        const comparisonSold = externalHoursTotals.comparison_sold;
        const comparisonUsed = externalHoursTotals.comparison_used;

        // Format numbers (remove decimals if whole number, otherwise show 1 decimal)
        const formatHours = (value) => {
            if (value === 0) return '0';
            if (Number.isInteger(value)) {
                return value.toLocaleString('en-US');
            }
            return value.toLocaleString('en-US', { maximumFractionDigits: 1 });
        };

        // Format comparison
        const formatComparison = (comparison) => {
            if (!comparison) return '';
            const percent = comparison.change_percentage || 0;
            const trend = comparison.trend || 'up';
            const isPositive = trend === 'up';
            const arrow = isPositive ? '▲' : '▼';
            const colorClass = isPositive ? 'text-emerald-600' : 'text-rose-600';
            return `<span class="${colorClass}">${arrow} ${percent.toFixed(1)}% vs last month</span>`;
        };

        container.innerHTML = `
            <div class="flex flex-col gap-6 sm:flex-row sm:gap-8">
                <!-- Ext Hrs SOLD -->
                <div class="flex-1 text-center">
                    <div class="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">Ext Hrs SOLD</div>
                    <div class="text-4xl font-bold text-slate-900 mb-2">${formatHours(sold)}</div>
                    ${comparisonSold ? `<div class="text-xs">${formatComparison(comparisonSold)}</div>` : '<div class="text-xs text-slate-400">No comparison data</div>'}
                </div>
                
                <!-- Ext Hrs Used -->
                <div class="flex-1 text-center">
                    <div class="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">Ext Hrs Used</div>
                    <div class="text-4xl font-bold text-slate-900 mb-2">${formatHours(used)}</div>
                    ${comparisonUsed ? `<div class="text-xs">${formatComparison(comparisonUsed)}</div>` : '<div class="text-xs text-slate-400">No comparison data</div>'}
                </div>
            </div>
        `;
    };

    // Function to render subscriptions list
    const updateSubscriptionsList = (subscriptions) => {
        const container = document.getElementById('subscriptionsList');
        if (!container) return;
        
        // Apply filters
        const filteredSubscriptions = applyFilters(subscriptions);

        if (!Array.isArray(subscriptions) || subscriptions.length === 0) {
            container.innerHTML = '<div class="text-center text-sm text-slate-500 py-8">No active subscriptions for this month</div>';
            return;
        }
        
        if (filteredSubscriptions.length === 0) {
            container.innerHTML = '<div class="text-center text-sm text-slate-500 py-8">No subscriptions match the selected filters</div>';
            return;
        }

        // Build table HTML
        let html = `
            <div class="overflow-x-auto">
                <table class="w-full text-left text-xs table-fixed" style="table-layout: fixed;">
                    <colgroup>
                        <col style="width: 24%;">
                        <col style="width: 10%;">
                        <col style="width: 12%;">
                        <col style="width: 10%;">
                        <col style="width: 10%;">
                        <col style="width: 12%;">
                        <col style="width: 22%;">
                    </colgroup>
                    <thead class="border-b border-slate-200 bg-slate-50">
                        <tr>
                            <th class="px-2 py-3 font-semibold text-slate-700">Client</th>
                            <th class="px-2 py-3 font-semibold text-slate-700">Order</th>
                            <th class="px-2 py-3 font-semibold text-slate-700">Market</th>
                            <th class="px-2 py-3 font-semibold text-slate-700">Ext. Hrs Sold</th>
                            <th class="px-2 py-3 font-semibold text-slate-700">Ext. Hrs Used</th>
                            <th class="px-2 py-3 font-semibold text-slate-700">Status</th>
                            <th class="px-2 py-3 font-semibold text-slate-700 text-right">Monthly Payment</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white">
            `;

        filteredSubscriptions.forEach((sub, index) => {
                const endDateDisplay = sub.end_date
                    ? new Date(sub.end_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
                    : 'Ongoing';
                const statusBadge = sub.is_ongoing
                ? '<span class="inline-flex items-center rounded-full bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-800">Ongoing</span>'
                : `<span class="inline-flex items-center rounded-full bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-700">Ends ${endDateDisplay}</span>`;
            
            const orderName = sub.order_name || 'N/A';
            const projectName = sub.project_name && sub.project_name !== 'Unassigned Project' ? sub.project_name : 'N/A';
            const market = sub.market || 'Unassigned Market';
            const externalHoursSold = sub.external_sold_hours_display || '0h';
            const externalHoursUsed = sub.external_hours_used_display || '0h';
            const monthlyPayment = sub.monthly_recurring_payment_display || 'AED 0.00';

                html += `
                <tr class="border-b border-slate-100 hover:bg-slate-50">
                    <td class="px-2 py-3 font-medium text-slate-900 truncate" title="${projectName}">${projectName}</td>
                    <td class="px-2 py-3 text-slate-600 truncate" title="${orderName}">${orderName}</td>
                    <td class="px-2 py-3 text-slate-600 truncate" title="${market}">${market}</td>
                    <td class="px-2 py-3 text-slate-600 whitespace-nowrap">${externalHoursSold}</td>
                    <td class="px-2 py-3 text-slate-600 whitespace-nowrap">${externalHoursUsed}</td>
                    <td class="px-2 py-3">${statusBadge}</td>
                    <td class="px-2 py-3 font-medium text-slate-900 text-right whitespace-nowrap">${monthlyPayment}</td>
                </tr>
                `;
            });

            html += `
                    </tbody>
                </table>
                </div>
            `;

        container.innerHTML = html;
    };

    // Helper function to show/hide loading overlay
    const showLoadingOverlay = () => {
        const loadingOverlay = document.querySelector("[data-loading-overlay]");
        if (loadingOverlay) {
            loadingOverlay.classList.remove("hidden");
        }
    };

    const hideLoadingOverlay = () => {
        const loadingOverlay = document.querySelector("[data-loading-overlay]");
        if (loadingOverlay) {
            loadingOverlay.classList.add("hidden");
        }
    };

    // Function to clear sales UI (show loading/empty state)
    const clearSalesUI = () => {
        // Clear invoice count
        if (salesInvoiceCount) {
            salesInvoiceCount.textContent = '---';
            salesInvoiceCount.classList.add('opacity-50');
        }
        // Clear sales order count
        if (salesOrderCount) {
            salesOrderCount.textContent = '---';
        }
        // Clear subscription count (Total Subscriptions card)
        if (salesSubscriptionCount) {
            salesSubscriptionCount.textContent = '---';
        }
        // Subscription trend removed per user request
        // Hide comparison
        if (salesComparison) {
            salesComparison.classList.add('opacity-0');
        }
        // Clear sales order trend
        if (salesOrderTrend) {
            salesOrderTrend.innerHTML = '';
        }
        // Clear invoice list
        if (invoiceListBody) {
            invoiceListBody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-slate-500">Loading...</td></tr>';
        }
        // Clear sales order list
        if (salesOrderListBody) {
            salesOrderListBody.innerHTML = '<tr><td colspan="9" class="px-4 py-8 text-center text-slate-500">Loading...</td></tr>';
        }
        // Clear sales orders grouped table
        const salesOrdersGroupedTableBody = document.getElementById('salesOrdersGroupedTableBody');
        if (salesOrdersGroupedTableBody) {
            salesOrdersGroupedTableBody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-slate-500">Loading...</td></tr>';
        }
        // Clear subscription stats
        const subscriptionStatsCard = document.getElementById('subscriptionStatsCard');
        if (subscriptionStatsCard) {
            subscriptionStatsCard.innerHTML = '<div class="text-center text-slate-500 p-8">Loading...</div>';
        }
        // Clear external hours card
        const externalHoursCard = document.getElementById('externalHoursCard');
        if (externalHoursCard) {
            externalHoursCard.innerHTML = '<div class="text-center text-slate-500 p-8">Loading...</div>';
        }
        // Clear external hours agreement table
        const externalHoursAgreementTableBody = document.getElementById('externalHoursAgreementTableBody');
        if (externalHoursAgreementTableBody) {
            externalHoursAgreementTableBody.innerHTML = '<tr><td colspan="3" class="px-4 py-8 text-center text-slate-500">Loading...</td></tr>';
        }
        // Clear subscriptions list
        const subscriptionsList = document.getElementById('subscriptionsList');
        if (subscriptionsList) {
            const tableBody = subscriptionsList.querySelector('[data-subscription-table-body]');
            if (tableBody) {
                tableBody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-slate-500">Loading...</td></tr>';
            }
        }
        // Destroy charts to ensure they're cleared
        if (invoicedChart) {
            invoicedChart.destroy();
            invoicedChart = null;
        }
        if (salesOrdersChart) {
            salesOrdersChart.destroy();
            salesOrdersChart = null;
        }
        if (salesOrdersAgreementTypeChart) {
            salesOrdersAgreementTypeChart.destroy();
            salesOrdersAgreementTypeChart = null;
        }
        if (agreementTypeChart) {
            agreementTypeChart.destroy();
            agreementTypeChart = null;
        }
    };

    // Function to verify that all UI elements are populated
    const verifyUIComplete = (data) => {
        // Check if stats are populated
        if (salesInvoiceCount) {
            const text = salesInvoiceCount.textContent.trim();
            if (text === '---' || text === '' || text.includes('...')) {
                return false;
            }
        }
        if (salesOrderCount) {
            const text = salesOrderCount.textContent.trim();
            if (text === '---' || text === '' || text.includes('...')) {
                return false;
            }
        }
        // Check subscription count (Total Subscriptions card)
        // If subscription stats exist with BOTH counts defined, the count must be populated (can be '0' if legitimately zero)
        // If subscription stats don't exist or are incomplete, it should show '---'
        if (salesSubscriptionCount) {
            const text = salesSubscriptionCount.textContent.trim();
            if (data.subscription_stats && typeof data.subscription_stats === 'object') {
                // Check if subscription stats have complete data (both counts defined)
                const hasCompleteStats = data.subscription_stats.active_count !== undefined && 
                                        data.subscription_stats.churned_count !== undefined;
                if (hasCompleteStats) {
                    // Subscription stats exist with complete data, so count should be populated (not '---' or empty)
                    // Allow '0' as valid (legitimately zero subscriptions)
                    if (text === '---' || text === '' || text.includes('...')) {
                        return false;
                    }
                } else {
                    // Subscription stats exist but incomplete, should show '---'
                    if (text !== '---' && text !== '') {
                        return false;
                    }
                }
            } else {
                // No subscription stats, should show '---'
                if (text !== '---' && text !== '') {
                    // If it shows a number but no stats, might be stale data
                    return false;
                }
            }
        }
        // Check if charts are rendered (only if data exists)
        if (data.invoiced_series && data.invoiced_series.length > 0 && !invoicedChart) {
            return false;
        }
        if (data.sales_orders_series && data.sales_orders_series.length > 0 && !salesOrdersChart) {
            return false;
        }
        // Check if lists are populated (not showing loading and have actual content)
        if (invoiceListBody) {
            const loadingRow = invoiceListBody.querySelector('td[colspan="7"]');
            if (loadingRow && loadingRow.textContent.includes('Loading')) {
                return false;
            }
            // Also check if list has actual rows (not just empty)
            const rows = invoiceListBody.querySelectorAll('tr');
            if (data.sales_stats && data.sales_stats.invoices && data.sales_stats.invoices.length > 0) {
                // If invoices exist in data, there should be rows (excluding header if any)
                const dataRows = Array.from(rows).filter(row => !row.querySelector('th'));
                if (dataRows.length === 0) {
                    return false;
                }
            }
        }
        if (salesOrderListBody) {
            const loadingRow = salesOrderListBody.querySelector('td[colspan="9"]');
            if (loadingRow && loadingRow.textContent.includes('Loading')) {
                return false;
            }
            // Also check if list has actual rows
            const rows = salesOrderListBody.querySelectorAll('tr');
            if (data.sales_stats && data.sales_stats.sales_orders && data.sales_stats.sales_orders.length > 0) {
                const dataRows = Array.from(rows).filter(row => !row.querySelector('th'));
                if (dataRows.length === 0) {
                    return false;
                }
            }
        }
        // Check sales orders grouped table
        const salesOrdersGroupedTableBody = document.getElementById('salesOrdersGroupedTableBody');
        if (salesOrdersGroupedTableBody && data.sales_stats && data.sales_stats.sales_orders) {
            const loadingRow = salesOrdersGroupedTableBody.querySelector('td[colspan="7"]');
            if (loadingRow && loadingRow.textContent.includes('Loading')) {
                return false;
            }
            // Check if table has actual rows
            const rows = salesOrdersGroupedTableBody.querySelectorAll('tr');
            const dataRows = Array.from(rows).filter(row => !row.querySelector('th'));
            if (dataRows.length === 0 && Array.isArray(data.sales_stats.sales_orders) && data.sales_stats.sales_orders.length > 0) {
                return false;
            }
        }
        // Check subscription stats card - verify it has actual content, not loading
        const subscriptionStatsCard = document.getElementById('subscriptionStatsCard');
        if (subscriptionStatsCard) {
            const loadingDiv = subscriptionStatsCard.querySelector('.text-center.text-slate-500');
            if (loadingDiv && loadingDiv.textContent.includes('Loading')) {
                return false;
            }
            // If subscription stats exist, verify the card has actual content
            if (data.subscription_stats && typeof data.subscription_stats === 'object') {
                const hasCompleteStats = data.subscription_stats.active_count !== undefined && 
                                        data.subscription_stats.churned_count !== undefined;
                if (hasCompleteStats) {
                    // Check if card has the expected stat elements
                    const activeCount = subscriptionStatsCard.querySelector('[data-active-count]') || 
                                      subscriptionStatsCard.textContent.match(/Active.*In Progress.*\d+/);
                    const churnedCount = subscriptionStatsCard.querySelector('[data-churned-count]') || 
                                       subscriptionStatsCard.textContent.match(/Churned.*\d+/);
                    // If we can't find stat elements, card might not be fully rendered
                    if (!activeCount && !churnedCount) {
                        // Fallback: check if card has meaningful content (not just loading)
                        const cardText = subscriptionStatsCard.textContent.trim();
                        if (cardText === '' || cardText.includes('Loading') || cardText.length < 20) {
                            return false;
                        }
                    }
                }
            }
        }
        // Check subscriptions list - verify it has actual rows if subscriptions exist
        const subscriptionsList = document.getElementById('subscriptionsList');
        if (subscriptionsList && data.subscriptions) {
            const tableBody = subscriptionsList.querySelector('[data-subscription-table-body]');
            if (tableBody) {
                const loadingRow = tableBody.querySelector('td[colspan="7"]');
                if (loadingRow && loadingRow.textContent.includes('Loading')) {
                    return false;
                }
                // If subscriptions exist in data, verify rows are rendered
                if (Array.isArray(data.subscriptions) && data.subscriptions.length > 0) {
                    const rows = tableBody.querySelectorAll('tr');
                    const dataRows = Array.from(rows).filter(row => !row.querySelector('th'));
                    if (dataRows.length === 0) {
                        return false;
                    }
                }
            }
        }
        // Check external hours card
        const externalHoursCard = document.getElementById('externalHoursCard');
        if (externalHoursCard && data.external_hours_totals) {
            const loadingDiv = externalHoursCard.querySelector('.text-center.text-slate-500');
            if (loadingDiv && loadingDiv.textContent.includes('Loading')) {
                return false;
            }
            // Check if card has actual content
            const cardText = externalHoursCard.textContent.trim();
            if (cardText === '' || cardText.includes('Loading') || cardText.length < 10) {
                return false;
            }
        }
        // Check external hours agreement table
        const externalHoursAgreementTableBody = document.getElementById('externalHoursAgreementTableBody');
        if (externalHoursAgreementTableBody && data.external_hours_by_agreement) {
            const loadingRow = externalHoursAgreementTableBody.querySelector('td[colspan="3"]');
            if (loadingRow && loadingRow.textContent.includes('Loading')) {
                return false;
            }
            // Check if table has actual rows
            const rows = externalHoursAgreementTableBody.querySelectorAll('tr');
            const dataRows = Array.from(rows).filter(row => !row.querySelector('th'));
            if (dataRows.length === 0) {
                return false;
            }
        }
        // Verify charts are actually rendered and visible (not just created)
        if (data.invoiced_series && data.invoiced_series.length > 0) {
            if (!invoicedChart) {
                return false;
            }
            // Check if chart canvas is visible
            const chartCanvas = document.getElementById('invoicedChart');
            if (chartCanvas && chartCanvas.offsetHeight === 0) {
                return false;
            }
        }
        if (data.sales_orders_series && data.sales_orders_series.length > 0) {
            if (!salesOrdersChart) {
                return false;
            }
            const chartCanvas = document.getElementById('salesOrdersChart');
            if (chartCanvas && chartCanvas.offsetHeight === 0) {
                return false;
            }
        }
        return true;
    };

    /**
     * If a fetch for the same month is already in-flight, optionally show the loading
     * overlay and wait for it to finish so we don't flash stale data.
     * @param {string} month - Month we are waiting on
     * @param {boolean} showOverlay - Whether to show the loading overlay while waiting
     */
    const waitForExistingLoad = async (month, showOverlay = false) => {
        const shouldShow = Boolean(showOverlay);
        if (shouldShow) {
            showLoadingOverlay();
            clearSalesUI(); // remove any stale content while we wait
        }

        try {
            await salesDataLoadingPromise.promise;
        } catch (error) {
            console.error(`Error waiting for in-flight sales data for ${month}:`, error);
        } finally {
            if (shouldShow) {
                hideLoadingOverlay();
            }
        }
    };

    // Function to fetch and update sales data
    const fetchSalesData = async (month, showLoading = false, forceRefresh = false) => {
        // If force refresh, clear cache and UI first
        if (forceRefresh) {
            delete salesDataCache[month];
            clearSalesUI();
        }

        // Check cache first (only if not forcing refresh)
        if (!forceRefresh && salesDataCache[month]) {
            const cachedSalesStats = getSalesStatsForCurrentFilters(salesDataCache[month].sales_stats);
            const effectiveSalesStats = cachedSalesStats || salesDataCache[month].sales_stats;
            const agreementTotalsForFilters = getAgreementTotalsForCurrentFilters(
                salesDataCache[month].agreement_type_totals,
                effectiveSalesStats?.invoices || salesDataCache[month].sales_stats?.invoices
            );
            const salesOrdersAgreementTotalsForFilters = getSalesOrdersAgreementTotalsForCurrentFilters(
                salesDataCache[month].sales_orders_agreement_type_totals,
                effectiveSalesStats?.sales_orders || salesDataCache[month].sales_stats?.sales_orders
            );
            const salesOrdersProjectTotalsForFilters = getSalesOrdersProjectTotalsForCurrentFilters(
                salesDataCache[month].sales_orders_project_totals,
                effectiveSalesStats?.sales_orders || salesDataCache[month].sales_stats?.sales_orders
            );
            const invoicedSeriesForFilters = getInvoicedSeriesForCurrentFilters(
                salesDataCache[month].invoiced_series,
                salesDataCache[month].invoiced_series_breakdown
            );
            const salesOrdersSeriesForFilters = getSalesOrdersSeriesForCurrentFilters(
                salesDataCache[month].sales_orders_series,
                salesDataCache[month].sales_orders_series_breakdown
            );
            // Compute filter-aware comparisons if filters are active
                let invoiceComparisonOverride = null;
                let salesOrderComparisonOverride = null;
                let subscriptionComparisonOverride = null;
            if (currentFilterState && currentFilterState.hasActiveFilters) {
                invoiceComparisonOverride = computeFilterComparisonFromBreakdown(
                    salesDataCache[month].invoiced_series_breakdown,
                    month,
                    currentFilterState
                );
                salesOrderComparisonOverride = computeFilterComparisonFromBreakdown(
                    salesDataCache[month].sales_orders_series_breakdown,
                    month,
                    currentFilterState
                );

                // Subscription comparison: compare filtered current subscriptions to filtered previous month if cached
                const currentSubsFiltered = applyFilters(salesDataCache[month].subscriptions || []);
                const prevKey = getPrevMonthKey(month);
                if (prevKey && salesDataCache[prevKey] && Array.isArray(salesDataCache[prevKey].subscriptions)) {
                    const prevSubsFiltered = applyFilters(salesDataCache[prevKey].subscriptions);
                    subscriptionComparisonOverride = calculateComparison(
                        currentSubsFiltered.length,
                        prevSubsFiltered.length
                    );
                }
            }

            updateSalesUI(effectiveSalesStats, salesDataCache[month].subscription_stats, {
                invoiceComparisonOverride,
                salesOrderComparisonOverride,
                subscriptionComparisonOverride,
            });
            if (effectiveSalesStats && effectiveSalesStats.invoices) {
                renderInvoiceList(effectiveSalesStats.invoices);
            }
            if (Array.isArray(invoicedSeriesForFilters)) {
                updateInvoicedChart(invoicedSeriesForFilters);
            } else if (salesDataCache[month].invoiced_series) {
                updateInvoicedChart(salesDataCache[month].invoiced_series);
            }
            if (Array.isArray(salesOrdersSeriesForFilters)) {
                updateSalesOrdersChart(salesOrdersSeriesForFilters);
            } else if (salesDataCache[month].sales_orders_series) {
                updateSalesOrdersChart(salesDataCache[month].sales_orders_series);
            }
            if (salesOrdersAgreementTotalsForFilters) {
                updateSalesOrdersAgreementTypeChart(salesOrdersAgreementTotalsForFilters);
            } else if (salesDataCache[month].sales_orders_agreement_type_totals) {
                updateSalesOrdersAgreementTypeChart(salesDataCache[month].sales_orders_agreement_type_totals);
            }
            if (Array.isArray(salesOrdersProjectTotalsForFilters)) {
                updateSalesOrdersProjectCards(salesOrdersProjectTotalsForFilters);
            } else if (salesDataCache[month].sales_orders_project_totals) {
                updateSalesOrdersProjectCards(salesDataCache[month].sales_orders_project_totals);
            }
            if (agreementTotalsForFilters) {
                updateAgreementTypeChart(agreementTotalsForFilters);
            } else if (salesDataCache[month].agreement_type_totals) {
                updateAgreementTypeChart(salesDataCache[month].agreement_type_totals);
            }
            if (salesDataCache[month].subscriptions) {
                updateSubscriptionsList(salesDataCache[month].subscriptions);
            }
            if (salesDataCache[month].subscription_stats) {
                updateSubscriptionStatsCard(salesDataCache[month].subscription_stats);
            }
            if (salesDataCache[month].external_hours_totals) {
                updateExternalHoursCard(salesDataCache[month].external_hours_totals);
            }
            if (salesDataCache[month].external_hours_by_agreement) {
                updateExternalHoursAgreementTable(salesDataCache[month].external_hours_by_agreement);
            }
            // Ensure charts are resized after rendering cached data
            setTimeout(() => {
                if (invoicedChart) invoicedChart.resize();
                if (salesOrdersChart) salesOrdersChart.resize();
                if (salesOrdersAgreementTypeChart) salesOrdersAgreementTypeChart.resize();
                if (agreementTypeChart) agreementTypeChart.resize();
            }, 100);
            return;
        }

        // If already loading for this month, wait for that promise instead of starting a new request
        if (salesDataLoadingPromise && salesDataLoadingPromise.month === month) {
            await waitForExistingLoad(month, showLoading);
            return;
        }

        // If already loading for this month and not forcing refresh, wait for existing promise
        if (isLoading && !forceRefresh) {
            if (salesDataLoadingPromise && salesDataLoadingPromise.month === month) {
                await waitForExistingLoad(month, showLoading);
            }
            return;
        }

        isLoading = true;
        filtersReady = false; // Reset filters ready flag when starting new load

        // Show loading overlay if requested (when switching tabs or months)
        if (showLoading) {
            showLoadingOverlay();
        }

        // Clear UI before fetching if showing loading (to avoid showing old data)
        if (showLoading && !forceRefresh) {
            clearSalesUI();
        }

        // Create a promise for this fetch so other calls can wait for it
        const fetchPromise = (async () => {
            try {
                // Show loading state if not cached
                if (salesInvoiceCount && !showLoading) {
                    salesInvoiceCount.classList.add('opacity-50');
                    // Only show loading text if we don't have data yet (avoid flickering on refresh)
                    if (salesInvoiceCount.textContent.trim() === '0' || salesInvoiceCount.textContent.trim() === '---') {
                        salesInvoiceCount.innerHTML = '<span class="text-3xl text-slate-300">...</span>';
                    }
                }

                const params = new URLSearchParams({ month });
                const response = await fetch(`/api/sales?${params.toString()}`);

                if (!response.ok) {
                    throw new Error('Failed to fetch sales data');
                }

                const data = await response.json();

                // IMPORTANT: Check if this month is still the current month before rendering
                // This prevents stale data from being displayed when user switches months quickly
                const currentActiveMonth = monthSelect ? monthSelect.value : currentMonth;
                if (month !== currentActiveMonth) {
                    console.log(`Skipping render for ${month} - current month is now ${currentActiveMonth}`);
                    // Still cache it in case user switches back, but don't render
                    salesDataCache[month] = data;
                    return; // Exit early, don't render stale data
                }

                // Cache the result
                salesDataCache[month] = data;

                // Update filter state before using it (safely)
                try {
                    if (window.SalesFilters && typeof window.SalesFilters.getFilterState === 'function') {
                        currentFilterState = window.SalesFilters.getFilterState();
                    } else {
                        currentFilterState = { hasActiveFilters: false };
                    }
                } catch (error) {
                    console.warn('Error getting filter state, continuing without filters:', error);
                    currentFilterState = { hasActiveFilters: false };
                }

                // Update sales UI - use filtered subscription stats if filters are active
                let subscriptionStatsToUse = data.subscription_stats;
                const salesStatsForFilters = getSalesStatsForCurrentFilters(data.sales_stats);
                const effectiveSalesStats = salesStatsForFilters || data.sales_stats;
                const agreementTotalsForFilters = getAgreementTotalsForCurrentFilters(
                    data.agreement_type_totals,
                    salesStatsForFilters?.invoices || data.sales_stats?.invoices
                );
                const salesOrdersAgreementTotalsForFilters = getSalesOrdersAgreementTotalsForCurrentFilters(
                    data.sales_orders_agreement_type_totals,
                    salesStatsForFilters?.sales_orders || data.sales_stats?.sales_orders
                );
                const salesOrdersProjectTotalsForFilters = getSalesOrdersProjectTotalsForCurrentFilters(
                    data.sales_orders_project_totals,
                    salesStatsForFilters?.sales_orders || data.sales_stats?.sales_orders
                );
                const invoicedSeriesForFilters = getInvoicedSeriesForCurrentFilters(
                    data.invoiced_series,
                    data.invoiced_series_breakdown
                );
                let invoiceComparisonOverride = null;
                let salesOrderComparisonOverride = null;
                let subscriptionComparisonOverride = null;
                
                if (currentFilterState && currentFilterState.hasActiveFilters) {
                    invoiceComparisonOverride = computeFilterComparisonFromBreakdown(
                        data.invoiced_series_breakdown,
                        month,
                        currentFilterState
                    );
                    salesOrderComparisonOverride = computeFilterComparisonFromBreakdown(
                        data.sales_orders_series_breakdown,
                        month,
                        currentFilterState
                    );

                    // Subscription comparison: calculate using filtered subscriptions and recalculated stats
                    if (data.subscriptions) {
                        try {
                            const filteredSubscriptions = applyFilters(data.subscriptions);
                            // Parse month from data.selected_month or month parameter
                            let monthStart, monthEnd;
                            if (data.selected_month) {
                                const [year, monthNum] = data.selected_month.split('-').map(Number);
                                monthStart = new Date(year, monthNum - 1, 1);
                                const lastDay = new Date(year, monthNum, 0).getDate();
                                monthEnd = new Date(year, monthNum - 1, lastDay);
                            } else {
                                // Parse from month parameter (format: "YYYY-MM")
                                const monthStr = month; // Use function parameter
                                const [year, monthNum] = monthStr.split('-').map(Number);
                                monthStart = new Date(year, monthNum - 1, 1);
                                const lastDay = new Date(year, monthNum, 0).getDate();
                                monthEnd = new Date(year, monthNum - 1, lastDay);
                            }
                            subscriptionStatsToUse = recalculateSubscriptionStats(filteredSubscriptions, monthStart, monthEnd);
                            console.log('[DEBUG] loadSalesData: Recalculated subscription stats:', {
                                total_subscriptions: subscriptionStatsToUse.total_subscriptions,
                                active_count: subscriptionStatsToUse.active_count,
                                churned_count: subscriptionStatsToUse.churned_count
                            });
                            
                            // Calculate subscription comparison using total_subscriptions from recalculated stats
                            // This ensures we compare the same metric (total_subscriptions) that's displayed in the UI
                            // Use data.selected_month if available, otherwise use month parameter
                            const monthKeyForComparison = data.selected_month || month;
                            const prevKey = getPrevMonthKey(monthKeyForComparison);
                            console.log('[DEBUG] loadSalesData: Subscription comparison calculation:', {
                                monthKeyForComparison,
                                prevKey,
                                hasPrevMonthCache: !!(prevKey && salesDataCache[prevKey]),
                                hasPrevSubscriptions: !!(prevKey && salesDataCache[prevKey] && Array.isArray(salesDataCache[prevKey].subscriptions))
                            });
                            if (prevKey && salesDataCache[prevKey] && Array.isArray(salesDataCache[prevKey].subscriptions)) {
                                const prevSubsFiltered = applyFilters(salesDataCache[prevKey].subscriptions);
                                console.log('[DEBUG] loadSalesData: Previous month filtered subscriptions count:', prevSubsFiltered.length);
                                // Calculate previous month bounds
                                const prevMonthParts = prevKey.split('-').map(Number);
                                const prevMonthStart = new Date(prevMonthParts[0], prevMonthParts[1] - 1, 1);
                                const prevLastDay = new Date(prevMonthParts[0], prevMonthParts[1], 0).getDate();
                                const prevMonthEnd = new Date(prevMonthParts[0], prevMonthParts[1] - 1, prevLastDay);
                                const prevStatsRecalculated = recalculateSubscriptionStats(prevSubsFiltered, prevMonthStart, prevMonthEnd);
                                console.log('[DEBUG] loadSalesData: Previous month recalculated stats:', {
                                    total_subscriptions: prevStatsRecalculated.total_subscriptions,
                                    active_count: prevStatsRecalculated.active_count,
                                    churned_count: prevStatsRecalculated.churned_count
                                });
                                
                                // Compare total_subscriptions from both recalculated stats
                                subscriptionComparisonOverride = calculateComparison(
                                    subscriptionStatsToUse.total_subscriptions,
                                    prevStatsRecalculated.total_subscriptions
                                );
                                console.log('[DEBUG] loadSalesData: Calculated subscriptionComparisonOverride:', subscriptionComparisonOverride);
                            } else {
                                console.log('[DEBUG] loadSalesData: Cannot calculate subscriptionComparisonOverride - previous month data not available');
                            }
                        } catch (error) {
                            console.error('Error recalculating subscription stats, using original:', error);
                            subscriptionStatsToUse = data.subscription_stats;
                        }
                    }
                }
                
                // Update sales UI - wrap in try-catch to prevent blocking
                console.log('[DEBUG] loadSalesData: Calling updateSalesUI with comparison overrides:', {
                    invoiceComparisonOverride: invoiceComparisonOverride ? 'SET' : 'NULL',
                    salesOrderComparisonOverride: salesOrderComparisonOverride ? 'SET' : 'NULL',
                    subscriptionComparisonOverride: subscriptionComparisonOverride ? 'SET' : 'NULL',
                    subscriptionComparisonOverrideValue: subscriptionComparisonOverride
                });
                try {
                    updateSalesUI(effectiveSalesStats, subscriptionStatsToUse, {
                        invoiceComparisonOverride,
                        salesOrderComparisonOverride,
                        subscriptionComparisonOverride,
                    });
                } catch (error) {
                    console.error('Error updating sales UI:', error);
                    // Try with original stats as fallback
                    try {
                        updateSalesUI(effectiveSalesStats, data.subscription_stats, {
                            invoiceComparisonOverride,
                            salesOrderComparisonOverride,
                            subscriptionComparisonOverride,
                        });
                    } catch (fallbackError) {
                        console.error('Error updating sales UI with fallback:', fallbackError);
                    }
                }

                // Render all UI elements and wait for each to complete
                // Use Promise.all to ensure all rendering completes before verification
                const renderingPromises = [];

                // Render invoice list (synchronous, but wait for DOM update)
                try {
                    if (data.sales_stats && data.sales_stats.invoices) {
                        renderInvoiceList(data.sales_stats.invoices);
                        renderingPromises.push(new Promise(resolve => {
                            requestAnimationFrame(() => {
                                requestAnimationFrame(resolve);
                            });
                        }));
                    }
                } catch (error) {
                    console.error('Error rendering invoice list:', error);
                }

                // Render sales order list
                try {
                    if (data.sales_stats && data.sales_stats.sales_orders) {
                        renderSalesOrderList(data.sales_stats.sales_orders);
                        renderSalesOrdersGroupedByProject(data.sales_stats.sales_orders);
                        renderingPromises.push(new Promise(resolve => {
                            requestAnimationFrame(() => {
                                requestAnimationFrame(resolve);
                            });
                        }));
                    }
                } catch (error) {
                    console.error('Error rendering sales order list:', error);
                }

                // Render subscriptions
                try {
                    if (data.subscriptions) {
                        updateSubscriptionsList(data.subscriptions);
                        renderingPromises.push(new Promise(resolve => {
                            requestAnimationFrame(() => {
                                requestAnimationFrame(resolve);
                            });
                        }));
                    }
                } catch (error) {
                    console.error('Error rendering subscriptions:', error);
                }
                
                // Render subscription statistics - use already calculated subscriptionStatsToUse
                try {
                    if (subscriptionStatsToUse) {
                        updateSubscriptionStatsCard(subscriptionStatsToUse);
                    } else if (data.subscription_stats) {
                        // Fallback to original stats
                        updateSubscriptionStatsCard(data.subscription_stats);
                    }
                    renderingPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                } catch (error) {
                    console.error('Error rendering subscription stats:', error);
                    // Fallback to original stats if rendering fails
                    if (data.subscription_stats) {
                        updateSubscriptionStatsCard(data.subscription_stats);
                    }
                }
                
                // Render external hours - apply filters if active
                if (data.external_hours_totals) {
                    try {
                        if (currentFilterState && currentFilterState.hasActiveFilters && data.subscriptions && data.sales_stats && data.sales_stats.sales_orders) {
                            // Recalculate from filtered data
                            const filteredSubscriptions = applyFilters(data.subscriptions);
                            const filteredSalesOrders = applyFilters(data.sales_stats.sales_orders);
                            const recalculatedTotals = recalculateExternalHoursTotals(
                                filteredSubscriptions,
                                filteredSalesOrders,
                                data.external_hours_totals
                            );
                            updateExternalHoursCard(recalculatedTotals);
                            
                            if (data.external_hours_by_agreement) {
                                const recalculatedByAgreement = recalculateExternalHoursByAgreement(
                                    filteredSubscriptions,
                                    filteredSalesOrders
                                );
                                updateExternalHoursAgreementTable(recalculatedByAgreement);
                            }
                        } else {
                            // Use original unfiltered data
                            updateExternalHoursCard(data.external_hours_totals);
                            if (data.external_hours_by_agreement) {
                                updateExternalHoursAgreementTable(data.external_hours_by_agreement);
                            }
                        }
                    } catch (error) {
                        console.error('Error rendering external hours:', error);
                        // Fallback to original data if recalculation fails
                        updateExternalHoursCard(data.external_hours_totals);
                        if (data.external_hours_by_agreement) {
                            updateExternalHoursAgreementTable(data.external_hours_by_agreement);
                        }
                    }
                    renderingPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }

                // Before rendering charts, verify we're still rendering the correct month
                const currentActiveMonthBeforeCharts = monthSelect ? monthSelect.value : currentMonth;
                if (month !== currentActiveMonthBeforeCharts) {
                    console.log(`Skipping chart render for ${month} - current month is now ${currentActiveMonthBeforeCharts}`);
                    return; // Exit early, don't render stale charts
                }

                // Wait for all DOM updates to complete
                await Promise.all(renderingPromises);

                // Now render charts (which may be async)
                const chartPromises = [];

                // Render invoiced chart
                const invoicedSeriesToRender = invoicedSeriesForFilters || data.invoiced_series;
                if (invoicedSeriesToRender) {
                    updateInvoicedChart(invoicedSeriesToRender);
                    chartPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            if (invoicedChart) {
                                invoicedChart.resize();
                            }
                            requestAnimationFrame(() => {
                                setTimeout(resolve, 100); // Give Chart.js time to render
                            });
                        });
                    }));
                }

                // Render Sales Orders chart
                const salesOrdersSeriesToRender = typeof salesOrdersSeriesForFilters !== 'undefined'
                    ? salesOrdersSeriesForFilters
                    : data.sales_orders_series;
                if (salesOrdersSeriesToRender) {
                    updateSalesOrdersChart(salesOrdersSeriesToRender);
                    chartPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            if (salesOrdersChart) {
                                salesOrdersChart.resize();
                            }
                            requestAnimationFrame(() => {
                                setTimeout(resolve, 100);
                            });
                        });
                    }));
                }

                // Render Sales Orders agreement type chart
                const salesOrdersAgreementTotalsToRender = salesOrdersAgreementTotalsForFilters || data.sales_orders_agreement_type_totals;
                if (salesOrdersAgreementTotalsToRender) {
                    updateSalesOrdersAgreementTypeChart(salesOrdersAgreementTotalsToRender);
                    chartPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            if (salesOrdersAgreementTypeChart) {
                                salesOrdersAgreementTypeChart.resize();
                            }
                            requestAnimationFrame(() => {
                                setTimeout(resolve, 100);
                            });
                        });
                    }));
                }

                // Render Sales Orders project cards
                const salesOrdersProjectTotalsToRender = Array.isArray(salesOrdersProjectTotalsForFilters)
                    ? salesOrdersProjectTotalsForFilters
                    : data.sales_orders_project_totals;
                if (salesOrdersProjectTotalsToRender) {
                    updateSalesOrdersProjectCards(salesOrdersProjectTotalsToRender);
                    chartPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }

                // Render invoice agreement type chart
                const agreementTotalsToRender = agreementTotalsForFilters || data.agreement_type_totals;
                if (agreementTotalsToRender) {
                    updateAgreementTypeChart(agreementTotalsToRender);
                    chartPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            if (agreementTypeChart) {
                                agreementTypeChart.resize();
                            }
                            requestAnimationFrame(() => {
                                setTimeout(resolve, 100);
                            });
                        });
                    }));
                }

                // Wait for all charts to render
                await Promise.all(chartPromises);

                // Mark filters as ready after initial load completes
                filtersReady = true;

                // Force a synchronous layout recalculation
                void document.body.offsetHeight;

                // Final check before verification - ensure we're still rendering the correct month
                const currentActiveMonthFinal = monthSelect ? monthSelect.value : currentMonth;
                if (month !== currentActiveMonthFinal) {
                    console.log(`Skipping final verification for ${month} - current month is now ${currentActiveMonthFinal}`);
                    return; // Exit early
                }

                // Final verification - wait until UI is actually populated and stable
                await new Promise((resolve) => {
                    let attempts = 0;
                    const maxAttempts = 100; // Maximum 10 seconds (100 * 100ms)
                    let consecutivePasses = 0;
                    const requiredConsecutivePasses = 5; // Require 5 consecutive passes
                    
                    const checkAndResolve = () => {
                        attempts++;
                        
                        // Resize charts on each check
                        if (invoicedChart) invoicedChart.resize();
                        if (salesOrdersChart) salesOrdersChart.resize();
                        if (salesOrdersAgreementTypeChart) salesOrdersAgreementTypeChart.resize();
                        if (agreementTypeChart) agreementTypeChart.resize();
                        
                        // Verify UI is complete
                        const isComplete = verifyUIComplete(data);
                        
                        if (isComplete) {
                            consecutivePasses++;
                            if (consecutivePasses >= requiredConsecutivePasses) {
                                // UI is complete and stable, wait for final paint
                                requestAnimationFrame(() => {
                                    requestAnimationFrame(() => {
                                        setTimeout(() => {
                                            resolve();
                                        }, 300);
                                    });
                                });
                            } else {
                                setTimeout(checkAndResolve, 100);
                            }
                        } else {
                            consecutivePasses = 0;
                            if (attempts >= maxAttempts) {
                                console.warn('UI verification timeout');
                                requestAnimationFrame(() => {
                                    requestAnimationFrame(() => {
                                        resolve();
                                    });
                                });
                            } else {
                                setTimeout(checkAndResolve, 100);
                            }
                        }
                    };
                    
                    // Start checking after charts have had time to render
                    requestAnimationFrame(() => {
                        setTimeout(() => {
                            checkAndResolve();
                        }, 300);
                    });
                });

            } catch (error) {
                console.error('Error fetching sales data:', error);
                // Show error state in UI
                if (salesInvoiceCount) {
                    salesInvoiceCount.textContent = '---';
                }
                if (salesComparison) {
                    salesComparison.classList.add('opacity-0');
                }
                // Don't re-throw - let the dashboard render what it can
                // The error is already logged, and we don't want to block other parts
            } finally {
                isLoading = false;
                salesDataLoadingPromise = null; // Clear the loading promise
                if (salesInvoiceCount) salesInvoiceCount.classList.remove('opacity-50');
                // Hide loading overlay if it was shown - only after all rendering is complete
                if (showLoading) {
                    hideLoadingOverlay();
                }
            }
        })();

        // Store the promise so other calls can wait for it
        salesDataLoadingPromise = { month, promise: fetchPromise };

        // Execute the fetch
        await fetchPromise;
    };

    // === Collapsible Section Functionality ===
    const initializeCollapsibleSection = (sectionName) => {
        const section = document.querySelector(`[data-collapsible-section="${sectionName}"]`);
        if (!section) return;

        const toggleButton = section.querySelector(`[data-collapsible-toggle="${sectionName}"]`);
        const content = section.querySelector('[data-collapsible-content]');
        const icon = section.querySelector(`[data-collapsible-icon="${sectionName}"]`);

        if (!toggleButton || !content) return;

        toggleButton.addEventListener('click', () => {
            const isCollapsed = section.dataset.sectionCollapsed === 'true';
            const newState = !isCollapsed;

            // Update state
            section.dataset.sectionCollapsed = newState.toString();
            toggleButton.setAttribute('aria-expanded', (!newState).toString());

            // Toggle content visibility
            if (newState) {
                content.classList.add('hidden');
            } else {
                content.classList.remove('hidden');
            }

            // Change icon text (matching Creative Dashboard pattern)
            if (icon) {
                icon.textContent = newState ? 'expand_more' : 'expand_less';
            }

            // Resize charts if they exist
            if (invoicedChart) {
                setTimeout(() => invoicedChart.resize(), 0);
            }
            if (salesOrdersChart) {
                setTimeout(() => salesOrdersChart.resize(), 0);
            }
            if (salesOrdersAgreementTypeChart) {
                setTimeout(() => salesOrdersAgreementTypeChart.resize(), 0);
            }
            if (agreementTypeChart) {
                setTimeout(() => agreementTypeChart.resize(), 0);
            }
        });
    };

    // === Refresh Invoiced Data Functionality ===
    const refreshInvoicedData = async () => {
        const refreshButton = document.querySelector('[data-refresh-invoiced]');
        if (!refreshButton) return;

        const refreshIcon = refreshButton.querySelector('.material-symbols-rounded');

        // Disable button and show loading state
        refreshButton.disabled = true;
        if (refreshIcon) {
            refreshIcon.classList.add('animate-spin');
        }

        try {
            const response = await fetch('/api/sales/refresh-invoiced', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Failed to refresh data');
            }

            const data = await response.json();

            if (data.invoiced_series) {
                const filteredSeries = getInvoicedSeriesForCurrentFilters(
                    data.invoiced_series,
                    data.invoiced_series_breakdown
                );
                const seriesToRender = Array.isArray(filteredSeries) ? filteredSeries : data.invoiced_series;

                // Update chart with refreshed data (respecting current filters if any)
                updateInvoicedChart(seriesToRender);

                // Update cache for the active month so subsequent renders use fresh data
                if (currentMonth) {
                    if (!salesDataCache[currentMonth]) {
                        salesDataCache[currentMonth] = {};
                    }
                    salesDataCache[currentMonth].invoiced_series = data.invoiced_series;
                    salesDataCache[currentMonth].invoiced_series_breakdown = data.invoiced_series_breakdown;
                }

                // Show success feedback
                console.log('Invoiced data refreshed successfully:', data.message);
            }
        } catch (error) {
            console.error('Failed to refresh invoiced data:', error);
            alert(`Error refreshing data: ${error.message}`);
        } finally {
            // Re-enable button and stop spinning
            refreshButton.disabled = false;
            if (refreshIcon) {
                refreshIcon.classList.remove('animate-spin');
            }
        }
    };

    // === Refresh Sales Orders Data Functionality ===
    const refreshSalesOrdersData = async () => {
        const refreshButton = document.querySelector('[data-refresh-sales-orders]');
        if (!refreshButton) return;

        const refreshIcon = refreshButton.querySelector('.material-symbols-rounded');

        // Disable button and show loading state
        refreshButton.disabled = true;
        if (refreshIcon) {
            refreshIcon.classList.add('animate-spin');
        }

        try {
            const response = await fetch('/api/sales/refresh-sales-orders', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Failed to refresh data');
            }

            const data = await response.json();

            if (data.sales_orders_series) {
                const filteredSeries = getSalesOrdersSeriesForCurrentFilters(
                    data.sales_orders_series,
                    data.sales_orders_series_breakdown
                );
                const seriesToRender = Array.isArray(filteredSeries) ? filteredSeries : data.sales_orders_series;

                // Update chart with refreshed data
                updateSalesOrdersChart(seriesToRender);

                // Update cache for active month so subsequent renders use fresh data
                if (currentMonth) {
                    if (!salesDataCache[currentMonth]) {
                        salesDataCache[currentMonth] = {};
                    }
                    salesDataCache[currentMonth].sales_orders_series = data.sales_orders_series;
                    salesDataCache[currentMonth].sales_orders_series_breakdown = data.sales_orders_series_breakdown;
                }

                // Show success feedback
                console.log('Sales Orders data refreshed successfully:', data.message);
            }
        } catch (error) {
            console.error('Failed to refresh Sales Orders data:', error);
            alert(`Error refreshing data: ${error.message}`);
        } finally {
            // Re-enable button and stop spinning
            refreshButton.disabled = false;
            if (refreshIcon) {
                refreshIcon.classList.remove('animate-spin');
            }
        }
    };

    // Attach refresh handlers
    const refreshInvoicedButton = document.querySelector('[data-refresh-invoiced]');
    if (refreshInvoicedButton) {
        refreshInvoicedButton.addEventListener('click', refreshInvoicedData);
    }

    const refreshSalesOrdersButton = document.querySelector('[data-refresh-sales-orders]');
    if (refreshSalesOrdersButton) {
        refreshSalesOrdersButton.addEventListener('click', refreshSalesOrdersData);
    }

    // Initialize collapsible sections
    initializeCollapsibleSection('invoiced-chart');
    initializeCollapsibleSection('sales-orders-chart');
    initializeCollapsibleSection('subscriptions');
    initializeCollapsibleSection('external-hours');

    // Function to handle sales tab activation (called from both click and custom event)
    const handleSalesTabActivation = (month) => {
        // Update currentMonth to match the select element
        const selectedMonth = month || (monthSelect ? monthSelect.value : currentMonth);
        if (selectedMonth) {
            currentMonth = selectedMonth; // Sync currentMonth with actual selection
        }
        // If data is not cached, fetch it with loading overlay
        if (selectedMonth && !salesDataCache[selectedMonth]) {
            fetchSalesData(selectedMonth, true); // Pass true to show loading overlay
        } else if (selectedMonth && salesDataCache[selectedMonth]) {
            // Data is cached, but ensure UI is fully rendered
            // Resize charts after a brief delay to ensure DOM is ready
            setTimeout(() => {
                if (invoicedChart) invoicedChart.resize();
                if (salesOrdersChart) salesOrdersChart.resize();
                if (salesOrdersAgreementTypeChart) salesOrdersAgreementTypeChart.resize();
                if (agreementTypeChart) agreementTypeChart.resize();
            }, 100);
        }
    };

    // Listen for tab clicks on all tab buttons
    tabButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const targetTab = button.dataset.dashboardTab;
            if (targetTab === 'sales') {
                handleSalesTabActivation();
            }
        });
    });

    // Also listen for custom event dispatched from dashboard.js (e.g., after password verification)
    document.addEventListener('salesTabActivated', (event) => {
        handleSalesTabActivation(event.detail?.month);
    });

    // Also refresh sales data when month changes and sales tab is active
    if (monthSelect) {
        monthSelect.addEventListener('change', () => {
            const selectedMonth = monthSelect.value;
            const previousMonth = currentMonth;
            currentMonth = selectedMonth;

            const activeTab = Array.from(tabButtons).find(btn => btn.dataset.active === 'true');
            if (activeTab && activeTab.dataset.dashboardTab === 'sales') {
                // Clear cache for previous month
                if (previousMonth && previousMonth !== selectedMonth) {
                    delete salesDataCache[previousMonth];
                }
                // Clear cache for new month to force fresh fetch
                delete salesDataCache[selectedMonth];
                // Cancel any in-flight requests for other months by clearing the loading promise
                // This ensures stale data won't render
                if (salesDataLoadingPromise && salesDataLoadingPromise.month !== selectedMonth) {
                    salesDataLoadingPromise = null;
                }
                // Show loading overlay immediately and clear UI
                showLoadingOverlay();
                clearSalesUI();
                // Fetch new data with loading overlay and force refresh
                fetchSalesData(selectedMonth, true, true);
            } else {
                // Prefetch if on another tab (no loading overlay, but force refresh to get fresh data)
                if (previousMonth && previousMonth !== selectedMonth) {
                    delete salesDataCache[previousMonth];
                }
                delete salesDataCache[selectedMonth];
                fetchSalesData(selectedMonth, false, true);
            }
        });
    }

    // Initial prefetch on load - ensure currentMonth is set correctly first
    // Use requestAnimationFrame to ensure DOM is fully ready
    requestAnimationFrame(() => {
        try {
            // Ensure currentMonth is synced with the select element
            if (monthSelect && monthSelect.value) {
                currentMonth = monthSelect.value;
            }
            if (currentMonth) {
                fetchSalesData(currentMonth);
            } else {
                console.warn('No currentMonth set for initial sales dashboard load');
            }
        } catch (error) {
            console.error('Error initializing sales dashboard:', error);
            // Still try to load data even if initialization fails
            if (monthSelect && monthSelect.value) {
                currentMonth = monthSelect.value;
            }
            if (currentMonth) {
                fetchSalesData(currentMonth);
            }
        }
    });
});
