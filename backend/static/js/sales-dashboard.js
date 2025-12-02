// Sales Dashboard Tab Functionality
document.addEventListener("DOMContentLoaded", () => {
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

    const monthSelect = document.querySelector('[data-month-select]');
    const tabButtons = document.querySelectorAll('[data-dashboard-tab]');

    // Invoice list elements
    const toggleInvoiceListBtn = document.querySelector('[data-toggle-invoice-list]');
    const invoiceListContainer = document.querySelector('[data-invoice-list-container]');
    const invoiceListBody = document.querySelector('[data-invoice-list-body]');
    const debugInvoiceCount = document.querySelector('[data-debug-invoice-count]');

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

    // Function to render sales order list
    const renderSalesOrderList = (orders) => {
        if (!salesOrderListBody || !Array.isArray(orders)) return;

        if (orders.length === 0) {
            salesOrderListBody.innerHTML = `
        <tr>
          <td colspan="7" class="px-4 py-8 text-center text-slate-500">
            No sales orders found for selected month
          </td>
        </tr>
      `;
            return;
        }

        salesOrderListBody.innerHTML = orders.map((order, index) => {
            const aedTotal = order.x_studio_aed_total ? parseFloat(order.x_studio_aed_total).toLocaleString('en-AE', { style: 'currency', currency: 'AED' }) : '0.00 AED';
            const tags = Array.isArray(order.tags) ? order.tags.join(', ') : '';

            return `
        <tr class="hover:bg-slate-50">
          <td class="px-4 py-3 font-medium text-slate-900">${order.name || 'N/A'}</td>
          <td class="px-4 py-3 text-slate-600">${order.date_order ? order.date_order.split(' ')[0] : 'N/A'}</td>
          <td class="px-4 py-3 text-slate-600 max-w-xs truncate" title="${order.project_name}">${order.project_name}</td>
          <td class="px-4 py-3 text-slate-600">${order.market}</td>
          <td class="px-4 py-3 text-slate-600">${order.agreement_type}</td>
          <td class="px-4 py-3 text-slate-600 max-w-xs truncate" title="${tags}">${tags}</td>
          <td class="px-4 py-3 font-medium text-slate-900 text-right">${aedTotal}</td>
        </tr>
      `;
        }).join('');
    };

    // Function to update sales UI with data
    const updateSalesUI = (salesStats) => {
        if (!salesStats) return;

        // Update invoice count
        if (salesInvoiceCount) {
            salesInvoiceCount.textContent = salesStats.invoice_count.toLocaleString();
        }

        // Update sales order count
        if (salesOrderCount && salesStats.sales_order_count !== undefined) {
            salesOrderCount.textContent = salesStats.sales_order_count.toLocaleString();
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

    // Function to fetch and update sales data
    const fetchSalesData = async (month) => {
        // Check cache first
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
                }
            } catch (error) {
                console.error('Error waiting for sales data:', error);
            }
            return;
        }

        if (isLoading) return;
        isLoading = true;

        // Create a promise for this fetch so other calls can wait for it
        const fetchPromise = (async () => {
            try {
                // Show loading state if not cached
                if (salesInvoiceCount) {
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

                updateSalesUI(data.sales_stats);

                // Render invoice list
                if (data.sales_stats && data.sales_stats.invoices) {
                    renderInvoiceList(data.sales_stats.invoices);
                }

                // Render sales order list
                if (data.sales_stats && data.sales_stats.sales_orders) {
                    renderSalesOrderList(data.sales_stats.sales_orders);
                }

                // Render invoiced chart
                if (data.invoiced_series) {
                    updateInvoicedChart(data.invoiced_series);
                }

                // Render Sales Orders chart
                if (data.sales_orders_series) {
                    updateSalesOrdersChart(data.sales_orders_series);
                }

                // Render Sales Orders agreement type chart
                if (data.sales_orders_agreement_type_totals) {
                    updateSalesOrdersAgreementTypeChart(data.sales_orders_agreement_type_totals);
                }

                // Render Sales Orders project cards
                if (data.sales_orders_project_totals) {
                    updateSalesOrdersProjectCards(data.sales_orders_project_totals);
                }

                // Render invoice agreement type chart
                if (data.agreement_type_totals) {
                    updateAgreementTypeChart(data.agreement_type_totals);
                }

                // Render subscriptions
                if (data.subscriptions) {
                    updateSubscriptionsList(data.subscriptions);
                }
                
                // Render subscription statistics
                if (data.subscription_stats) {
                    updateSubscriptionStatsCard(data.subscription_stats);
                }

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

    // Listen for tab clicks on all tab buttons
    tabButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const targetTab = button.dataset.dashboardTab;

            // If sales tab is clicked, data should already be loaded or loading
            // Just resize charts if needed when tab becomes visible
            if (targetTab === 'sales') {
                const selectedMonth = monthSelect ? monthSelect.value : currentMonth;
                // Data should already be loading from initial prefetch, but ensure it's fetched if not cached
                if (selectedMonth && !salesDataCache[selectedMonth]) {
                    fetchSalesData(selectedMonth);
                }
                // Resize charts if needed when tab becomes visible
                setTimeout(() => {
                    if (invoicedChart) {
                        invoicedChart.resize();
                    }
                    if (salesOrdersChart) {
                        salesOrdersChart.resize();
                    }
                    if (salesOrdersAgreementTypeChart) {
                        salesOrdersAgreementTypeChart.resize();
                    }
                    if (agreementTypeChart) {
                        agreementTypeChart.resize();
                    }
                }, 0);
            }
        });
    });

    // Also refresh sales data when month changes and sales tab is active
    if (monthSelect) {
        monthSelect.addEventListener('change', () => {
            const selectedMonth = monthSelect.value;
            currentMonth = selectedMonth;

            // Clear cache for this month to force refresh on explicit change
            // delete salesDataCache[selectedMonth]; 

            const activeTab = Array.from(tabButtons).find(btn => btn.dataset.active === 'true');
            if (activeTab && activeTab.dataset.dashboardTab === 'sales') {
                fetchSalesData(selectedMonth);
            } else {
                // Prefetch if on another tab
                fetchSalesData(selectedMonth);
            }
        });
    }

    // Initial prefetch on load - load immediately alongside creative dashboard
    if (currentMonth) {
        fetchSalesData(currentMonth);
    }
});
