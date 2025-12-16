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

    // Function to render invoice list
    const renderInvoiceList = (invoices) => {
        if (!invoiceListBody || !Array.isArray(invoices)) return;

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
            No invoices found for selected month
          </td>
        </tr>
      `;
            if (debugInvoiceCount) {
                debugInvoiceCount.textContent = '0';
            }
            return;
        }

        invoiceListBody.innerHTML = invoices.map((invoice, index) => {
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

        if (orders.length === 0) {
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
        orders.forEach(order => {
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

        if (orders.length === 0) {
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

    // Function to update sales UI with data
    const updateSalesUI = (salesStats, subscriptionStats) => {
        if (!salesStats) return;

        // Update invoice count
        if (salesInvoiceCount) {
            salesInvoiceCount.textContent = salesStats.invoice_count.toLocaleString();
        }

        // Update sales order count
        if (salesOrderCount && salesStats.sales_order_count !== undefined) {
            salesOrderCount.textContent = salesStats.sales_order_count.toLocaleString();
        }

        // Update subscription count
        // Only update if subscriptionStats exists and BOTH counts are defined
        // This prevents showing "0" during loading when data is incomplete
        if (salesSubscriptionCount) {
            if (subscriptionStats && typeof subscriptionStats === 'object') {
                // Both counts must be defined (not undefined) to consider it valid data
                // This ensures we have complete data, not partial/loading data
                const hasCompleteStats = subscriptionStats.active_count !== undefined && 
                                        subscriptionStats.churned_count !== undefined;
                if (hasCompleteStats) {
                    const totalSubscriptions = (subscriptionStats.active_count || 0) + (subscriptionStats.churned_count || 0);
                    salesSubscriptionCount.textContent = totalSubscriptions.toLocaleString();
                    // Remove opacity if it was added during loading
                    salesSubscriptionCount.classList.remove('opacity-50');
                }
                // If subscriptionStats exists but doesn't have both counts defined, keep current state (don't change to 0 or ---)
            }
            // If no subscriptionStats, don't change it (keep it as --- from clearSalesUI)
        }

        // Update invoice trend comparison
        if (salesStats.comparison && salesComparison) {
            const { change_percentage, trend } = salesStats.comparison;

            // Show comparison container
            salesComparison.classList.remove('opacity-0');

            // Update trend icon
            if (salesTrendIcon) {
                salesTrendIcon.textContent = trend === 'up' ? 'trending_up' : 'trending_down';
            }

            // Update trend text
            if (salesTrendText) {
                salesTrendText.textContent = `${change_percentage.toFixed(1)}% vs last month`;
            }

            // Update colors based on trend
            if (trend === 'up') {
                salesComparison.classList.remove('text-rose-600');
                salesComparison.classList.add('text-emerald-600');
            } else {
                salesComparison.classList.remove('text-emerald-600');
                salesComparison.classList.add('text-rose-600');
            }
        } else {
            // Hide comparison if no data
            if (salesComparison) {
                salesComparison.classList.add('opacity-0');
            }
        }

        // Update sales order trend comparison
        if (salesStats.sales_order_comparison && salesOrderTrend) {
            const { change_percentage, trend } = salesStats.sales_order_comparison;

            const icon = trend === 'up' ? 'trending_up' : 'trending_down';
            const colorClass = trend === 'up' ? 'text-emerald-600' : 'text-rose-600';

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
        container.innerHTML = validProjects.map((project, index) => {
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

        const mrr = stats.mrr || 0;
        const activeCount = stats.active_count || 0;
        const churnedCount = stats.churned_count || 0;
        const newRenewCount = stats.new_renew_count || 0;
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
                    <div class="text-4xl font-bold text-slate-900 relative group cursor-help" title="${orderNamesTooltip}">${activeCount}</div>
                    <div class="mt-1 text-sm font-medium text-slate-600">Active (In Progress)</div>
                </div>
                <div class="flex items-center justify-center gap-12">
                    <div class="text-center">
                        <div class="text-4xl font-bold text-slate-900">${newRenewCount}</div>
                        <div class="mt-1 text-sm font-medium text-slate-600">New Subs / Renewal</div>
                    </div>
                    <div class="text-center">
                        <div class="text-4xl font-bold text-slate-900">${churnedCount}</div>
                        <div class="mt-1 text-sm font-medium text-slate-600">Churned</div>
                    </div>
                </div>
            </div>
        `;
    };

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

        if (!Array.isArray(subscriptions) || subscriptions.length === 0) {
            container.innerHTML = '<div class="text-center text-sm text-slate-500 py-8">No active subscriptions for this month</div>';
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

        subscriptions.forEach((sub, index) => {
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

    // Function to fetch and update sales data
    const fetchSalesData = async (month, showLoading = false, forceRefresh = false) => {
        // If force refresh, clear cache and UI first
        if (forceRefresh) {
            delete salesDataCache[month];
            clearSalesUI();
        }

        // Check cache first (only if not forcing refresh)
        if (!forceRefresh && salesDataCache[month]) {
            updateSalesUI(salesDataCache[month].sales_stats, salesDataCache[month].subscription_stats);
            if (salesDataCache[month].sales_stats && salesDataCache[month].sales_stats.invoices) {
                renderInvoiceList(salesDataCache[month].sales_stats.invoices);
            }
            if (salesDataCache[month].invoiced_series) {
                updateInvoicedChart(salesDataCache[month].invoiced_series);
            }
            if (salesDataCache[month].sales_orders_series) {
                updateSalesOrdersChart(salesDataCache[month].sales_orders_series);
            }
            if (salesDataCache[month].sales_orders_agreement_type_totals) {
                updateSalesOrdersAgreementTypeChart(salesDataCache[month].sales_orders_agreement_type_totals);
            }
            if (salesDataCache[month].sales_orders_project_totals) {
                updateSalesOrdersProjectCards(salesDataCache[month].sales_orders_project_totals);
            }
            if (salesDataCache[month].agreement_type_totals) {
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
            try {
                await salesDataLoadingPromise.promise;
                // Data should now be in cache, update UI
                if (salesDataCache[month]) {
                    updateSalesUI(salesDataCache[month].sales_stats);
                    if (salesDataCache[month].sales_stats && salesDataCache[month].sales_stats.invoices) {
                        renderInvoiceList(salesDataCache[month].sales_stats.invoices);
                    }
                    if (salesDataCache[month].invoiced_series) {
                        updateInvoicedChart(salesDataCache[month].invoiced_series);
                    }
                    if (salesDataCache[month].sales_orders_series) {
                        updateSalesOrdersChart(salesDataCache[month].sales_orders_series);
                    }
                    if (salesDataCache[month].sales_orders_agreement_type_totals) {
                        updateSalesOrdersAgreementTypeChart(salesDataCache[month].sales_orders_agreement_type_totals);
                    }
                    if (salesDataCache[month].sales_orders_project_totals) {
                        updateSalesOrdersProjectCards(salesDataCache[month].sales_orders_project_totals);
                    }
                    if (salesDataCache[month].agreement_type_totals) {
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
                }
            } catch (error) {
                console.error('Error waiting for sales data:', error);
            }
            return;
        }

        // If already loading for this month and not forcing refresh, wait for existing promise
        if (isLoading && !forceRefresh) {
            if (salesDataLoadingPromise && salesDataLoadingPromise.month === month) {
                try {
                    await salesDataLoadingPromise.promise;
                    // Data should now be in cache, update UI
                    if (salesDataCache[month]) {
                        updateSalesUI(salesDataCache[month].sales_stats, salesDataCache[month].subscription_stats);
                        if (salesDataCache[month].sales_stats && salesDataCache[month].sales_stats.invoices) {
                            renderInvoiceList(salesDataCache[month].sales_stats.invoices);
                        }
                        if (salesDataCache[month].invoiced_series) {
                            updateInvoicedChart(salesDataCache[month].invoiced_series);
                        }
                        if (salesDataCache[month].sales_orders_series) {
                            updateSalesOrdersChart(salesDataCache[month].sales_orders_series);
                        }
                        if (salesDataCache[month].sales_orders_agreement_type_totals) {
                            updateSalesOrdersAgreementTypeChart(salesDataCache[month].sales_orders_agreement_type_totals);
                        }
                        if (salesDataCache[month].sales_orders_project_totals) {
                            updateSalesOrdersProjectCards(salesDataCache[month].sales_orders_project_totals);
                        }
                        if (salesDataCache[month].agreement_type_totals) {
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
                    }
                } catch (error) {
                    console.error('Error waiting for sales data:', error);
                }
            }
            return;
        }

        isLoading = true;

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

                // Cache the result
                salesDataCache[month] = data;

                updateSalesUI(data.sales_stats, data.subscription_stats);

                // Render all UI elements and wait for each to complete
                // Use Promise.all to ensure all rendering completes before verification
                const renderingPromises = [];

                // Render invoice list (synchronous, but wait for DOM update)
                if (data.sales_stats && data.sales_stats.invoices) {
                    renderInvoiceList(data.sales_stats.invoices);
                    renderingPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }

                // Render sales order list
                if (data.sales_stats && data.sales_stats.sales_orders) {
                    renderSalesOrderList(data.sales_stats.sales_orders);
                    renderSalesOrdersGroupedByProject(data.sales_stats.sales_orders);
                    renderingPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }

                // Render subscriptions
                if (data.subscriptions) {
                    updateSubscriptionsList(data.subscriptions);
                    renderingPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }
                
                // Render subscription statistics
                if (data.subscription_stats) {
                    updateSubscriptionStatsCard(data.subscription_stats);
                    renderingPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }
                
                // Render external hours card
                if (data.external_hours_totals) {
                    updateExternalHoursCard(data.external_hours_totals);
                    renderingPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }
                
                // Render external hours by agreement type table
                if (data.external_hours_by_agreement) {
                    updateExternalHoursAgreementTable(data.external_hours_by_agreement);
                    renderingPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }

                // Wait for all DOM updates to complete
                await Promise.all(renderingPromises);

                // Now render charts (which may be async)
                const chartPromises = [];

                // Render invoiced chart
                if (data.invoiced_series) {
                    updateInvoicedChart(data.invoiced_series);
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
                if (data.sales_orders_series) {
                    updateSalesOrdersChart(data.sales_orders_series);
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
                if (data.sales_orders_agreement_type_totals) {
                    updateSalesOrdersAgreementTypeChart(data.sales_orders_agreement_type_totals);
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
                if (data.sales_orders_project_totals) {
                    updateSalesOrdersProjectCards(data.sales_orders_project_totals);
                    chartPromises.push(new Promise(resolve => {
                        requestAnimationFrame(() => {
                            requestAnimationFrame(resolve);
                        });
                    }));
                }

                // Render invoice agreement type chart
                if (data.agreement_type_totals) {
                    updateAgreementTypeChart(data.agreement_type_totals);
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

                // Force a synchronous layout recalculation
                void document.body.offsetHeight;

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
                throw error; // Re-throw so waiting promises know it failed
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
                // Update chart with refreshed data
                updateInvoicedChart(data.invoiced_series);

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
                // Update chart with refreshed data
                updateSalesOrdersChart(data.sales_orders_series);

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
        const selectedMonth = month || (monthSelect ? monthSelect.value : currentMonth);
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

    // Initial prefetch on load - load immediately alongside creative dashboard
    if (currentMonth) {
        fetchSalesData(currentMonth);
    }
});
