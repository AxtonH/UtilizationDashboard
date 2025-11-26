// Sales Dashboard Tab Functionality
document.addEventListener("DOMContentLoaded", () => {
    // Sales dashboard elements
    const salesInvoiceCount = document.querySelector('[data-sales-invoice-count]');
    const salesTrendContainer = document.querySelector('[data-sales-trend-container]');
    const salesComparison = document.querySelector('[data-sales-comparison]');
    const salesTrendIcon = document.querySelector('[data-sales-trend-icon]');
    const salesTrendText = document.querySelector('[data-sales-trend-text]');
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

    // Function to update sales UI with data
    const updateSalesUI = (salesStats) => {
        if (!salesStats) return;

        // Update invoice count
        if (salesInvoiceCount) {
            salesInvoiceCount.textContent = salesStats.invoice_count.toLocaleString();
        }

        // Update trend comparison
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
    };

    // Chart instances
    let invoicedChart = null;
    let agreementTypeChart = null;

    // Plugin to draw AED values above bars (for vertical bars)
    const barValuePlugin = {
        id: 'barValuePlugin',
        afterDatasetsDraw: function(chart) {
            const ctx = chart.ctx;
            ctx.save();
            ctx.font = '12px sans-serif';
            ctx.fillStyle = '#64748b';
            
            chart.data.datasets.forEach((dataset, i) => {
                const meta = chart.getDatasetMeta(i);
                meta.data.forEach((bar, index) => {
                    const value = dataset.data[index];
                    if (value !== null && value !== undefined && value > 0) {
                        const formattedValue = new Intl.NumberFormat('en-AE', { 
                            style: 'currency', 
                            currency: 'AED',
                            minimumFractionDigits: 0,
                            maximumFractionDigits: 0
                        }).format(value);
                        
                        // Check if horizontal or vertical bars
                        if (chart.options.indexAxis === 'y') {
                            // Horizontal bars - place value to the right
                            ctx.textAlign = 'left';
                            ctx.textBaseline = 'middle';
                            ctx.fillText(formattedValue, bar.x + bar.width + 8, bar.y);
                        } else {
                            // Vertical bars - place value above
                            // For grouped bars, adjust position based on dataset index
                            const isGrouped = chart.data.datasets.length > 1;
                            let xOffset = 0;
                            if (isGrouped) {
                                // Calculate offset for grouped bars
                                // Chart.js automatically positions grouped bars, so we use bar.x directly
                                // but we need to account for the bar's center position
                                xOffset = 0; // bar.x is already positioned correctly for grouped bars
                            }
                            ctx.textAlign = 'center';
                            ctx.textBaseline = 'bottom';
                            ctx.fillText(formattedValue, bar.x, bar.y - 5);
                        }
                    }
                });
            });
            ctx.restore();
        }
    };

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
                        barValuePlugin: barValuePlugin
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            display: false, // Hide X-axis scale/values
                            grid: {
                                display: false,
                                drawBorder: false
                            },
                            ticks: {
                                display: false // Hide X-axis ticks/values
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
                    plugins: {
                        legend: {
                            display: hasPreviousYear,
                            position: 'top',
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
                        barValuePlugin: barValuePlugin,
                        // Plugin to create overlapping effect - blue bars overlap yellow bars
                        afterLayout: function(chart) {
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
            if (salesDataCache[month].agreement_type_totals) {
                updateAgreementTypeChart(salesDataCache[month].agreement_type_totals);
            }
            return;
        }

        if (isLoading) return;
        isLoading = true;

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

            // Render chart
            if (data.invoiced_series) {
                updateInvoicedChart(data.invoiced_series);
            }

            // Render agreement type chart
            if (data.agreement_type_totals) {
                updateAgreementTypeChart(data.agreement_type_totals);
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
        } finally {
            isLoading = false;
            if (salesInvoiceCount) salesInvoiceCount.classList.remove('opacity-50');
        }
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

    // Attach refresh handler
    const refreshButton = document.querySelector('[data-refresh-invoiced]');
    if (refreshButton) {
        refreshButton.addEventListener('click', refreshInvoicedData);
    }

    // Initialize collapsible section
    initializeCollapsibleSection('invoiced-chart');

    // Listen for tab clicks on all tab buttons
    tabButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const targetTab = button.dataset.dashboardTab;

            // If sales tab is clicked, fetch data
            if (targetTab === 'sales') {
                const selectedMonth = monthSelect ? monthSelect.value : currentMonth;
                if (selectedMonth) {
                    fetchSalesData(selectedMonth);
                }
                // Resize charts if needed when tab becomes visible
                setTimeout(() => {
                    if (invoicedChart) {
                        invoicedChart.resize();
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

    // Initial prefetch on load
    if (currentMonth) {
        // Small delay to let main dashboard load first
        setTimeout(() => {
            fetchSalesData(currentMonth);
        }, 1000);
    }
});
