// Sales list/table rendering: invoice list, sales-order list, grouped project
// table, and the subscriptions table (with their sort/cache state). Bodies
// verbatim from main.js (original indentation kept).
import { formatHoursToMinutes, boundsFromSelectedPeriod } from "./period-utils.js";
import { applyFilters } from "./filter-state.js";

export const salesOrderListBody = document.querySelector('[data-sales-order-list]');
export const invoiceListBody = document.querySelector('[data-invoice-list-body]');

// main.js owns the currently selected month; tables read it lazily via this hook.
let currentMonthProvider = () => null;
export const setCurrentMonthProvider = (fn) => {
  currentMonthProvider = fn;
};

    export const renderInvoiceList = (invoices) => {
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

    /** Last orders passed to the grouped-by-project table (for re-sort without refetch). */
    let cachedSalesOrdersForProjectTable = null;
    /** Sort column: ext | int | aed; direction: desc = largest first, asc = smallest first */
    let salesOrdersProjectTableSort = { column: 'aed', direction: 'desc' };

    const syncSalesOrdersProjectTableSortSelects = () => {
        ['ext', 'int', 'aed'].forEach((col) => {
            const el = document.querySelector(`[data-project-sort-col="${col}"]`);
            if (!el) {
                return;
            }
            if (salesOrdersProjectTableSort.column === col) {
                el.value = salesOrdersProjectTableSort.direction;
            } else {
                el.value = '';
            }
        });
    };

    const sortProjectTableGroups = (groups, column, direction) => {
        const key =
            column === 'ext' ? 'total_ext_hrs' : column === 'int' ? 'total_int_hrs' : 'total_aed';
        const sorted = [...groups];
        sorted.sort((a, b) => {
            const av = Number(a[key]) || 0;
            const bv = Number(b[key]) || 0;
            return direction === 'desc' ? bv - av : av - bv;
        });
        return sorted;
    };

    // Function to render sales orders grouped by project
    export const renderSalesOrdersGroupedByProject = (orders) => {
        const tbody = document.getElementById('salesOrdersGroupedTableBody');
        if (!tbody || !Array.isArray(orders)) return;

        cachedSalesOrdersForProjectTable = orders;
        
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
            syncSalesOrdersProjectTableSortSelects();
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

        let projectGroups = Object.values(groupedByProject);
        const { column: sortCol, direction: sortDir } = salesOrdersProjectTableSort;
        projectGroups = sortProjectTableGroups(projectGroups, sortCol, sortDir);

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
        syncSalesOrdersProjectTableSortSelects();
    };

    const salesOrdersGroupedTableEl = document.getElementById('salesOrdersGroupedTable');
    if (salesOrdersGroupedTableEl) {
        salesOrdersGroupedTableEl.addEventListener('change', (e) => {
            const t = e.target;
            if (!t || !t.matches || !t.matches('[data-project-sort-col]')) {
                return;
            }
            const col = t.getAttribute('data-project-sort-col');
            const v = t.value;
            if (!v) {
                salesOrdersProjectTableSort = { column: 'aed', direction: 'desc' };
            } else if (col === 'ext' || col === 'int' || col === 'aed') {
                salesOrdersProjectTableSort = { column: col, direction: v };
            }
            syncSalesOrdersProjectTableSortSelects();
            if (cachedSalesOrdersForProjectTable) {
                renderSalesOrdersGroupedByProject(cachedSalesOrdersForProjectTable);
            }
        });
    }

    /** Subscriptions list: re-sort without refetch (Ext. sold / used / monthly payment). */
    let cachedSubscriptionsForListTable = null;
    /** Sort column: sold | used | payment */
    let subscriptionsListTableSort = { column: 'payment', direction: 'desc' };
    /** Selected period bounds for churn / new pills on subscription rows */
    let subscriptionsListPeriodBounds = { monthStart: null, monthEnd: null };

    const updateSubscriptionsListPeriodBounds = (boundsSource) => {
        if (!boundsSource || typeof boundsSource !== 'object') {
            return;
        }
        const pk = boundsSource.selected_month != null ? boundsSource.selected_month : currentMonthProvider();
        const kind = boundsSource.period_kind || 'month';
        const subRange = boundsFromSelectedPeriod(pk, kind);
        if (subRange) {
            subscriptionsListPeriodBounds = {
                monthStart: subRange.monthStart,
                monthEnd: subRange.monthEnd,
            };
        } else {
            const now = new Date();
            subscriptionsListPeriodBounds = {
                monthStart: new Date(now.getFullYear(), now.getMonth(), 1),
                monthEnd: new Date(now.getFullYear(), now.getMonth() + 1, 0),
            };
        }
    };

    const buildSubscriptionLifecyclePillsHtml = (sub) => {
        const ms = subscriptionsListPeriodBounds.monthStart;
        const me = subscriptionsListPeriodBounds.monthEnd;
        let isChurned = null;
        let isNew = null;
        if (
            ms instanceof Date &&
            me instanceof Date &&
            !isNaN(ms.getTime()) &&
            !isNaN(me.getTime())
        ) {
            if (sub.end_date) {
                const endDate = new Date(sub.end_date);
                isChurned = !isNaN(endDate.getTime()) && endDate <= me;
            } else {
                isChurned = false;
            }
            const startStr = sub.start_date || sub.first_contract_date;
            if (startStr) {
                const startDate = new Date(startStr);
                isNew = !isNaN(startDate.getTime()) && ms <= startDate && startDate <= me;
            } else {
                isNew = false;
            }
        }
        if (isChurned === null && typeof sub.is_churned === 'boolean') {
            isChurned = sub.is_churned;
        }
        if (isNew === null && typeof sub.is_new_in_month === 'boolean') {
            isNew = sub.is_new_in_month;
        }
        isChurned = !!isChurned;
        isNew = !!isNew;
        const parts = [];
        if (isChurned) {
            parts.push(
                '<span class="inline-flex shrink-0 items-center rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">Churned</span>'
            );
        }
        if (isNew) {
            parts.push(
                '<span class="inline-flex shrink-0 items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">New</span>'
            );
        }
        if (parts.length === 0) {
            return '';
        }
        return `<span class="ml-2 inline-flex shrink-0 flex-wrap items-center gap-1">${parts.join('')}</span>`;
    };

    const syncSubscriptionsListTableSortSelects = () => {
        const root = document.getElementById('subscriptionsList');
        if (!root) {
            return;
        }
        ['sold', 'used', 'payment'].forEach((col) => {
            const el = root.querySelector(`[data-subscription-sort-col="${col}"]`);
            if (!el) {
                return;
            }
            if (subscriptionsListTableSort.column === col) {
                el.value = subscriptionsListTableSort.direction;
            } else {
                el.value = '';
            }
        });
    };

    const sortSubscriptionsListRows = (subs, column, direction) => {
        const sorted = [...subs];
        const getVal = (sub) => {
            if (column === 'sold') {
                return Number(sub.external_sold_hours) || 0;
            }
            if (column === 'used') {
                return Number(sub.external_hours_used) || 0;
            }
            return Number(sub.monthly_recurring_payment) || 0;
        };
        sorted.sort((a, b) => {
            const av = getVal(a);
            const bv = getVal(b);
            return direction === 'desc' ? bv - av : av - bv;
        });
        return sorted;
    };

    const subscriptionsListContainerEl = document.getElementById('subscriptionsList');
    if (subscriptionsListContainerEl) {
        subscriptionsListContainerEl.addEventListener('change', (e) => {
            const t = e.target;
            if (!t || !t.matches || !t.matches('[data-subscription-sort-col]')) {
                return;
            }
            const col = t.getAttribute('data-subscription-sort-col');
            const v = t.value;
            if (!v) {
                subscriptionsListTableSort = { column: 'payment', direction: 'desc' };
            } else if (col === 'sold' || col === 'used' || col === 'payment') {
                subscriptionsListTableSort = { column: col, direction: v };
            }
            syncSubscriptionsListTableSortSelects();
            if (cachedSubscriptionsForListTable) {
                updateSubscriptionsList(cachedSubscriptionsForListTable);
            }
        });
    }

    // Function to render sales order list
    export const renderSalesOrderList = (orders) => {
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

    export const updateSubscriptionsList = (subscriptions, boundsSource) => {
        const container = document.getElementById('subscriptionsList');
        if (!container) return;

        if (boundsSource !== undefined && boundsSource !== null) {
            updateSubscriptionsListPeriodBounds(boundsSource);
        }

        if (Array.isArray(subscriptions)) {
            cachedSubscriptionsForListTable = subscriptions;
        }
        
        const escapeAttr = (value) => {
            if (typeof value !== 'string') return '';
            return value
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        };

        const buildExternalHoursTooltip = (breakdown) => {
            if (!Array.isArray(breakdown) || breakdown.length === 0) return '';
            return breakdown
                .map((item) => {
                    const created = item.created_on_display || item.created_on || 'Created On: N/A';
                    const title = item.title || 'Subtask';
                    const hoursValue = typeof item.hours === 'number' ? item.hours : 0;
                    const hoursDisplay = item.hours_display || formatHoursToMinutes(hoursValue);
                    return `Created On: ${created} • ${title} • ${hoursDisplay}`;
                })
                .join('\n');
        };

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

        const sortedSubscriptions = sortSubscriptionsListRows(
            filteredSubscriptions,
            subscriptionsListTableSort.column,
            subscriptionsListTableSort.direction
        );

        // Sort controls: match creatives `salesOrdersGroupedTable` (dashboard.html) exactly.
        const subscriptionSortSelectClass =
            'max-w-full cursor-pointer border-0 border-b border-dotted border-slate-300/90 bg-transparent py-0 pl-0 pr-6 text-right text-[11px] text-slate-500 underline-offset-2 hover:border-slate-400 hover:text-slate-700 focus:outline-none focus:ring-0';

        // Build table HTML
        let html = `
            <div class="overflow-x-auto">
                <table id="subscriptionsListTable" class="w-full text-left text-sm table-fixed" style="table-layout: fixed;">
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
                            <th class="px-4 py-2.5 font-semibold text-slate-700">Client</th>
                            <th class="px-4 py-2.5 font-semibold text-slate-700">Order</th>
                            <th class="px-4 py-2.5 font-semibold text-slate-700">Market</th>
                            <th class="px-4 py-2.5 text-right font-semibold text-slate-700">Ext. Hrs Sold</th>
                            <th class="px-4 py-2.5 text-right font-semibold text-slate-700">Ext. Hrs Used</th>
                            <th class="px-4 py-2.5 font-semibold text-slate-700">Status</th>
                            <th class="px-4 py-2.5 text-right font-semibold text-slate-700">Monthly Payment</th>
                        </tr>
                        <tr class="border-b border-slate-100 bg-slate-50/90 text-[11px] font-normal text-slate-500">
                            <th colspan="3" class="px-4 py-1.5 text-left font-normal text-slate-400">
                                <span class="select-none">Sort</span>
                            </th>
                            <th class="px-4 py-1.5 text-right align-middle font-normal">
                                <label class="sr-only" for="subscriptionSortSold">Sort by external hours sold</label>
                                <select id="subscriptionSortSold" data-subscription-sort-col="sold" title="Sort by external hours sold"
                                    class="${subscriptionSortSelectClass}">
                                    <option value="">—</option>
                                    <option value="desc">High → low</option>
                                    <option value="asc">Low → high</option>
                                </select>
                            </th>
                            <th class="px-4 py-1.5 text-right align-middle font-normal">
                                <label class="sr-only" for="subscriptionSortUsed">Sort by external hours used</label>
                                <select id="subscriptionSortUsed" data-subscription-sort-col="used" title="Sort by external hours used"
                                    class="${subscriptionSortSelectClass}">
                                    <option value="">—</option>
                                    <option value="desc">High → low</option>
                                    <option value="asc">Low → high</option>
                                </select>
                            </th>
                            <th class="px-4 py-1.5 font-normal" aria-hidden="true"></th>
                            <th class="px-4 py-1.5 text-right align-middle font-normal">
                                <label class="sr-only" for="subscriptionSortPayment">Sort by monthly payment</label>
                                <select id="subscriptionSortPayment" data-subscription-sort-col="payment" title="Sort by monthly payment"
                                    class="${subscriptionSortSelectClass}">
                                    <option value="">—</option>
                                    <option value="desc" selected>High → low</option>
                                    <option value="asc">Low → high</option>
                                </select>
                            </th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 bg-white" data-subscription-table-body>
            `;

        sortedSubscriptions.forEach((sub, index) => {
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
            const externalHoursUsed = sub.external_hours_used_display || '0:00';
            const monthlyPayment = sub.monthly_recurring_payment_display || 'AED 0.00';
            const breakdownTooltip = buildExternalHoursTooltip(sub.external_hours_breakdown);
            const tooltipAttr = breakdownTooltip ? ` title="${escapeAttr(breakdownTooltip)}"` : '';
            const lifecyclePillsHtml = buildSubscriptionLifecyclePillsHtml(sub);

                html += `
                <tr class="hover:bg-slate-50">
                    <td class="px-4 py-3 font-medium text-slate-900 min-w-0" title="${escapeAttr(projectName)}">
                      <div class="flex min-w-0 items-center gap-1.5">
                        <span class="min-w-0 truncate">${projectName}</span>${lifecyclePillsHtml}
                      </div>
                    </td>
                    <td class="px-4 py-3 text-slate-600 truncate" title="${orderName}">${orderName}</td>
                    <td class="px-4 py-3 text-slate-600 truncate" title="${market}">${market}</td>
                    <td class="px-4 py-3 text-slate-600 text-right whitespace-nowrap">${externalHoursSold}</td>
                    <td class="px-4 py-3 text-slate-600 text-right whitespace-nowrap cursor-help"${tooltipAttr}>${externalHoursUsed}</td>
                    <td class="px-4 py-3">${statusBadge}</td>
                    <td class="px-4 py-3 font-medium text-slate-900 text-right whitespace-nowrap">${monthlyPayment}</td>
                </tr>
                `;
            });

            html += `
                    </tbody>
                </table>
                </div>
            `;

        container.innerHTML = html;
        syncSubscriptionsListTableSortSelects();
    };
