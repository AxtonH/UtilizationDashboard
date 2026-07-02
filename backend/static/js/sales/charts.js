// Chart.js rendering for the sales dashboard. Bodies verbatim from main.js
// (original indentation kept). Chart handles live on the shared
// chartInstances object so main.js (clearSalesUI, resize sites) mutates the
// same state the update functions write.

export const chartInstances = {
    invoiced: null,
    agreementType: null,
    salesOrders: null,
    salesOrdersAgreementType: null,
};


    // Register the datalabels plugin
    Chart.register(ChartDataLabels);

    // Function to init/update agreement type chart (horizontal bar chart)
    export const updateAgreementTypeChart = (agreementTotals) => {
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
            if (chartInstances.agreementType) {
                chartInstances.agreementType.destroy();
                chartInstances.agreementType = null;
            }
            return;
        }

        const labels = Object.keys(filteredTotals);
        const data = Object.values(filteredTotals);

        // Match the monthly invoiced chart style but keep horizontal bars
        const barColor = '#5AA0F9'; // Same blue as monthly invoiced chart
        const hoverColor = '#4a8ee6'; // Slightly darker blue on hover

        if (chartInstances.agreementType) {
            // If chart exists but no data, destroy it
            if (labels.length === 0) {
                chartInstances.agreementType.destroy();
                chartInstances.agreementType = null;
                return;
            }
            chartInstances.agreementType.data.labels = labels;
            chartInstances.agreementType.data.datasets[0].data = data;
            chartInstances.agreementType.update('active');
        } else {
            chartInstances.agreementType = new Chart(ctx, {
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
    export const updateInvoicedChart = (seriesData) => {
        const ctx = document.getElementById('invoicedChart');
        if (!ctx) return;

        const labels = seriesData.map(d => d.label);
        const currentYearData = seriesData.map(d => d.amount_aed);
        const previousYearData = seriesData.map(d => d.previous_year_amount_aed || 0);
        const hasPreviousYear = seriesData.some(d => d.previous_year_amount_aed !== undefined);
        const currentYear = seriesData.length > 0 ? seriesData[0].year : new Date().getFullYear();
        const previousYear = currentYear - 1;

        if (chartInstances.invoiced) {
            chartInstances.invoiced.data.labels = labels;

            // Update datasets maintaining order: previous year first, current year second
            if (hasPreviousYear) {
                if (chartInstances.invoiced.data.datasets.length >= 2) {
                    // Update existing datasets
                    chartInstances.invoiced.data.datasets[0].data = previousYearData; // Previous year (yellow) - behind
                    chartInstances.invoiced.data.datasets[1].data = currentYearData; // Current year (blue) - in front
                } else if (chartInstances.invoiced.data.datasets.length === 1) {
                    // Add previous year dataset before current year
                    chartInstances.invoiced.data.datasets.unshift({
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
                    chartInstances.invoiced.data.datasets[1].label = `${currentYear}`;
                }
            } else {
                // No previous year data, just update current year
                if (chartInstances.invoiced.data.datasets.length > 0) {
                    chartInstances.invoiced.data.datasets[0].data = currentYearData;
                    chartInstances.invoiced.data.datasets[0].label = `${currentYear}`;
                }
                // Remove previous year dataset if it exists
                if (chartInstances.invoiced.data.datasets.length > 1) {
                    chartInstances.invoiced.data.datasets.shift();
                }
            }
            chartInstances.invoiced.update('active');
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

            chartInstances.invoiced = new Chart(ctx, {
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
    export const updateSalesOrdersAgreementTypeChart = (agreementTotals) => {
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
            if (chartInstances.salesOrdersAgreementType) {
                chartInstances.salesOrdersAgreementType.destroy();
                chartInstances.salesOrdersAgreementType = null;
            }
            return;
        }

        const labels = Object.keys(filteredTotals);
        const data = Object.values(filteredTotals);

        // Match the monthly invoiced chart style but keep horizontal bars
        const barColor = '#5AA0F9'; // Same blue as monthly invoiced chart
        const hoverColor = '#4a8ee6'; // Slightly darker blue on hover

        if (chartInstances.salesOrdersAgreementType) {
            // If chart exists but no data, destroy it
            if (labels.length === 0) {
                chartInstances.salesOrdersAgreementType.destroy();
                chartInstances.salesOrdersAgreementType = null;
                return;
            }
            chartInstances.salesOrdersAgreementType.data.labels = labels;
            chartInstances.salesOrdersAgreementType.data.datasets[0].data = data;
            chartInstances.salesOrdersAgreementType.update('active');
        } else {
            chartInstances.salesOrdersAgreementType = new Chart(ctx, {
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
    export const updateSalesOrdersProjectCards = (projectTotals) => {
        const container = document.getElementById('salesOrdersProjectCards');
        if (!container) return;

        // Ensure we have valid data
        if (!Array.isArray(projectTotals) || projectTotals.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center text-sm text-slate-500 py-8">No project data available for this month</div>';
            return;
        }

        // Filter out zero values, sort by Total (AED) highest to lowest, then create cards
        const validProjects = projectTotals
            .filter(p => (p.total_amount_aed || 0) > 0)
            .sort((a, b) => (b.total_amount_aed || 0) - (a.total_amount_aed || 0));

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
    export const updateSalesOrdersChart = (seriesData) => {
        const ctx = document.getElementById('salesOrdersChart');
        if (!ctx) return;

        const labels = seriesData.map(d => d.label);
        const currentYearData = seriesData.map(d => d.amount_aed);
        const previousYearData = seriesData.map(d => d.previous_year_amount_aed || 0);
        const hasPreviousYear = seriesData.some(d => d.previous_year_amount_aed !== undefined);
        const currentYear = seriesData.length > 0 ? seriesData[0].year : new Date().getFullYear();
        const previousYear = currentYear - 1;

        if (chartInstances.salesOrders) {
            chartInstances.salesOrders.data.labels = labels;

            // Update datasets maintaining order: previous year first, current year second
            if (hasPreviousYear) {
                if (chartInstances.salesOrders.data.datasets.length >= 2) {
                    // Update existing datasets
                    chartInstances.salesOrders.data.datasets[0].data = previousYearData; // Previous year (yellow) - behind
                    chartInstances.salesOrders.data.datasets[1].data = currentYearData; // Current year (blue) - in front
                } else if (chartInstances.salesOrders.data.datasets.length === 1) {
                    // Add previous year dataset before current year
                    chartInstances.salesOrders.data.datasets.unshift({
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
                    chartInstances.salesOrders.data.datasets[1].label = `${currentYear}`;
                }
            } else {
                // No previous year data, just update current year
                if (chartInstances.salesOrders.data.datasets.length > 0) {
                    chartInstances.salesOrders.data.datasets[0].data = currentYearData;
                    chartInstances.salesOrders.data.datasets[0].label = `${currentYear}`;
                }
                // Remove previous year dataset if it exists
                if (chartInstances.salesOrders.data.datasets.length > 1) {
                    chartInstances.salesOrders.data.datasets.shift();
                }
            }
            chartInstances.salesOrders.update('active');
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

            chartInstances.salesOrders = new Chart(ctx, {
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

