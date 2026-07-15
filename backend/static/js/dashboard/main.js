// Entry module for the creatives dashboard (loaded with type="module").
// Modules are deferred, but guard on readyState so init runs exactly once
// whether or not DOMContentLoaded has already fired.
import {
  formatHours,
  formatHoursWhole,
  formatAed,
  parseDateValue,
  parseMonthBounds,
  isWithinMonth,
  registerPoolLabel,
  registerPoolLabelsFromData,
  getPoolLabel,
  POOL_DEFINITIONS,
  CLIENT_POOL_DEFINITIONS,
  CLIENT_POOL_MATCHERS,
  CLIENT_POOL_ALIAS_LOOKUP,
  normalizeClientPoolSlug,
} from "./utils.js";
import { initCreativeGroups } from "./groups.js";
import { createCollapsibleSections } from "./collapsible.js";
import {
  computeAggregates,
  calculateExternalHours,
  computePoolStats,
  monthAnchorUsesBuAssignmentModel,
  filterCreativesClientSide,
  computeFilteredHeadcount,
  computeFilteredTasksStats,
  computeFilteredOvertimeStats,
  computeFilteredPoolStats,
  sumPreviousTotalsForBuFilters,
  sumPreviousTotalsForFilters,
  buildComparisonFromTotals,
  applyNewJoinerFlipToCreative,
} from "./compute.js";
import {
  parseDatasetJson,
  computeClientPoolSummary,
  normalizeClientPoolSummary,
  buildFilteredClientData,
} from "./client-data.js";
import { createCreativesApi } from "./api.js";
import { initializeServerRenderedCards, createCardRenderer } from "./cards.js";
import { configureDailyHours, warmDailyHours } from "./daycal.js";
import { initTimecardExport } from "./export.js";

function initDashboard() {
  const grid = document.querySelector("[data-creatives-grid]");
  const clientMarketGrid = document.querySelector("[data-client-market-grid]");
  const clientSubscriptionGrid = document.querySelector("[data-client-subscription-grid]");
  const subscriptionSection = document.querySelector("[data-client-subscription-section]");
  const subscriptionHoursSummary = subscriptionSection?.querySelector(
    "[data-subscription-monthly-hours]"
  );
  const subscriptionUsedHoursSummary = subscriptionSection?.querySelector(
    "[data-subscription-used-hours]"
  );
  const subscriptionAedSummary = subscriptionSection?.querySelector(
    "[data-subscription-total-aed]"
  );
  const subscriptionCountBadge = subscriptionSection?.querySelector(
    "[data-subscription-summary-count]"
  );
  const subscriptionCountValue = subscriptionCountBadge?.querySelector(
    "[data-subscription-count-value]"
  );
  const subscriptionSummarySection = document.querySelector("[data-subscription-summary]");
  const subscriptionSummaryCount = subscriptionSummarySection?.querySelector("[data-subscription-summary-count]");
  const subscriptionSummaryHours = subscriptionSummarySection?.querySelector("[data-subscription-summary-hours]");
  const subscriptionSummaryUsedHours = subscriptionSummarySection?.querySelector("[data-subscription-summary-used-hours]");
  const subscriptionSummaryRevenue = subscriptionSummarySection?.querySelector("[data-subscription-summary-revenue]");
  const subscriptionParentTasksBadge = document.querySelector("[data-subscription-parent-tasks-count]");
  const subscriptionParentTasksValue = subscriptionParentTasksBadge?.querySelector("[data-subscription-parent-tasks-value]");
  const subscriptionTopClientsSection = document.querySelector("[data-subscription-top-clients]");
  const subscriptionTopClientsBody = subscriptionTopClientsSection?.querySelector("[data-top-clients-body]");
  const subscriptionTopClientsEmpty = subscriptionTopClientsSection?.querySelector("[data-top-clients-empty]");
  const poolSummarySection = document.querySelector("[data-pool-external-summary]");
  const poolSummaryBody = poolSummarySection?.querySelector("[data-pool-summary-body]");
  const poolSummaryEmpty = poolSummarySection?.querySelector("[data-pool-summary-empty]");
  const subscriptionUsedHoursChart = document.querySelector("[data-subscription-used-hours-chart]");
  const subscriptionUsedHoursBars = subscriptionUsedHoursChart?.querySelector("[data-used-hours-chart-bars]");
  const subscriptionUsedHoursEmpty = subscriptionUsedHoursChart?.querySelector("[data-used-hours-chart-empty]");
  const subscriptionUsedHoursTitle = subscriptionUsedHoursChart?.querySelector("[data-used-hours-title]");
  const subscriptionUsedHoursDescription = subscriptionUsedHoursChart?.querySelector("[data-used-hours-description]");
  const subscriptionUsedHoursModeButtons = subscriptionUsedHoursChart
    ? Array.from(subscriptionUsedHoursChart.querySelectorAll("[data-used-hours-mode]"))
    : [];
  const subscriptionUsedHoursRefreshButton = subscriptionUsedHoursChart
    ? subscriptionUsedHoursChart.querySelector("[data-used-hours-refresh]")
    : null;
  const externalSummarySection = document.querySelector("[data-external-summary]");
  const externalMonthlyHours = externalSummarySection?.querySelector("[data-external-monthly-hours]");
  const externalTotalAed = externalSummarySection?.querySelector("[data-external-total-aed]");
  const externalCountBadge = externalSummarySection?.querySelector("[data-external-summary-count]");
  const externalCountValue = externalCountBadge?.querySelector("[data-external-count-value]");
  const externalOrdersBadge = externalSummarySection?.querySelector("[data-external-orders-count]");
  const externalOrdersValue = externalOrdersBadge?.querySelector("[data-external-orders-value]");
  const filterForm = document.querySelector("[data-client-filter-form]");
  const agreementFilterSelect = filterForm?.querySelector('[data-client-filter="agreement"]') ?? null;
  const accountFilterSelect = filterForm?.querySelector('[data-client-filter="account"]') ?? null;
  const clientFilterSelects = [agreementFilterSelect, accountFilterSelect].filter(Boolean);
  const ACCOUNT_TYPE_LABELS = {
    key: "Key Account",
    "non-key": "Non-Key Account",
  };
  const companySummarySection = document.querySelector("[data-company-summary]");
  const summaryProjectsValue = companySummarySection?.querySelector("[data-summary-projects]");
  const summaryHoursValue = companySummarySection?.querySelector("[data-summary-hours]");
  const summaryRevenueValue = companySummarySection?.querySelector("[data-summary-revenue]");
  const monthPartSelect = document.querySelector("[data-month-part-select]");
  const yearSelect = document.querySelector("[data-year-select]");
  const monthLabel = document.querySelector("[data-month-label]");

  const getCombinedYm = () => {
    const m = monthPartSelect?.value;
    const y = yearSelect?.value;
    if (!m || !y) {
      return null;
    }
    if (m.startsWith("Q")) {
      return `${y}-${m}`;
    }
    return `${y}-${m}`;
  };
  configureDailyHours({ getPeriodValue: getCombinedYm });

  const applyMonthKeyToSelects = (key) => {
    if (!key || typeof key !== "string" || !monthPartSelect || !yearSelect) {
      return;
    }
    if (key.includes("-Q")) {
      const [py, qPart] = key.split("-Q");
      yearSelect.value = py;
      monthPartSelect.value = `Q${qPart}`;
      return;
    }
    const parts = key.split("-");
    if (parts.length < 2) {
      return;
    }
    const [py, pm] = parts;
    yearSelect.value = py;
    monthPartSelect.value = String(pm).padStart(2, "0").slice(0, 2);
  };
  const refreshButton = document.querySelector("[data-creatives-refresh]");
  const creativeFilterForm = document.querySelector("[data-creative-filter-form]");
  const tabButtons = document.querySelectorAll("[data-dashboard-tab]");
  const panels = document.querySelectorAll("[data-dashboard-panel]");
  // Top cards removed
  const totalCount = null;
  const availableCount = null;
  const activeCount = null;
  const loadingOverlay = document.querySelector("[data-loading-overlay]");
  const errorBanner = document.querySelector("[data-dashboard-error]");
  const errorBannerMessage = errorBanner?.querySelector("[data-dashboard-error-message]");
  // Pool cards removed
  const poolCards = {};
  const availableHoursValue = document.querySelector("[data-total-available-hours]");
  const availableHoursBar = document.querySelector("[data-total-available-bar]");
  const externalHoursValue = document.querySelector("[data-total-external-hours]");
  const externalHoursBar = document.querySelector("[data-total-external-bar]");
  const externalHoursContainer = document.querySelector("[data-external-used-hours-container]");
  const plannedHoursValue = document.querySelector("[data-total-planned-hours]");
  const plannedHoursBar = document.querySelector("[data-total-planned-bar]");
  const loggedHoursValue = document.querySelector("[data-total-logged-hours]");
  const loggedHoursBar = document.querySelector("[data-total-logged-bar]");
  const utilizationArc = document.querySelector("[data-utilization-arc]");
  const utilizationPercent = document.querySelector("[data-utilization-percent]");
  const plannedUtilizationArc = document.querySelector("[data-planned-utilization-arc]");
  const plannedUtilizationPercent = document.querySelector("[data-planned-utilization-percent]");
  const utilizationTitle = document.querySelector("[data-utilization-title]");
  const utilizationTitleDefault =
    typeof utilizationTitle?.textContent === "string" && utilizationTitle.textContent.trim().length > 0
      ? utilizationTitle.textContent.trim()
      : "Company Wide Utilization";

  const formatPoolSelectionHeading = (labels) => {
    const unique = Array.from(
      new Set(
        labels
          .map((label) => (typeof label === "string" ? label.trim() : ""))
          .filter((label) => label.length > 0)
      )
    );
    if (unique.length === 0) {
      return utilizationTitleDefault;
    }
    if (unique.length === 1) {
      return `${unique[0]} Utilization`;
    }
    if (unique.length === 2) {
      return `${unique[0]} and ${unique[1]} Utilization`;
    }
    const last = unique[unique.length - 1];
    const initial = unique.slice(0, -1).join(", ");
    return `${initial}, and ${last} Utilization`;
  };

  // Pool filter removed - initialize empty arrays to prevent errors
  const POOL_TAG_MAP = {};
  const poolFilterGroup = null;
  const poolFilterReset = null;
  const poolFilterInputs = [];

  const hideErrorBanner = () => {
    if (!errorBanner) {
      return;
    }
    errorBanner.classList.add("hidden");
    if (errorBannerMessage) {
      errorBannerMessage.textContent = "";
    }
  };

  const showErrorBanner = (message) => {
    if (!errorBanner) {
      return;
    }
    if (errorBannerMessage) {
      errorBannerMessage.textContent =
        typeof message === "string" && message.trim().length > 0
          ? message.trim()
          : "We hit a snag loading the dashboard. Please try again.";
    }
    errorBanner.classList.remove("hidden");
  };

  const setLoadingState = (isLoading) => {
    if (refreshButton) {
      refreshButton.disabled = isLoading;
      refreshButton.setAttribute("aria-busy", isLoading ? "true" : "false");
      refreshButton.classList.toggle("opacity-50", isLoading);
    }
    if (monthPartSelect) {
      monthPartSelect.disabled = isLoading;
      monthPartSelect.setAttribute("aria-disabled", isLoading ? "true" : "false");
    }
    if (yearSelect) {
      yearSelect.disabled = isLoading;
      yearSelect.setAttribute("aria-disabled", isLoading ? "true" : "false");
    }
    clientFilterSelects.forEach((select) => {
      select.disabled = isLoading;
      if (isLoading) {
        select.setAttribute("aria-disabled", "true");
      } else {
        select.removeAttribute("aria-disabled");
      }
    });
  };

  let clientMarketData = [];
  if (clientMarketGrid?.dataset?.clientInitial) {
    try {
      const parsed = JSON.parse(clientMarketGrid.dataset.clientInitial);
      if (Array.isArray(parsed)) {
        clientMarketData = parsed;
      }
    } catch (error) {
      console.warn("Failed to parse initial client market data", error);
    }
  }
  let clientMarketAllData = clientMarketData;
  if (grid?.dataset?.clientExternalHoursAll) {
    try {
      const parsed = JSON.parse(grid.dataset.clientExternalHoursAll);
      if (Array.isArray(parsed)) {
        clientMarketAllData = parsed;
      }
    } catch (error) {
      console.warn("Failed to parse client external hours from creatives grid", error);
    }
  } else if (clientMarketGrid?.dataset?.clientAll) {
    try {
      const parsed = JSON.parse(clientMarketGrid.dataset.clientAll);
      if (Array.isArray(parsed)) {
        clientMarketAllData = parsed;
      }
    } catch (error) {
      console.warn("Failed to parse complete client market data", error);
    }
  }
  let clientSubscriptionData = [];
  if (clientSubscriptionGrid?.dataset?.clientSubscriptionInitial) {
    try {
      const parsed = JSON.parse(clientSubscriptionGrid.dataset.clientSubscriptionInitial);
      if (Array.isArray(parsed)) {
        clientSubscriptionData = parsed;
      }
    } catch (error) {
      console.warn("Failed to parse initial subscription market data", error);
    }
  }
  let clientSubscriptionAllData = clientSubscriptionData;
  if (grid?.dataset?.clientSubscriptionHoursAll) {
    try {
      const parsed = JSON.parse(grid.dataset.clientSubscriptionHoursAll);
      if (Array.isArray(parsed)) {
        clientSubscriptionAllData = parsed;
      }
    } catch (error) {
      console.warn("Failed to parse subscription used hours from creatives grid", error);
    }
  } else if (clientSubscriptionGrid?.dataset?.clientSubscriptionAll) {
    try {
      const parsed = JSON.parse(clientSubscriptionGrid.dataset.clientSubscriptionAll);
      if (Array.isArray(parsed)) {
        clientSubscriptionAllData = parsed;
      }
    } catch (error) {
      console.warn("Failed to parse complete subscription market data", error);
    }
  }


  const initialFilterOptions = filterForm?.dataset?.clientFilterOptions
    ? parseDatasetJson(filterForm.dataset.clientFilterOptions, null)
    : null;
  const initialSelectedFilters = {
    agreement_type:
      typeof filterForm?.dataset?.selectedAgreement === "string"
        ? filterForm.dataset.selectedAgreement
        : "",
    account_type:
      typeof filterForm?.dataset?.selectedAccount === "string"
        ? filterForm.dataset.selectedAccount
        : "",
  };

  const populateClientFilters = (options, selected) => {
    if (!agreementFilterSelect && !accountFilterSelect) {
      return;
    }
    const agreementValues = Array.isArray(options?.agreement_types)
      ? Array.from(
        new Set(
          options.agreement_types
            .map((value) => (typeof value === "string" ? value.trim() : ""))
            .filter((value) => value.length > 0)
        )
      )
      : [];
    const accountValues = Array.isArray(options?.account_types)
      ? Array.from(
        new Set(
          options.account_types
            .map((value) => (typeof value === "string" ? value.trim() : ""))
            .filter((value) => value.length > 0)
        )
      )
      : [];
    const desiredAgreement =
      typeof selected?.agreement_type === "string" ? selected.agreement_type : agreementFilterSelect?.value;
    const desiredAccount =
      typeof selected?.account_type === "string" ? selected.account_type : accountFilterSelect?.value;

    const rebuildSelectOptions = (select, values, defaultLabel, labelFormatter, preferredValue) => {
      if (!select) {
        return;
      }
      const fragment = document.createDocumentFragment();
      const defaultOption = document.createElement("option");
      defaultOption.value = "";
      defaultOption.textContent = defaultLabel;
      fragment.appendChild(defaultOption);
      values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = labelFormatter(value);
        fragment.appendChild(option);
      });
      select.innerHTML = "";
      select.appendChild(fragment);
      const match = values.find((value) => value === preferredValue);
      select.value = match ?? "";
      if (!match) {
        defaultOption.selected = true;
      }
    };

    rebuildSelectOptions(
      agreementFilterSelect,
      agreementValues,
      "All Agreement Types",
      (value) => value,
      desiredAgreement
    );
    rebuildSelectOptions(
      accountFilterSelect,
      accountValues,
      "All Account Types",
      (value) => ACCOUNT_TYPE_LABELS[value] ?? value,
      desiredAccount
    );
  };


  const applyClientFilters = ({ render = true } = {}) => {
    const baseSales = Array.isArray(creativeState.clientMarketsAll)
      ? creativeState.clientMarketsAll
      : [];
    const baseSubscriptions = Array.isArray(creativeState.clientSubscriptionsAll)
      ? creativeState.clientSubscriptionsAll
      : [];
    if (baseSales.length === 0 && baseSubscriptions.length === 0) {
      return;
    }
    const filters = {
      agreementType: agreementFilterSelect?.value?.trim() || "",
      accountType: accountFilterSelect?.value?.trim() || "",
    };
    const result = buildFilteredClientData(baseSales, baseSubscriptions, filters);
    creativeState.clientMarkets = result.salesMarkets;
    creativeState.clientSummary = result.salesSummary;
    creativeState.clientSubscriptions = result.subscriptionMarkets;
    creativeState.subscriptionSummary = result.subscriptionSummary;
    creativeState.subscriptionOverview = result.subscriptionSummary;
    creativeState.subscriptionTopClients = result.topClients;
    creativeState.poolExternalSummary = normalizeClientPoolSummary(result.poolSummary);
    if (render) {
      renderClientMarkets(creativeState.clientMarkets, creativeState.clientSummary);
      renderSubscriptionMarkets(
        creativeState.clientSubscriptions,
        creativeState.subscriptionSummary
      );
      renderSubscriptionTopClients(creativeState.subscriptionTopClients);
      renderPoolExternalSummary(creativeState.poolExternalSummary);
    }
  };
  const initialUsedHoursMode =
    subscriptionUsedHoursChart?.dataset?.usedHoursMode === "sold" ? "sold" : "used";
  const initialUsedHoursYear = Number(
    subscriptionUsedHoursChart?.dataset?.usedHoursYear ?? new Date().getFullYear()
  );

  const creativeState = {
    creatives: parseDatasetJson(grid?.dataset?.creativesInitial, []),
    stats: parseDatasetJson(grid?.dataset?.creativesStats, null),
    aggregates: parseDatasetJson(grid?.dataset?.creativesAggregates, null),
    pools: parseDatasetJson(grid?.dataset?.creativesPools, null),
    tasks_stats: parseDatasetJson(grid?.dataset?.creativesTasksStats, null),
    hasPreviousMonth: grid?.dataset?.creativesHasPrevious === "true",
    selectedMonthValue: grid?.dataset?.creativesSelectedMonth || "",
    clientMarkets: clientMarketData,
    clientMarketsAll: clientMarketAllData,
    clientSummary: parseDatasetJson(companySummarySection?.dataset?.summaryInitial, null),
    clientSubscriptions: clientSubscriptionData,
    clientSubscriptionsAll: clientSubscriptionAllData,
    subscriptionSummary: parseDatasetJson(
      subscriptionSection?.dataset?.clientSubscriptionSummary,
      null
    ),
    subscriptionOverview: parseDatasetJson(subscriptionSummarySection?.dataset?.subscriptionSummaryInitial, null),
    subscriptionTopClients: parseDatasetJson(
      subscriptionTopClientsSection?.dataset?.topClientsInitial,
      []
    ),
    poolExternalSummary: parseDatasetJson(
      poolSummarySection?.dataset?.poolSummaryInitial,
      null
    ),
    subscriptionUsedHoursSeries: parseDatasetJson(
      subscriptionUsedHoursChart?.dataset?.usedHoursChartInitial,
      []
    ),
    subscriptionUsedHoursYear: initialUsedHoursYear,
    clientFilterOptions: initialFilterOptions,
    monthName: monthLabel?.textContent?.trim() || "",
    sectionCollapsed: {
      external: false,
      subscription: false,
      "sales-overview": false,
      "subscription-overview": false,
      "subscription-used-hours": false,
      "subscription-top-clients": false,
      "pool-external-summary": false,
      "company-utilization": false,
      "pool-utilization": false,
      "creatives-time-cards": false,
    },
    subscriptionUsedHoursMode: initialUsedHoursMode,
    // Store unfiltered tasks_stats for client-side filtering
    // Initialize from server-side rendering if available
    allTasksStats: parseDatasetJson(grid?.dataset?.creativesTasksStats, null),
    // Store unfiltered overtime_stats for client-side filtering
    // Initialize from server-side rendering if available
    allOvertimeStats: parseDatasetJson(grid?.dataset?.creativesOvertimeStats, null),
    overtime_stats: parseDatasetJson(grid?.dataset?.creativesOvertimeStats, null),
    useBuAssignmentFilters: creativeFilterForm?.dataset?.assignmentModel === "bu",
  };

  const initialPoolSummaryFallback = normalizeClientPoolSummary(creativeState.poolExternalSummary);
  const computedInitialPoolSummary = computeClientPoolSummary(
    creativeState.clientMarkets,
    creativeState.clientSubscriptions
  );
  const hasInitialClientData =
    (Array.isArray(creativeState.clientMarkets) && creativeState.clientMarkets.length > 0) ||
    (Array.isArray(creativeState.clientSubscriptions) && creativeState.clientSubscriptions.length > 0);
  creativeState.poolExternalSummary = hasInitialClientData
    ? normalizeClientPoolSummary(computedInitialPoolSummary)
    : initialPoolSummaryFallback;

  registerPoolLabelsFromData(creativeState.pools ?? []);


  // Collapsible sections live in collapsible.js; chart resize stays here.
  const { applySectionCollapsedState, initializeCollapsibleSections } =
    createCollapsibleSections({
      creativeState,
      onSectionToggled: (key) => {
        // Resize chart if it's the monthly utilization chart
        if (key === "monthly-utilization" && monthlyUtilizationChart) {
          setTimeout(() => {
            monthlyUtilizationChart.resize();
          }, 100);
        }
      },
    });

  const renderCompanySummary = (summary) => {
    if (!companySummarySection) {
      return;
    }
    const hasSummary = summary && typeof summary === "object";
    companySummarySection.classList.toggle("hidden", !hasSummary);
    const data =
      hasSummary
        ? summary
        : {
          total_projects: 0,
          total_external_hours: 0,
          total_external_hours_display: formatHours(0),
          total_revenue_aed: 0,
          total_revenue_aed_display: formatAed(0),
        };
    if (summaryProjectsValue) {
      const projectCount = Number(data.total_projects ?? 0);
      summaryProjectsValue.textContent = Number.isFinite(projectCount)
        ? projectCount.toLocaleString()
        : "0";
    }
    if (summaryHoursValue) {
      const display =
        typeof data.total_external_hours_display === "string" &&
          data.total_external_hours_display.trim().length > 0
          ? data.total_external_hours_display.trim()
          : formatHours(data.total_external_hours ?? 0);
      summaryHoursValue.textContent = display;
    }
    if (summaryRevenueValue) {
      const display =
        typeof data.total_revenue_aed_display === "string" &&
          data.total_revenue_aed_display.trim().length > 0
          ? data.total_revenue_aed_display.trim()
          : formatAed(data.total_revenue_aed ?? 0);
      summaryRevenueValue.textContent = display;
    }
  };

  const renderSubscriptionSummary = (summary) => {
    if (!subscriptionSection && !subscriptionSummarySection) {
      return;
    }
    const fallback = {
      total_subscriptions: 0,
      total_monthly_hours: 0,
      total_monthly_hours_display: formatHours(0),
      total_revenue_aed: 0,
      total_revenue_aed_display: formatAed(0),
      total_subscription_used_hours: 0,
      total_subscription_used_hours_display: formatHours(0),
      total_parent_tasks: 0,
    };
    const source = summary && typeof summary === "object" ? summary : {};
    const data = { ...fallback, ...source };

    const monthlyDisplay =
      typeof data.total_monthly_hours_display === "string" &&
        data.total_monthly_hours_display.trim().length > 0
        ? data.total_monthly_hours_display.trim()
        : formatHours(Number(data.total_monthly_hours ?? 0));
    const usedDisplay =
      typeof data.total_subscription_used_hours_display === "string" &&
        data.total_subscription_used_hours_display.trim().length > 0
        ? data.total_subscription_used_hours_display.trim()
        : formatHours(Number(data.total_subscription_used_hours ?? 0));
    const revenueDisplay =
      typeof data.total_revenue_aed_display === "string" &&
        data.total_revenue_aed_display.trim().length > 0
        ? data.total_revenue_aed_display.trim()
        : formatAed(Number(data.total_revenue_aed ?? 0));

    if (subscriptionHoursSummary) {
      subscriptionHoursSummary.textContent = monthlyDisplay;
    }
    if (subscriptionUsedHoursSummary) {
      subscriptionUsedHoursSummary.textContent = usedDisplay;
    }
    if (subscriptionAedSummary) {
      subscriptionAedSummary.textContent = revenueDisplay;
    }
    if (subscriptionCountBadge) {
      const count = Number(data.total_subscriptions ?? 0);
      if (subscriptionCountValue) {
        subscriptionCountValue.textContent = Number.isFinite(count)
          ? count.toLocaleString()
          : "0";
      }
      subscriptionCountBadge.classList.toggle("hidden", !(Number.isFinite(count) && count > 0));
    }

    if (!subscriptionSummarySection) {
      return;
    }

    if (subscriptionSummaryCount) {
      const subscriptionTotal = Number(data.total_subscriptions ?? 0);
      subscriptionSummaryCount.textContent = Number.isFinite(subscriptionTotal)
        ? subscriptionTotal.toLocaleString()
        : "0";
    }
    if (subscriptionSummaryHours) {
      subscriptionSummaryHours.textContent = monthlyDisplay;
    }
    if (subscriptionSummaryUsedHours) {
      subscriptionSummaryUsedHours.textContent = usedDisplay;
    }
    if (subscriptionSummaryRevenue) {
      subscriptionSummaryRevenue.textContent = revenueDisplay;
    }
    if (subscriptionParentTasksBadge) {
      const parentTasksCount = Number(data.total_parent_tasks ?? 0);
      if (subscriptionParentTasksValue) {
        subscriptionParentTasksValue.textContent = Number.isFinite(parentTasksCount)
          ? parentTasksCount.toLocaleString()
          : "0";
      }
      subscriptionParentTasksBadge.classList.toggle("hidden", !(Number.isFinite(parentTasksCount) && parentTasksCount > 0));
    }
  };

  const updateUsedHoursToggleButtons = () => {
    if (!subscriptionUsedHoursModeButtons || subscriptionUsedHoursModeButtons.length === 0) {
      return;
    }
    const activeMode = creativeState.subscriptionUsedHoursMode === "sold" ? "sold" : "used";
    subscriptionUsedHoursModeButtons.forEach((button) => {
      const buttonMode = button.dataset.usedHoursMode === "sold" ? "sold" : "used";
      const isActive = buttonMode === activeMode;
      button.dataset.active = isActive ? "true" : "false";
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  };

  const renderSubscriptionUsedHoursChart = (series) => {
    if (!subscriptionUsedHoursChart || !subscriptionUsedHoursBars) {
      return;
    }
    const mode = creativeState.subscriptionUsedHoursMode === "sold" ? "sold" : "used";
    if (subscriptionUsedHoursChart) {
      subscriptionUsedHoursChart.dataset.usedHoursMode = mode;
    }
    updateUsedHoursToggleButtons();

    const normalizedSeries = Array.isArray(series)
      ? [...series].sort((a, b) => Number(a?.month ?? 0) - Number(b?.month ?? 0))
      : [];

    const yearCandidate = Number.isFinite(creativeState.subscriptionUsedHoursYear)
      ? creativeState.subscriptionUsedHoursYear
      : Number(normalizedSeries[0]?.year ?? new Date().getFullYear());
    const year = Number.isFinite(yearCandidate) ? yearCandidate : new Date().getFullYear();
    creativeState.subscriptionUsedHoursYear = year;
    if (subscriptionUsedHoursChart) {
      subscriptionUsedHoursChart.dataset.usedHoursYear = String(year);
    }

    const modeLabel = mode === "sold" ? "Sold" : "Used";
    if (subscriptionUsedHoursTitle) {
      subscriptionUsedHoursTitle.textContent = `Month by Month External ${modeLabel} Hours (${year})`;
    }
    if (subscriptionUsedHoursDescription) {
      subscriptionUsedHoursDescription.textContent =
        mode === "sold"
          ? "External plus subscription monthly hours totals for each month of this year."
          : "External plus subscription used hours totals for each month of this year.";
    }

    subscriptionUsedHoursBars.innerHTML = "";

    if (normalizedSeries.length === 0) {
      if (subscriptionUsedHoursEmpty) {
        subscriptionUsedHoursEmpty.classList.remove("hidden");
      }
      return;
    }

    if (subscriptionUsedHoursEmpty) {
      subscriptionUsedHoursEmpty.classList.add("hidden");
    }

    const maxValue = normalizedSeries.reduce((accumulator, entry) => {
      const value =
        mode === "sold"
          ? Number(entry?.total_sold_hours ?? 0)
          : Number(entry?.total_used_hours ?? 0);
      return Number.isFinite(value) && value > accumulator ? value : accumulator;
    }, 0);
    const normalizer = maxValue > 0 ? maxValue : 1;

    normalizedSeries.forEach((entry) => {
      const monthLabel =
        typeof entry?.label === "string" && entry.label.trim() ? entry.label.trim() : "";
      const totalValue =
        mode === "sold"
          ? Number(entry?.total_sold_hours ?? 0)
          : Number(entry?.total_used_hours ?? 0);
      const displayValue = (() => {
        if (mode === "sold") {
          const soldDisplay = entry?.total_sold_hours_display;
          return typeof soldDisplay === "string" && soldDisplay.trim()
            ? soldDisplay.trim()
            : formatHours(totalValue);
        }
        const usedDisplay = entry?.total_used_hours_display;
        return typeof usedDisplay === "string" && usedDisplay.trim()
          ? usedDisplay.trim()
          : formatHours(totalValue);
      })();

      const wrapper = document.createElement("div");
      wrapper.className = "flex h-full min-w-[3rem] flex-col items-center gap-2";
      wrapper.style.justifyContent = "flex-end";
      wrapper.style.flex = "1 0 3rem";
      wrapper.setAttribute("role", "presentation");

      const valueLabel = document.createElement("span");
      valueLabel.className = "text-xs font-semibold text-slate-600";
      valueLabel.textContent = displayValue;
      wrapper.appendChild(valueLabel);

      const bar = document.createElement("div");
      bar.className = "w-8 sm:w-10 rounded-t-lg bg-sky-400/80 transition-all";
      const heightPercent = totalValue > 0 ? Math.max((totalValue / normalizer) * 100, 6) : 0;
      bar.style.height = `${heightPercent}%`;
      bar.style.minHeight = "4px";
      bar.title = monthLabel
        ? `${monthLabel}: ${displayValue} (${modeLabel})`
        : `${displayValue} (${modeLabel})`;
      wrapper.appendChild(bar);

      const label = document.createElement("span");
      label.className = "text-xs font-medium text-slate-600";
      label.textContent = monthLabel;
      wrapper.appendChild(label);

      subscriptionUsedHoursBars.appendChild(wrapper);
    });
  };

  subscriptionUsedHoursModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setSubscriptionUsedHoursMode(button.dataset.usedHoursMode);
    });
  });

  // Refresh button handler
  if (subscriptionUsedHoursRefreshButton) {
    subscriptionUsedHoursRefreshButton.addEventListener("click", async () => {
      if (subscriptionUsedHoursRefreshButton.disabled) {
        return;
      }

      const year = creativeState.subscriptionUsedHoursYear || new Date().getFullYear();
      const refreshIcon = subscriptionUsedHoursRefreshButton.querySelector(".material-symbols-rounded");

      // Disable button and show loading state
      subscriptionUsedHoursRefreshButton.disabled = true;
      if (refreshIcon) {
        refreshIcon.classList.add("animate-spin");
      }

      // Client dashboard refresh functionality removed
      console.warn("Client dashboard refresh functionality has been removed");
      subscriptionUsedHoursRefreshButton.disabled = false;
      if (refreshIcon) {
        refreshIcon.classList.remove("animate-spin");
      }
    });
  }

  const setSubscriptionUsedHoursMode = (mode, options = {}) => {
    const normalized = mode === "sold" ? "sold" : "used";
    const previous = creativeState.subscriptionUsedHoursMode;
    const rerender = options.rerender !== false || previous !== normalized;
    creativeState.subscriptionUsedHoursMode = normalized;
    if (subscriptionUsedHoursChart) {
      subscriptionUsedHoursChart.dataset.usedHoursMode = normalized;
    }
    updateUsedHoursToggleButtons();
    if (rerender) {
      renderSubscriptionUsedHoursChart(creativeState.subscriptionUsedHoursSeries);
    }
  };

  const buildGauge = (ratio, options = {}) => {
    const clamped = Math.max(0, Math.min(1, Number(ratio) || 0));
    const percentage = Math.round(clamped * 100);
    const container = document.createElement("div");
    container.className = "relative flex h-20 w-20 items-center justify-center";

    const track = document.createElement("div");
    track.className = "absolute inset-0 rounded-full bg-slate-200";
    container.appendChild(track);

    const fill = document.createElement("div");
    fill.className = "absolute inset-0 rounded-full";
    fill.style.background = `conic-gradient(#38bdf8 ${percentage}%, #e2e8f0 ${percentage}% 100%)`;
    container.appendChild(fill);

    const inner = document.createElement("div");
    inner.className = "absolute inset-3 flex items-center justify-center rounded-full bg-white text-xs font-semibold text-sky-600";
    inner.textContent = `${percentage}%`;
    container.appendChild(inner);

    return container;
  };

  const renderPoolExternalSummary = (summary) => {
    if (!poolSummarySection || !poolSummaryBody) {
      return;
    }
    poolSummaryBody.innerHTML = "";

    const normalizedSummary = normalizeClientPoolSummary(summary);
    const pools = Array.isArray(normalizedSummary?.pools) ? normalizedSummary.pools : [];
    if (pools.length === 0) {
      if (poolSummaryEmpty) {
        poolSummaryEmpty.classList.remove("hidden");
      }
      return;
    }

    if (poolSummaryEmpty) {
      poolSummaryEmpty.classList.add("hidden");
    }

    pools.forEach((pool) => {
      const card = document.createElement("article");
      card.className = "flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";

      const title = document.createElement("h3");
      title.className = "text-sm font-semibold uppercase tracking-wide text-slate-600";
      title.textContent = pool?.label ?? "Pool";
      card.appendChild(title);

      const metrics = pool?.metrics ?? {};
      const metricOrder = [
        { key: "projects", label: "No. Projects" },
        { key: "used_hours", label: "External Used Hours" },
        { key: "revenue", label: "Total Revenue" },
      ];

      metricOrder.forEach(({ key, label }) => {
        const metric = metrics[key];
        if (!metric) {
          return;
        }
        const wrapper = document.createElement("div");
        wrapper.className = "flex items-center gap-4 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3";

        const gauge = buildGauge(metric?.ratio ?? 0);
        wrapper.appendChild(gauge);

        const info = document.createElement("div");
        info.className = "flex flex-col";

        const metricLabel = document.createElement("span");
        metricLabel.className = "text-xs font-semibold uppercase tracking-wide text-slate-500";
        metricLabel.textContent = label;
        info.appendChild(metricLabel);

        const value = document.createElement("span");
        value.className = "text-sm font-semibold text-slate-900";
        value.textContent = metric?.display ?? "-";
        info.appendChild(value);

        const share = document.createElement("span");
        share.className = "text-xs text-slate-500";
        share.textContent = `of total ${metric?.total_display ?? "-"}`;
        info.appendChild(share);

        wrapper.appendChild(info);
        card.appendChild(wrapper);
      });

      poolSummaryBody.appendChild(card);
    });
  };

  const renderSubscriptionTopClients = (clients) => {
    if (!subscriptionTopClientsSection || !subscriptionTopClientsBody) {
      return;
    }
    const entries = Array.isArray(clients) ? clients.slice(0, 5) : [];
    subscriptionTopClientsBody.innerHTML = "";

    if (entries.length === 0) {
      if (subscriptionTopClientsEmpty) {
        subscriptionTopClientsEmpty.classList.remove("hidden");
      }
      return;
    }

    if (subscriptionTopClientsEmpty) {
      subscriptionTopClientsEmpty.classList.add("hidden");
    }

    entries.forEach((client) => {
      const row = document.createElement("tr");

      const nameCell = document.createElement("td");
      nameCell.className = "px-4 py-3";
      const nameWrapper = document.createElement("div");
      nameWrapper.className = "flex flex-col";
      const clientName = document.createElement("span");
      clientName.className = "font-semibold text-slate-900";
      const name =
        typeof client?.client_name === "string" && client.client_name.trim()
          ? client.client_name.trim()
          : "Unnamed Client";
      clientName.textContent = name;
      nameWrapper.appendChild(clientName);
      const market =
        typeof client?.market === "string" && client.market.trim() ? client.market.trim() : "";
      if (market) {
        const marketLabel = document.createElement("span");
        marketLabel.className = "text-xs font-medium text-slate-500";
        marketLabel.textContent = market;
        nameWrapper.appendChild(marketLabel);
      }
      nameCell.appendChild(nameWrapper);

      const requestsCell = document.createElement("td");
      requestsCell.className = "px-4 py-3 text-center text-sm font-semibold text-slate-700";
      const requestCount = Number(client?.request_count ?? 0);
      requestsCell.textContent = Number.isFinite(requestCount)
        ? requestCount.toLocaleString()
        : "0";

      const revenueCell = document.createElement("td");
      revenueCell.className = "px-4 py-3 text-right text-sm font-semibold text-emerald-600";
      const revenueDisplay =
        typeof client?.total_revenue_aed_display === "string" &&
          client.total_revenue_aed_display.trim()
          ? client.total_revenue_aed_display.trim()
          : formatAed(client?.total_revenue_aed ?? 0);
      revenueCell.textContent = revenueDisplay;

      row.appendChild(nameCell);
      row.appendChild(requestsCell);
      row.appendChild(revenueCell);
      subscriptionTopClientsBody.appendChild(row);
    });
  };

  const renderExternalSummary = (summary) => {
    if (!externalSummarySection) {
      return;
    }
    const data =
      summary && typeof summary === "object"
        ? summary
        : {
          total_external_hours: 0,
          total_external_hours_display: formatHours(0),
          total_revenue_aed: 0,
          total_revenue_aed_display: formatAed(0),
          total_invoices: 0,
          total_orders: 0,
        };
    if (externalMonthlyHours) {
      const display =
        typeof data.total_external_hours_display === "string" &&
          data.total_external_hours_display.trim().length > 0
          ? data.total_external_hours_display.trim()
          : formatHours(data.total_external_hours ?? 0);
      externalMonthlyHours.textContent = display;
    }
    if (externalTotalAed) {
      const display =
        typeof data.total_revenue_aed_display === "string" &&
          data.total_revenue_aed_display.trim().length > 0
          ? data.total_revenue_aed_display.trim()
          : formatAed(data.total_revenue_aed ?? 0);
      externalTotalAed.textContent = display;
    }
    if (externalCountBadge) {
      const count = Number(data.total_invoices ?? 0);
      if (externalCountValue) {
        externalCountValue.textContent = Number.isFinite(count)
          ? count.toLocaleString()
          : "0";
      }
      externalCountBadge.classList.toggle("hidden", !(Number.isFinite(count) && count > 0));
    }
    if (externalOrdersBadge) {
      const ordersCount = Number(data.total_orders ?? 0);
      if (externalOrdersValue) {
        externalOrdersValue.textContent = Number.isFinite(ordersCount)
          ? ordersCount.toLocaleString()
          : "0";
      }
      externalOrdersBadge.classList.toggle("hidden", !(Number.isFinite(ordersCount) && ordersCount > 0));
    }
  };

  const updateMonthLabel = (monthName) => {
    if (monthLabel && monthName) {
      monthLabel.textContent = monthName;
    }
  };


  const updateStats = (stats, creatives) => {
    // Top cards removed, no stats to update
    /*
    const fallback = computeStats(creatives);
    const totals = {
      // Total should ALWAYS come from backend stats (all creatives from Odoo)
      // This ensures filters don't affect the total count
      total: stats?.total ?? fallback.total,
      // Available and active can use fallback when filters are active
      available: stats?.available ?? fallback.available,
      active: stats?.active ?? fallback.active,
    };
  
    if (totalCount) {
      totalCount.textContent = totals.total;
    }
    if (availableCount) {
      availableCount.textContent = totals.available;
    }
    if (activeCount) {
      activeCount.textContent = totals.active;
    }
    */
  };


  /** Keep New Joiners / Offboarding summary numbers equal to visible <li> rows in each block. */
  const syncHeadcountDetailsBadgesFromLists = () => {
    document.querySelectorAll("[data-headcount-new-joiners-list]").forEach((ul) => {
      const details = ul.closest("details");
      const badge = details?.querySelector("[data-headcount-new-joiners]");
      if (badge) {
        badge.textContent = String(ul.querySelectorAll("li").length);
      }
    });
    document.querySelectorAll("[data-headcount-offboarded-list]").forEach((ul) => {
      const details = ul.closest("details");
      const badge = details?.querySelector("[data-headcount-offboarded]");
      if (badge) {
        badge.textContent = String(ul.querySelectorAll("li").length);
      }
    });
  };

  /** Agreement column for Client Breakdown table (matches Tasks Breakdown categories). */
  const formatClientAgreementType = (task) => {
    const tokens = [];
    const addTokens = (raw) => {
      if (raw == null) return;
      if (typeof raw === "string") {
        raw.split(/[,/&|]+/).forEach((p) => {
          const s = p.trim();
          if (s) tokens.push(s);
        });
      } else if (Array.isArray(raw)) {
        raw.forEach(addTokens);
      }
    };
    addTokens(task?.agreement_type);
    addTokens(task?.tags);
    const normalized = tokens.map((t) => t.toLowerCase());
    if (normalized.some((t) => t.includes("retainer") || t.includes("subscription") || t.includes("subscr"))) {
      return "Retainer";
    }
    if (normalized.some((t) => t.includes("framework"))) {
      return "Framework";
    }
    if (normalized.some((t) => t.includes("ad-hoc") || t.includes("adhoc") || t.includes("ad hoc"))) {
      return "Ad-hoc";
    }
    const raw = typeof task?.agreement_type === "string" ? task.agreement_type.trim() : "";
    return raw || "Other";
  };

  const renderClientBreakdownTable = (tasksStats) => {
    const tbody = document.querySelector("[data-client-breakdown-tbody]");
    const emptyEl = document.querySelector("[data-client-breakdown-empty]");
    const countEl = document.querySelector("[data-client-breakdown-count]");
    if (!tbody) {
      return;
    }
    const tasks = Array.isArray(tasksStats?.tasks) ? tasksStats.tasks : [];
    const sorted = tasks
      .slice()
      .sort((a, b) =>
        String(a?.project_name || "").localeCompare(String(b?.project_name || ""), undefined, {
          sensitivity: "base",
        })
      );
    tbody.innerHTML = "";
    sorted.forEach((task) => {
      const tr = document.createElement("tr");
      tr.className = "bg-white";
      const nameTd = document.createElement("td");
      nameTd.className = "border border-slate-200 px-3 py-2";
      nameTd.textContent = task?.project_name != null && String(task.project_name).trim() !== ""
        ? String(task.project_name)
        : "—";
      const agreeTd = document.createElement("td");
      agreeTd.className = "border border-slate-200 px-3 py-2";
      agreeTd.textContent = formatClientAgreementType(task);
      tr.appendChild(nameTd);
      tr.appendChild(agreeTd);
      tbody.appendChild(tr);
    });
    const n = typeof tasksStats?.total === "number" ? tasksStats.total : sorted.length;
    if (countEl) {
      countEl.textContent = String(n);
    }
    if (emptyEl) {
      emptyEl.classList.toggle("hidden", sorted.length > 0);
    }
  };

  // Update headcount metrics
  const updateTasks = (tasksStats) => {
    if (!tasksStats) return;

    const totalEl = document.querySelector("[data-tasks-total]");
    const totalTasksEl = document.querySelector("[data-total-tasks-value]");

    const adhocTasksEl = document.querySelector("[data-tasks-adhoc-tasks]");
    const frameworkTasksEl = document.querySelector("[data-tasks-framework-tasks]");
    const retainerTasksEl = document.querySelector("[data-tasks-retainer-tasks]");
    const avgPerCreatorEl = document.querySelector("[data-tasks-avg-per-creator]");
    const comparisonEl = document.querySelector("[data-tasks-comparison]");
    const tasksComparisonEl = document.querySelector("[data-total-tasks-comparison]");
    const tasksContainer = totalEl?.closest("[data-tasks-container]");

    if (totalEl) {
      totalEl.textContent = tasksStats.total || 0;
      const projectIds = Array.isArray(tasksStats.project_ids) ? tasksStats.project_ids : [];
      const tooltip = projectIds.length > 0 ? `Projects: ${projectIds.join(", ")}` : "";
      if (tooltip) {
        totalEl.setAttribute("title", tooltip);
        tasksContainer?.setAttribute("title", tooltip);
      } else {
        totalEl.removeAttribute("title");
        tasksContainer?.removeAttribute("title");
      }
    }

    if (totalTasksEl) {
      totalTasksEl.textContent = tasksStats.total_tasks || 0;
      // Update tooltip with parent task names
      const parentTaskNames = tasksStats.parent_task_names || [];
      const tooltipText = parentTaskNames.length > 0
        ? parentTaskNames.join(', ')
        : 'No parent tasks';
      totalTasksEl.setAttribute('title', tooltipText);
    }

    if (adhocTasksEl) {
      adhocTasksEl.textContent = tasksStats.adhoc_tasks || 0;
    }

    if (frameworkTasksEl) {
      frameworkTasksEl.textContent = tasksStats.framework_tasks || 0;
    }

    if (retainerTasksEl) {
      retainerTasksEl.textContent = tasksStats.retainer_tasks || 0;
    }

    if (avgPerCreatorEl) {
      avgPerCreatorEl.textContent = (tasksStats.average_per_creator ?? 0).toFixed(2);
    }

    const avgTasksPerCreatorEl = document.querySelector("[data-tasks-avg-tasks-per-creator]");
    if (avgTasksPerCreatorEl) {
      avgTasksPerCreatorEl.textContent = (tasksStats.average_tasks_per_creator ?? 0).toFixed(2);
    }

    if (comparisonEl) {
      const comparison = tasksStats.comparison;
      if (comparison) {
        comparisonEl.classList.remove("hidden");
        const trend = comparison.trend || "flat";
        const changePercent = comparison.change_percentage ?? 0;
        comparisonEl.className = `flex items-center gap-1 ${trend === "up" ? "text-emerald-600" : "text-rose-600"}`;
        const textEl = comparisonEl.querySelector("span:first-child");
        const iconEl = comparisonEl.querySelector(".material-symbols-rounded");
        if (textEl) {
          textEl.textContent = `${changePercent.toFixed(1)}%`;
        }
        if (iconEl) {
          iconEl.textContent = trend === "up" ? "trending_up" : "trending_down";
        }
      } else {
        comparisonEl.classList.add("hidden");
      }
    }

    if (tasksComparisonEl) {
      const comparison = tasksStats.tasks_comparison;
      if (comparison) {
        tasksComparisonEl.classList.remove("hidden");
        const trend = comparison.trend || "flat";
        const changePercent = comparison.change_percentage ?? 0;
        tasksComparisonEl.className = `flex items-center gap-1 ${trend === "up" ? "text-emerald-600" : "text-rose-600"}`;
        const textEl = tasksComparisonEl.querySelector("span:first-child");
        const iconEl = tasksComparisonEl.querySelector(".material-symbols-rounded");
        if (textEl) {
          textEl.textContent = `${changePercent.toFixed(1)}%`;
        }
        if (iconEl) {
          iconEl.textContent = trend === "up" ? "trending_up" : "trending_down";
        }
      } else {
        tasksComparisonEl.classList.add("hidden");
      }
    }

    renderClientBreakdownTable(tasksStats);
  };

  const updateOvertime = (overtimeStats) => {
    if (!overtimeStats) return;

    const totalEl = document.querySelector("[data-overtime-total]");
    const projectsContainer = document.querySelector("[data-overtime-projects]");

    if (totalEl) {
      totalEl.textContent = overtimeStats.total_hours_display ?? "0h";
    }

    if (projectsContainer) {
      const topProjects = overtimeStats.top_projects ?? [];
      if (topProjects.length === 0) {
        projectsContainer.innerHTML = '<div class="text-xs text-slate-500 py-2">No overtime recorded</div>';
      } else {
        projectsContainer.innerHTML = topProjects.slice(0, 5).map((project, index) => {
          const projectName = project.project_name ?? "Unassigned Project";
          const hoursDisplay = project.hours_display ?? "0h";
          const contributors = project.contributors && project.contributors.length > 0 ? project.contributors.join(", ") : "";
          const tooltipAttr = contributors ? `title="${contributors}"` : "";
          const cursorClass = contributors ? "cursor-help relative" : "";

          return `
            <div class="flex items-center justify-between gap-2 px-2 py-1 rounded-lg bg-slate-50 ${cursorClass}" ${tooltipAttr}>
              <span class="text-xs font-semibold text-slate-700 truncate flex-1 text-left">${projectName}</span>
              <span class="text-xs font-bold text-slate-900 whitespace-nowrap" data-overtime-project-hours="${index}">${hoursDisplay}</span>
            </div>
          `;
        }).join("");
      }
    }
  };

  const updateHeadcount = (headcount) => {
    if (!headcount) return;

    const countEl = document.querySelector("[data-headcount-count]");
    const newJoinersEl = document.querySelector("[data-headcount-new-joiners]");
    const offboardedEl = document.querySelector("[data-headcount-offboarded]");

    if (countEl) {
      const n = headcount.employee_count;
      countEl.textContent =
        typeof n === "number" && Number.isFinite(n)
          ? String(n)
          : String(headcount.total ?? 0);
    }

    const newJoinersList = document.querySelector("[data-headcount-new-joiners-list]");
    const newJoinersEmpty = document.querySelector("[data-headcount-new-joiners-empty]");
    if (newJoinersList && headcount.new_joiners_names !== undefined) {
      const names = Array.isArray(headcount.new_joiners_names) ? headcount.new_joiners_names : [];
      newJoinersList.innerHTML = "";
      names.forEach((raw) => {
        const name = raw == null ? "" : String(raw).trim();
        if (!name) {
          return;
        }
        const li = document.createElement("li");
        li.textContent = name;
        newJoinersList.appendChild(li);
      });
      if (newJoinersEmpty) {
        newJoinersEmpty.classList.toggle("hidden", newJoinersList.children.length > 0);
      }
      if (newJoinersEl) {
        newJoinersEl.textContent = String(newJoinersList.children.length);
      }
    } else if (newJoinersEl && headcount.new_joiners_count !== undefined) {
      newJoinersEl.textContent = String(headcount.new_joiners_count ?? 0);
    }

    const offboardedList = document.querySelector("[data-headcount-offboarded-list]");
    const offboardedEmpty = document.querySelector("[data-headcount-offboarded-empty]");
    if (offboardedList && headcount.offboarded_names !== undefined) {
      const names = Array.isArray(headcount.offboarded_names) ? headcount.offboarded_names : [];
      offboardedList.innerHTML = "";
      names.forEach((raw) => {
        const name = raw == null ? "" : String(raw).trim();
        if (!name) {
          return;
        }
        const li = document.createElement("li");
        li.textContent = name;
        offboardedList.appendChild(li);
      });
      if (offboardedEmpty) {
        offboardedEmpty.classList.toggle("hidden", offboardedList.children.length > 0);
      }
      if (offboardedEl) {
        offboardedEl.textContent = String(offboardedList.children.length);
      }
    } else if (offboardedEl && headcount.offboarded_count !== undefined) {
      offboardedEl.textContent = String(headcount.offboarded_count ?? 0);
    }

    syncHeadcountDetailsBadgesFromLists();
  };

  // Initialize tooltip for new joiners
  const initNewJoinersTooltip = () => {
    // Custom tooltip disabled; rely on native title attribute
  };

  // Monthly Utilization Chart
  let monthlyUtilizationChart = null;

  const initMonthlyUtilizationChart = () => {
    const canvas = document.getElementById("monthlyUtilizationChart");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (monthlyUtilizationChart) {
      monthlyUtilizationChart.destroy();
    }

    monthlyUtilizationChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: [],
        datasets: [{
          label: "Logged utilization %",
          data: [],
          backgroundColor: "rgba(14, 165, 233, 0.8)",
          borderColor: "rgba(14, 165, 233, 1)",
          borderWidth: 1,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          datalabels: false,  // Disable datalabels plugin
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: function (context) {
                return `Logged utilization: ${context.parsed.y.toFixed(1)}%`;
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            ticks: {
              callback: function (value) {
                return value + "%";
              }
            },
            title: {
              display: false
            }
          },
          x: {
            title: {
              display: false
            }
          }
        }
      }
    });

    // Load initial data
    updateMonthlyUtilizationChart();
  };

  const updateMonthlyUtilizationChart = () => {
    if (!monthlyUtilizationChart) return;

    const monthlyData = window.monthlyUtilizationData || [];

    const useBuModel = assignmentFilterModelIsBu();
    const selectedMarkets = getSelectedMarkets();
    const selectedPools = getSelectedPools();
    const selectedBu = getSelectedBusinessUnits();
    const selectedSbu = getSelectedSubBusinessUnits();
    const selectedPod = getSelectedPods();
    const chartYear = parseInt(yearSelect?.value || "", 10);

    // Process and aggregate data with filtering
    const chartData = monthlyData.map((monthData) => {
      const creatives = monthData.creatives || [];
      const monthNum = monthData.month;
      const useBuForChartMonth =
        useBuModel && monthAnchorUsesBuAssignmentModel(chartYear, monthNum);

      const filteredCreatives = filterCreativesClientSide(
        creatives,
        selectedMarkets,
        selectedPools,
        selectedBu,
        selectedSbu,
        selectedPod,
        useBuForChartMonth
      );

      // Aggregate available and logged hours from ALL filtered creatives
      const totalAvailable = filteredCreatives.reduce((sum, c) => {
        const available = Number(c.available_hours) || 0;
        return sum + available;
      }, 0);

      const totalLogged = filteredCreatives.reduce((sum, c) => {
        const logged = Number(c.logged_hours) || 0;
        return sum + logged;
      }, 0);

      // Calculate utilization percentage
      const utilizationPercent = totalAvailable > 0
        ? (totalLogged / totalAvailable) * 100
        : 0;

      return {
        label: monthData.label,
        utilization: utilizationPercent
      };
    });

    // Update chart
    monthlyUtilizationChart.data.labels = chartData.map(d => d.label);
    monthlyUtilizationChart.data.datasets[0].data = chartData.map(d => d.utilization);
    monthlyUtilizationChart.update();
  };

  // === Refresh Monthly Utilization Data Functionality ===
  const parseJsonOrNull = (text) => {
    if (!text || typeof text !== 'string') return null;
    try {
      return JSON.parse(text);
    } catch {
      return null;
    }
  };

  const refreshMonthlyUtilizationData = async () => {
    const refreshButton = document.querySelector('[data-refresh-monthly-utilization]');
    if (!refreshButton) return;

    const refreshIcon = refreshButton.querySelector('.material-symbols-rounded');

    // Disable button and show loading state
    refreshButton.disabled = true;
    if (refreshIcon) {
      refreshIcon.classList.add('animate-spin');
    }

    try {
      const response = await fetch('/api/utilization/refresh-monthly', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const contentType = response.headers.get('content-type') || '';
      const text = await response.text();

      if (!response.ok) {
        const errorData = parseJsonOrNull(text);
        const message = errorData?.message || (contentType.includes('application/json')
          ? 'Failed to refresh data'
          : 'The server returned an error. Please try again later.');
        throw new Error(message);
      }

      const data = parseJsonOrNull(text);
      if (!data) {
        throw new Error('Invalid response from server. Please try again.');
      }

      if (data.monthly_utilization_series) {
        // Update global data
        window.monthlyUtilizationData = data.monthly_utilization_series;

        // Update chart with refreshed data
        updateMonthlyUtilizationChart();

        // Show success feedback
        console.log('Utilization data refreshed successfully:', data.message);
      }
    } catch (error) {
      console.error('Failed to refresh utilization data:', error);
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
  const refreshUtilizationButton = document.querySelector('[data-refresh-monthly-utilization]');
  if (refreshUtilizationButton) {
    refreshUtilizationButton.addEventListener('click', refreshMonthlyUtilizationData);
  }

  const updateAggregates = (aggregates, creatives) => {
    const fallback = computeAggregates(creatives);
    const totals = {
      planned: aggregates?.planned ?? fallback.planned ?? 0,
      logged: aggregates?.logged ?? fallback.logged ?? 0,
      available: aggregates?.available ?? fallback.available ?? 0,
    };

    const selectedMarkets = getSelectedMarkets();
    const selectedPools = getSelectedPools();
    const useBuForExternal = assignmentFilterModelIsBu();
    const buAssignmentFiltersActive =
      useBuForExternal &&
      (getSelectedBusinessUnits().length > 0 ||
        getSelectedSubBusinessUnits().length > 0 ||
        getSelectedPods().length > 0);
    const externalHoursData = calculateExternalHours(
      creativeState.clientMarketsAll || [],
      creativeState.clientSubscriptionsAll || [],
      selectedMarkets,
      selectedPools,
      useBuForExternal ? { useBuModel: true, assignmentFiltersActive: buAssignmentFiltersActive } : null
    );

    // Update max to include external hours if it should be shown
    const max = Math.max(
      aggregates?.max ?? fallback.max ?? 0,
      externalHoursData.shouldShow ? externalHoursData.hours : 0
    );

    const display = aggregates?.display ?? {
      planned: formatHours(totals.planned),
      logged: formatHours(totals.logged),
      available: formatHours(totals.available),
    };

    // Show/hide external hours container based on filter state
    if (externalHoursContainer) {
      externalHoursContainer.classList.toggle("hidden", !externalHoursData.shouldShow);
      externalHoursContainer.classList.toggle("flex", !!externalHoursData.shouldShow);
    }

    const externalHoursCollapsibleSection = document.querySelector(
      '[data-collapsible-section="external-hours"]'
    );
    if (externalHoursCollapsibleSection) {
      if (useBuForExternal) {
        externalHoursCollapsibleSection.classList.toggle("hidden", buAssignmentFiltersActive);
      } else {
        externalHoursCollapsibleSection.classList.remove("hidden");
      }
    }

    const entries = [
      {
        value: totals.available,
        labelEl: availableHoursValue,
        barEl: availableHoursBar,
        display: display.available,
      },
      {
        value: externalHoursData.hours,
        labelEl: externalHoursValue,
        barEl: externalHoursBar,
        display: useBuForExternal
          ? formatHoursWhole(externalHoursData.hours)
          : formatHours(externalHoursData.hours),
        shouldShow: externalHoursData.shouldShow,
      },
      {
        value: totals.planned,
        labelEl: plannedHoursValue,
        barEl: plannedHoursBar,
        display: display.planned,
      },
      {
        value: totals.logged,
        labelEl: loggedHoursValue,
        barEl: loggedHoursBar,
        display: display.logged,
      },
    ];

    entries.forEach((entry) => {
      // Skip external hours entry if it shouldn't be shown
      if (entry.shouldShow === false) {
        return;
      }

      if (entry.labelEl && typeof entry.display === "string") {
        entry.labelEl.textContent = entry.display;
      }
      if (entry.barEl) {
        const baseHeight = max > 0 ? (entry.value / max) * 100 : 0;
        const height =
          entry.value > 0
            ? Math.min(100, Math.max(baseHeight, 10))
            : 0;
        entry.barEl.style.height = `${height}%`;
      }
    });

    // Update new metrics list (Available, Booked, Logged) with raw numbers
    const availableHoursEl = document.querySelector("[data-metrics-available-hours]");
    if (availableHoursEl) {
      availableHoursEl.textContent = Math.round(totals.available);
    }

    const plannedHoursEl = document.querySelector("[data-metrics-planned-hours]");
    if (plannedHoursEl) {
      plannedHoursEl.textContent = Math.round(totals.planned);
    }

    const loggedHoursEl = document.querySelector("[data-metrics-logged-hours]");
    if (loggedHoursEl) {
      loggedHoursEl.textContent = Math.round(totals.logged);
    }

    // Update headcount data if available
    // REMOVED: This was overwriting the correct headcount value with aggregates.headcount (filtered)
    // Headcount is now properly handled in renderCreatives() with preservation of unfiltered total
    // updateHeadcount(aggregates?.headcount);

    // Update tasks data if available
    updateTasks(aggregates?.tasks_stats);

    // Update overtime data if available
    updateOvertime(aggregates?.overtime_stats);

    // Update comparison indicators
    const updateComparisonIndicator = (selector, change) => {
      const indicator = document.querySelector(selector);
      if (!indicator) return;

      if (change === null || change === undefined) {
        indicator.classList.add("hidden");
        return;
      }

      indicator.classList.remove("hidden");
      const isPositive = change >= 0;
      indicator.className = `flex items-center gap-1 ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`;

      const icon = indicator.querySelector(".material-symbols-rounded");
      const percent = indicator.querySelector("span:last-child");

      if (icon) {
        icon.textContent = isPositive ? "trending_up" : "trending_down";
      }
      if (percent) {
        percent.textContent = `${Math.abs(change).toFixed(1)}%`;
      }
    };

    const comparison = aggregates?.comparison || null;
    if (comparison) {
      updateComparisonIndicator("[data-available-change]", comparison.available?.change);
      updateComparisonIndicator("[data-planned-change]", comparison.planned?.change);
      updateComparisonIndicator("[data-logged-change]", comparison.logged?.change);

      // Update utilization and booking capacity comparison
      const utilizationChangeEl = document.querySelector("[data-utilization-change]");
      if (utilizationChangeEl) {
        const hasUtilChange = comparison.utilization?.change !== null && comparison.utilization?.change !== undefined;
        const utilChange = hasUtilChange ? comparison.utilization.change : 0;
        const isPositive = utilChange >= 0;
        const colorClass = hasUtilChange ? (isPositive ? 'text-emerald-600' : 'text-rose-600') : 'text-slate-500';
        utilizationChangeEl.className = `mt-4 flex items-center gap-2 ${colorClass}`;
        utilizationChangeEl.classList.remove("hidden");
        const icon = utilizationChangeEl.querySelector(".material-symbols-rounded");
        const text = utilizationChangeEl.querySelector("span:last-child");
        if (icon) {
          icon.textContent = hasUtilChange ? (isPositive ? "trending_up" : "trending_down") : "trending_flat";
          icon.className = "material-symbols-rounded gauge-trend-icon";
        }
        if (text) text.textContent = `${Math.abs(utilChange).toFixed(1)}% vs last month`;
      }

      const bookingChangeEl = document.querySelector("[data-booking-change]");
      if (bookingChangeEl) {
        const hasBookingChange = comparison.booking_capacity?.change !== null && comparison.booking_capacity?.change !== undefined;
        const bookingChange = hasBookingChange ? comparison.booking_capacity.change : 0;
        const isPositive = bookingChange >= 0;
        const colorClass = hasBookingChange ? (isPositive ? 'text-emerald-600' : 'text-rose-600') : 'text-slate-500';
        bookingChangeEl.className = `mt-2 flex items-center gap-2 ${colorClass}`;
        bookingChangeEl.classList.remove("hidden");
        const icon = bookingChangeEl.querySelector(".material-symbols-rounded");
        const text = bookingChangeEl.querySelector("span:last-child");
        if (icon) {
          icon.textContent = hasBookingChange ? (isPositive ? "trending_up" : "trending_down") : "trending_flat";
          icon.className = "material-symbols-rounded gauge-trend-icon";
        }
        if (text) text.textContent = `${Math.abs(bookingChange).toFixed(1)}% vs last month`;
      }
    } else {
      // Hide all comparison indicators if no comparison data
      updateComparisonIndicator("[data-available-change]", null);
      updateComparisonIndicator("[data-planned-change]", null);
      updateComparisonIndicator("[data-logged-change]", null);
      const utilizationChangeEl = document.querySelector("[data-utilization-change]");
      if (utilizationChangeEl) {
        utilizationChangeEl.className = "mt-4 flex items-center gap-2 text-slate-500";
        utilizationChangeEl.classList.remove("hidden");
        const icon = utilizationChangeEl.querySelector(".material-symbols-rounded");
        const text = utilizationChangeEl.querySelector("span:last-child");
        if (icon) {
          icon.textContent = "trending_flat";
          icon.className = "material-symbols-rounded gauge-trend-icon";
        }
        if (text) text.textContent = "0.0% vs last month";
      }
      const bookingChangeEl = document.querySelector("[data-booking-change]");
      if (bookingChangeEl) {
        bookingChangeEl.className = "mt-2 flex items-center gap-2 text-slate-500";
        bookingChangeEl.classList.remove("hidden");
        const icon = bookingChangeEl.querySelector(".material-symbols-rounded");
        const text = bookingChangeEl.querySelector("span:last-child");
        if (icon) {
          icon.textContent = "trending_flat";
          icon.className = "material-symbols-rounded gauge-trend-icon";
        }
        if (text) text.textContent = "0.0% vs last month";
      }
    }

    const utilization =
      totals.available > 0 ? Math.min(100, (totals.logged / totals.available) * 100) : 0;
    const plannedUtilization =
      totals.available > 0 ? Math.min(100, (totals.planned / totals.available) * 100) : 0;
    const circumference = 2 * Math.PI * 45;
    if (utilizationArc) {
      const offset = circumference - (circumference * utilization) / 100;
      utilizationArc.style.strokeDasharray = `${circumference}`;
      utilizationArc.style.strokeDashoffset = `${offset}`;
    }
    if (utilizationPercent) {
      utilizationPercent.textContent = `${utilization.toFixed(1)}%`;
    }
    if (plannedUtilizationArc) {
      const offset = circumference - (circumference * plannedUtilization) / 100;
      plannedUtilizationArc.style.strokeDasharray = `${circumference}`;
      plannedUtilizationArc.style.strokeDashoffset = `${offset}`;
    }
    if (plannedUtilizationPercent) {
      plannedUtilizationPercent.textContent = `${plannedUtilization.toFixed(1)}%`;
    }
  };


  const updatePools = (pools, creatives) => {
    const fallback = computePoolStats(creatives);
    const poolMap = Array.isArray(pools)
      ? pools.reduce((acc, pool) => {
        if (pool?.slug) {
          acc[pool.slug] = pool;
        }
        return acc;
      }, {})
      : {};

    POOL_DEFINITIONS.forEach((pool) => {
      const stats = poolMap[pool.slug] ?? fallback[pool.slug];
      const elements = poolCards[pool.slug];
      if (!stats || !elements) {
        return;
      }
      if (elements.total) {
        elements.total.textContent = String(stats.total_creatives ?? 0);
      }
      if (elements.available) {
        elements.available.textContent = String(stats.available_creatives ?? 0);
      }
      if (elements.active) {
        elements.active.textContent = String(stats.active_creatives ?? 0);
      }
      if (elements.availableHours) {
        elements.availableHours.textContent =
          stats.available_hours_display ??
          formatHours(Number(stats.available_hours ?? 0));
      }
      if (elements.plannedHours) {
        elements.plannedHours.textContent =
          stats.planned_hours_display ??
          formatHours(Number(stats.planned_hours ?? 0));
      }
      if (elements.loggedHours) {
        elements.loggedHours.textContent =
          stats.logged_hours_display ??
          formatHours(Number(stats.logged_hours ?? 0));
      }
    });
  };

  const bindProjectToggle = (card, toggle, details) => {
    if (!card || !toggle || !details) {
      return;
    }
    if (card.dataset.projectInit === "true") {
      return;
    }
    card.dataset.projectInit = "true";
    const icon = toggle.querySelector("[data-project-toggle-icon]");
    const expanded = card.dataset.expanded === "true";
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    details.classList.toggle("hidden", !expanded);
    toggle.addEventListener("click", () => {
      const isExpanded = card.dataset.expanded === "true";
      const next = !isExpanded;
      card.dataset.expanded = next ? "true" : "false";
      toggle.setAttribute("aria-expanded", next ? "true" : "false");
      details.classList.toggle("hidden", !next);
      if (icon) {
        icon.classList.toggle("rotate-180", next);
      }
    });
  };

  const initializeProjectCards = () => {
    document.querySelectorAll("[data-project-card]").forEach((card) => {
      const toggle = card.querySelector("[data-project-toggle]");
      const details = card.querySelector("[data-project-details]");
      bindProjectToggle(card, toggle, details);
    });
  };

  const bindSubscriptionToggle = (card, toggle, details) => {
    if (!card || !toggle || !details) {
      return;
    }
    if (card.dataset.subscriptionInit === "true") {
      return;
    }
    card.dataset.subscriptionInit = "true";
    const icon = toggle.querySelector("[data-subscription-toggle-icon]");
    const expanded = card.dataset.expanded === "true";
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    details.classList.toggle("hidden", !expanded);
    toggle.addEventListener("click", () => {
      const isExpanded = card.dataset.expanded === "true";
      const next = !isExpanded;
      card.dataset.expanded = next ? "true" : "false";
      toggle.setAttribute("aria-expanded", next ? "true" : "false");
      details.classList.toggle("hidden", !next);
      if (icon) {
        icon.classList.toggle("rotate-180", next);
      }
    });
  };

  const initializeSubscriptionCards = () => {
    document.querySelectorAll("[data-subscription-card]").forEach((card) => {
      const toggle = card.querySelector("[data-subscription-toggle]");
      const details = card.querySelector("[data-subscription-details]");
      bindSubscriptionToggle(card, toggle, details);
    });
  };

  const buildProjectCard = (project) => {
    const projectName =
      typeof project?.project_name === "string" && project.project_name.trim().length > 0
        ? project.project_name.trim()
        : "Unnamed Project";
    const slug = projectName.toLowerCase().replace(/\s+/g, "-");
    const agreementLabel =
      typeof project?.agreement_type === "string" && project.agreement_type.trim().length > 0
        ? project.agreement_type.trim()
        : "Unknown";
    const totalExternalHours =
      typeof project?.total_external_hours === "number" ? project.total_external_hours : 0;
    const externalHoursDisplay =
      typeof project?.external_hours_display === "string" &&
        project.external_hours_display.trim().length > 0
        ? project.external_hours_display.trim()
        : formatHours(totalExternalHours);
    const totalAedValue = Number(project?.total_aed ?? 0);
    const totalAedDisplay =
      typeof project?.total_aed_display === "string" && project.total_aed_display.trim().length > 0
        ? project.total_aed_display.trim()
        : formatAed(totalAedValue);
    const tags = Array.isArray(project?.tags) ? project.tags : [];
    const orders = Array.isArray(project?.sales_orders) ? project.sales_orders : [];

    const card = document.createElement("article");
    card.className =
      "group flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition data-[expanded='true']:shadow-lg data-[expanded='true']:ring-1 data-[expanded='true']:ring-sky-200/60";
    card.dataset.projectCard = slug;
    card.dataset.expanded = "false";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.dataset.projectToggle = "true";
    toggle.setAttribute("aria-expanded", "false");
    toggle.className =
      "relative flex w-full min-h-[200px] flex-col justify-between gap-4 rounded-xl bg-gradient-to-r from-sky-500 via-sky-600 to-indigo-600 px-4 py-4 text-left text-white shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-white";

    const summary = document.createElement("div");
    summary.className = "flex flex-col gap-1";

    const summaryLabel = document.createElement("span");
    summaryLabel.className = "text-[11px] uppercase tracking-widest text-sky-100/90";
    summaryLabel.textContent = "Project";
    summary.appendChild(summaryLabel);

    const title = document.createElement("h4");
    title.className = "text-lg font-semibold leading-tight text-white min-h-[48px]";
    title.textContent = projectName;
    summary.appendChild(title);

    const agreement = document.createElement("p");
    agreement.className = "text-xs font-medium text-sky-100/80";
    agreement.textContent = `Agreement: ${agreementLabel}`;
    summary.appendChild(agreement);

    toggle.appendChild(summary);

    const summaryMetrics = document.createElement("div");
    summaryMetrics.className = "mt-auto flex flex-col items-end gap-1 text-sm font-semibold";

    const hoursSummary = document.createElement("span");
    hoursSummary.className = "text-sky-100/90";
    hoursSummary.textContent = `Hours: ${externalHoursDisplay}`;
    summaryMetrics.appendChild(hoursSummary);

    const aedSummary = document.createElement("span");
    aedSummary.className = "text-white/90";
    aedSummary.textContent = totalAedDisplay;
    summaryMetrics.appendChild(aedSummary);

    toggle.appendChild(summaryMetrics);

    const icon = document.createElement("span");
    icon.className =
      "material-symbols-rounded text-base text-white/80 transition group-data-[expanded='true']:rotate-180 pointer-events-none absolute top-4 right-4";
    icon.dataset.projectToggleIcon = "true";
    icon.textContent = "expand_more";
    toggle.appendChild(icon);

    const details = document.createElement("div");
    details.dataset.projectDetails = "true";
    details.className = "hidden space-y-4 pt-4";

    if (tags.length > 0) {
      const tagList = document.createElement("ul");
      tagList.className = "flex flex-wrap gap-2";
      tags.forEach((tag) => {
        const tagChip = document.createElement("li");
        tagChip.className =
          "inline-flex items-center rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-700";
        tagChip.textContent = tag;
        tagList.appendChild(tagChip);
      });
      details.appendChild(tagList);
    }

    const totalsBox = document.createElement("div");
    totalsBox.className =
      "flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600";

    const totalHoursEl = document.createElement("span");
    const totalHoursLabel = document.createElement("span");
    totalHoursLabel.className = "font-semibold text-slate-800";
    totalHoursLabel.textContent = "Total External Hours:";
    totalHoursEl.appendChild(totalHoursLabel);
    totalHoursEl.appendChild(document.createTextNode(` ${externalHoursDisplay}`));
    totalsBox.appendChild(totalHoursEl);

    const totalAedEl = document.createElement("span");
    const totalAedLabel = document.createElement("span");
    totalAedLabel.className = "font-semibold text-slate-800";
    totalAedLabel.textContent = "Total AED:";
    totalAedEl.appendChild(totalAedLabel);
    totalAedEl.appendChild(document.createTextNode(` ${totalAedDisplay}`));
    totalsBox.appendChild(totalAedEl);

    details.appendChild(totalsBox);

    const orderList = document.createElement("ul");
    orderList.dataset.projectOrders = "";
    orderList.className = "space-y-3 text-sm font-semibold text-slate-600";

    orders.forEach((order) => {
      const reference =
        typeof order?.order_reference === "string" && order.order_reference.trim().length > 0
          ? order.order_reference.trim()
          : "Unnamed Order";
      const orderHoursDisplay =
        typeof order?.external_hours_display === "string" &&
          order.external_hours_display.trim().length > 0
          ? order.external_hours_display.trim()
          : formatHours(order?.external_hours ?? 0);
      const rawOrderAed = Number(order?.aed_total ?? 0);
      const orderAedDisplay =
        typeof order?.aed_total_display === "string" && order.aed_total_display.trim().length > 0
          ? order.aed_total_display.trim()
          : formatAed(rawOrderAed);

      const orderItem = document.createElement("li");
      orderItem.className =
        "rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition hover:border-sky-200 hover:shadow";
      orderItem.dataset.projectOrder = "true";

      const topRow = document.createElement("div");
      topRow.className = "flex flex-wrap items-center justify-between gap-3";

      const orderInfo = document.createElement("span");
      orderInfo.className = "inline-flex items-center gap-2 text-slate-800";

      const badge = document.createElement("span");
      badge.className =
        "inline-flex items-center rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-700";
      badge.textContent = "Sales Order";
      orderInfo.appendChild(badge);

      const orderNumber = document.createElement("span");
      orderNumber.className = "text-sm font-semibold text-slate-900";
      orderNumber.textContent = reference;
      orderInfo.appendChild(orderNumber);

      topRow.appendChild(orderInfo);

      const orderMetrics = document.createElement("div");
      orderMetrics.className = "flex flex-wrap items-center gap-3 text-sm";

      const hoursValue = document.createElement("span");
      hoursValue.className = "text-slate-900";
      hoursValue.textContent = orderHoursDisplay;
      orderMetrics.appendChild(hoursValue);

      // Add order line count if available
      const orderLineCount = typeof order?.order_line_count === "number" ? order.order_line_count : null;
      if (orderLineCount !== null && orderLineCount > 0) {
        const lineCountValue = document.createElement("span");
        lineCountValue.className = "text-slate-600 text-xs";
        lineCountValue.textContent = `${orderLineCount} line${orderLineCount !== 1 ? "s" : ""}`;
        orderMetrics.appendChild(lineCountValue);
      }

      const aedValue = document.createElement("span");
      aedValue.className = "text-emerald-600";
      aedValue.textContent = orderAedDisplay;
      orderMetrics.appendChild(aedValue);

      topRow.appendChild(orderMetrics);
      orderItem.appendChild(topRow);
      orderList.appendChild(orderItem);
    });

    details.appendChild(orderList);

    card.appendChild(toggle);
    card.appendChild(details);

    return card;
  };

  const buildSubscriptionEntry = (subscription) => {
    const orderReference =
      typeof subscription?.order_reference === "string" && subscription.order_reference.trim()
        ? subscription.order_reference.trim()
        : "Subscription";
    const invoiceReference =
      typeof subscription?.invoice_reference === "string" && subscription.invoice_reference.trim()
        ? subscription.invoice_reference.trim()
        : "Invoice";
    const projectName =
      typeof subscription?.project_name === "string" && subscription.project_name.trim()
        ? subscription.project_name.trim()
        : "Unassigned Project";
    const agreementType =
      typeof subscription?.agreement_type === "string" && subscription.agreement_type.trim()
        ? subscription.agreement_type.trim()
        : "Unknown";
    const invoiceDateDisplay =
      typeof subscription?.invoice_date_display === "string" &&
        subscription.invoice_date_display.trim()
        ? subscription.invoice_date_display.trim()
        : "-";
    const monthlyHoursDisplay =
      typeof subscription?.monthly_billable_hours_display === "string" &&
        subscription.monthly_billable_hours_display.trim()
        ? subscription.monthly_billable_hours_display.trim()
        : formatHours(subscription?.monthly_billable_hours ?? 0);
    const usedHoursDisplay =
      typeof subscription?.subscription_used_hours_display === "string" &&
        subscription.subscription_used_hours_display.trim()
        ? subscription.subscription_used_hours_display.trim()
        : formatHours(subscription?.subscription_used_hours ?? 0);
    const aedTotalDisplay =
      typeof subscription?.aed_total_display === "string" &&
        subscription.aed_total_display.trim()
        ? subscription.aed_total_display.trim()
        : formatAed(subscription?.aed_total ?? 0);
    const tags = Array.isArray(subscription?.tags) ? subscription.tags : [];
    const parentTasks = Array.isArray(subscription?.subscription_parent_tasks)
      ? subscription.subscription_parent_tasks
      : [];

    const slug = orderReference.toLowerCase().replace(/\s+/g, "-");

    const card = document.createElement("section");
    card.className =
      "group flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition data-[expanded='true']:shadow-lg data-[expanded='true']:ring-1 data-[expanded='true']:ring-sky-200/60";
    card.dataset.subscriptionCard = slug;
    card.dataset.expanded = "false";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.dataset.subscriptionToggle = "true";
    toggle.setAttribute("aria-expanded", "false");
    toggle.className =
      "relative flex w-full min-h-[200px] flex-col justify-between gap-4 rounded-xl bg-gradient-to-r from-sky-500 via-sky-600 to-indigo-600 px-4 py-4 text-left text-white shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-white";

    const summary = document.createElement("div");
    summary.className = "flex flex-col gap-1";

    const label = document.createElement("span");
    label.className = "text-[11px] uppercase tracking-widest text-sky-100/90";
    label.textContent = "Subscription";
    summary.appendChild(label);

    const title = document.createElement("h4");
    title.className = "text-lg font-semibold leading-tight text-white";
    title.textContent = orderReference;
    summary.appendChild(title);

    const invoiceLine = document.createElement("p");
    invoiceLine.className = "text-xs font-medium text-sky-100/80";
    invoiceLine.textContent = `Invoice ${invoiceReference} - ${projectName}`;
    summary.appendChild(invoiceLine);

    const agreementLine = document.createElement("p");
    agreementLine.className = "text-xs font-medium text-sky-100/80";
    agreementLine.textContent = `Agreement: ${agreementType}`;
    summary.appendChild(agreementLine);

    toggle.appendChild(summary);

    const summaryMetrics = document.createElement("div");
    summaryMetrics.className = "mt-auto flex flex-col items-end gap-1 text-sm font-semibold";

    const hoursMetric = document.createElement("span");
    hoursMetric.className = "text-sky-100/90";
    hoursMetric.textContent = `Monthly Hours: ${monthlyHoursDisplay}`;
    summaryMetrics.appendChild(hoursMetric);

    const usedMetric = document.createElement("span");
    usedMetric.className = "text-sky-100/90";
    usedMetric.textContent = `Used Hours: ${usedHoursDisplay}`;
    summaryMetrics.appendChild(usedMetric);

    const aedMetric = document.createElement("span");
    aedMetric.className = "text-white/90";
    aedMetric.textContent = aedTotalDisplay;
    summaryMetrics.appendChild(aedMetric);

    toggle.appendChild(summaryMetrics);

    const icon = document.createElement("span");
    icon.className =
      "material-symbols-rounded text-base text-white/80 transition group-data-[expanded='true']:rotate-180 pointer-events-none absolute top-4 right-4";
    icon.dataset.subscriptionToggleIcon = "true";
    icon.textContent = "expand_more";
    toggle.appendChild(icon);

    const details = document.createElement("div");
    details.className = "hidden space-y-4 pt-4";
    details.dataset.subscriptionDetails = "true";

    if (tags.length > 0) {
      const tagList = document.createElement("ul");
      tagList.className = "flex flex-wrap gap-2";
      tags.forEach((tag) => {
        const tagChip = document.createElement("li");
        tagChip.className =
          "inline-flex items-center rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-700";
        tagChip.textContent = tag;
        tagList.appendChild(tagChip);
      });
      details.appendChild(tagList);
    }

    const infoRow = document.createElement("div");
    infoRow.className =
      "flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600";

    const dateLabel = document.createElement("span");
    dateLabel.innerHTML = `<span class="font-semibold text-slate-800">Invoice Date:</span> ${invoiceDateDisplay}`;
    infoRow.appendChild(dateLabel);

    const totalLabel = document.createElement("span");
    totalLabel.innerHTML = `<span class="font-semibold text-slate-800">Total AED:</span> ${aedTotalDisplay}`;
    infoRow.appendChild(totalLabel);

    details.appendChild(infoRow);

    const usedHoursContainer = document.createElement("div");
    usedHoursContainer.className =
      "rounded-xl border border-slate-200 bg-white px-4 py-4 text-sm text-slate-600";

    const usedHeader = document.createElement("div");
    usedHeader.className = "flex flex-wrap items-center justify-between gap-3";
    const usedLabelEl = document.createElement("span");
    usedLabelEl.className = "font-semibold text-slate-800";
    usedLabelEl.textContent = "Subscription Used Hours";
    const usedValueEl = document.createElement("span");
    usedValueEl.className = "text-base font-semibold text-slate-900";
    usedValueEl.textContent = usedHoursDisplay;
    usedHeader.appendChild(usedLabelEl);
    usedHeader.appendChild(usedValueEl);
    usedHoursContainer.appendChild(usedHeader);

    if (parentTasks.length > 0) {
      const parentListWrapper = document.createElement("div");
      parentListWrapper.className = "mt-3 space-y-3";

      const parentHeading = document.createElement("h5");
      parentHeading.className = "text-xs font-semibold uppercase tracking-wide text-slate-500";
      parentHeading.textContent = "Parent Tasks";
      parentListWrapper.appendChild(parentHeading);

      parentTasks.forEach((parentTask) => {
        const parentCard = document.createElement("article");
        parentCard.className = "rounded-lg border border-slate-200 bg-slate-50 px-3 py-3";

        const parentHeader = document.createElement("div");
        parentHeader.className = "flex flex-wrap items-start justify-between gap-3";

        const parentInfo = document.createElement("div");
        const parentName = document.createElement("p");
        parentName.className = "text-sm font-semibold text-slate-800";
        const parentTaskName =
          typeof parentTask?.task_name === "string" && parentTask.task_name.trim()
            ? parentTask.task_name.trim()
            : "Parent Task";
        parentName.textContent = parentTaskName;
        parentInfo.appendChild(parentName);

        const requestedDisplay =
          typeof parentTask?.request_datetime_display === "string" &&
            parentTask.request_datetime_display.trim()
            ? parentTask.request_datetime_display.trim()
            : "-";
        const requestedLabel = document.createElement("p");
        requestedLabel.className = "text-xs text-slate-500";
        requestedLabel.textContent = `Requested: ${requestedDisplay}`;
        parentInfo.appendChild(requestedLabel);

        parentHeader.appendChild(parentInfo);

        const parentHoursDisplay =
          typeof parentTask?.external_hours_display === "string" &&
            parentTask.external_hours_display.trim()
            ? parentTask.external_hours_display.trim()
            : formatHours(parentTask?.external_hours ?? 0);
        const parentHours = document.createElement("span");
        parentHours.className = "text-sm font-semibold text-slate-800";
        parentHours.textContent = parentHoursDisplay;
        parentHeader.appendChild(parentHours);

        parentCard.appendChild(parentHeader);

        const childTasks = Array.isArray(parentTask?.subtasks) ? parentTask.subtasks : [];
        if (childTasks.length > 0) {
          const childList = document.createElement("ul");
          childList.className = "mt-3 space-y-1 text-xs text-slate-600";
          childTasks.forEach((subtask) => {
            const row = document.createElement("li");
            row.className = "flex items-center justify-between gap-3 rounded-md bg-white px-2 py-1";

            const subtaskName = document.createElement("span");
            subtaskName.className = "font-medium text-slate-700";
            subtaskName.textContent =
              typeof subtask?.task_name === "string" && subtask.task_name.trim()
                ? subtask.task_name.trim()
                : "Subtask";
            row.appendChild(subtaskName);

            const subtaskHoursDisplay =
              typeof subtask?.external_hours_display === "string" &&
                subtask.external_hours_display.trim()
                ? subtask.external_hours_display.trim()
                : formatHours(subtask?.external_hours ?? 0);
            const subtaskHours = document.createElement("span");
            subtaskHours.className = "font-semibold text-slate-800";
            subtaskHours.textContent = subtaskHoursDisplay;
            row.appendChild(subtaskHours);

            childList.appendChild(row);
          });
          parentCard.appendChild(childList);
        }

        parentListWrapper.appendChild(parentCard);
      });

      usedHoursContainer.appendChild(parentListWrapper);
    } else {
      const emptyMessage = document.createElement("p");
      emptyMessage.className = "mt-3 text-xs text-slate-500";
      emptyMessage.textContent = "No subscription used hours recorded for this month.";
      usedHoursContainer.appendChild(emptyMessage);
    }

    details.appendChild(usedHoursContainer);

    card.appendChild(toggle);
    card.appendChild(details);

    return card;
  };

  const renderSubscriptionMarkets = (markets, summary = null) => {
    if (!clientSubscriptionGrid) {
      if (summary && typeof summary === "object") {
        creativeState.subscriptionSummary = summary;
      }
      renderSubscriptionSummary(summary ?? creativeState.subscriptionSummary);
      return;
    }

    const subscriptionMarkets = Array.isArray(markets) ? markets : [];
    creativeState.clientSubscriptions = subscriptionMarkets;
    if (summary && typeof summary === "object") {
      creativeState.subscriptionSummary = summary;
    }

    clientSubscriptionGrid.innerHTML = "";
    let gridClasses = "mt-6 grid gap-6 items-start";
    if (subscriptionMarkets.length >= 2) {
      gridClasses += " sm:grid-cols-2";
    }
    if (subscriptionMarkets.length >= 3) {
      gridClasses += " xl:grid-cols-3";
    } else if (subscriptionMarkets.length === 2) {
      gridClasses += " xl:grid-cols-2";
    }
    clientSubscriptionGrid.className = gridClasses;

    if (subscriptionMarkets.length === 0) {
      const empty = document.createElement("div");
      empty.className =
        "rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm font-semibold text-slate-500";
      empty.textContent = "No posted subscription invoices found for the selected month.";
      clientSubscriptionGrid.appendChild(empty);
      renderSubscriptionSummary(creativeState.subscriptionSummary);
      applySectionCollapsedState("subscription");
      return;
    }

    subscriptionMarkets.forEach((market) => {
      const marketName =
        typeof market?.market === "string" && market.market.trim()
          ? market.market.trim()
          : "Unnamed Market";
      const normalized = marketName.toLowerCase().replace(/\s+/g, "-");
      const totalMonthlyHours =
        typeof market?.total_monthly_hours === "number" ? market.total_monthly_hours : 0;
      const totalMonthlyDisplay =
        typeof market?.total_monthly_hours_display === "string" &&
          market.total_monthly_hours_display.trim()
          ? market.total_monthly_hours_display.trim()
          : formatHours(totalMonthlyHours);
      const totalUsedHours =
        typeof market?.total_subscription_used_hours === "number"
          ? market.total_subscription_used_hours
          : 0;
      const totalUsedDisplay =
        typeof market?.total_subscription_used_hours_display === "string" &&
          market.total_subscription_used_hours_display.trim()
          ? market.total_subscription_used_hours_display.trim()
          : formatHours(totalUsedHours);
      const totalAedValue = Number(market?.total_aed ?? 0);
      const totalAedDisplay =
        typeof market?.total_aed_display === "string" && market.total_aed_display.trim()
          ? market.total_aed_display.trim()
          : formatAed(totalAedValue);

      const card = document.createElement("article");
      card.className =
        "flex flex-col gap-5 rounded-3xl border border-slate-200 bg-white p-6 shadow-md transition hover:shadow-lg";
      card.dataset.subscriptionMarketCard = normalized;

      const header = document.createElement("header");
      header.className = "flex flex-wrap items-start justify-between gap-4";

      const headerLeft = document.createElement("div");
      const title = document.createElement("h3");
      title.className = "text-lg font-semibold text-slate-900";
      title.textContent = marketName;
      headerLeft.appendChild(title);

      const monthlyLabel = document.createElement("p");
      monthlyLabel.className = "text-xs font-medium text-slate-500";
      monthlyLabel.innerHTML = `Monthly Hours: <span class="font-semibold text-slate-700">${totalMonthlyDisplay}</span>`;
      headerLeft.appendChild(monthlyLabel);

      const usedLabel = document.createElement("p");
      usedLabel.className = "text-xs font-medium text-slate-500";
      usedLabel.innerHTML = `Subscription Used Hours: <span class="font-semibold text-slate-700">${totalUsedDisplay}</span>`;
      headerLeft.appendChild(usedLabel);

      header.appendChild(headerLeft);

      const headerRight = document.createElement("div");
      headerRight.className = "text-right";
      const aedCaption = document.createElement("span");
      aedCaption.className = "text-xs font-semibold uppercase tracking-wide text-slate-400";
      aedCaption.textContent = "Total AED";
      const aedValue = document.createElement("p");
      aedValue.className = "text-base font-semibold text-emerald-600";
      aedValue.textContent = totalAedDisplay;
      headerRight.appendChild(aedCaption);
      headerRight.appendChild(aedValue);
      header.appendChild(headerRight);

      card.appendChild(header);

      const entries = document.createElement("div");
      entries.className = "space-y-4";
      entries.dataset.subscriptionEntries = "";

      (Array.isArray(market?.subscriptions) ? market.subscriptions : []).forEach((subscription) => {
        entries.appendChild(buildSubscriptionEntry(subscription));
      });

      card.appendChild(entries);
      clientSubscriptionGrid.appendChild(card);
    });

    initializeSubscriptionCards();
    renderSubscriptionSummary(creativeState.subscriptionSummary);
    applySectionCollapsedState("subscription");
  };

  const renderClientMarkets = (markets, summary = null) => {
    if (!clientMarketGrid) {
      if (summary && typeof summary === "object") {
        creativeState.clientSummary = summary;
      }
      const effectiveSummary = summary ?? creativeState.clientSummary;
      renderCompanySummary(effectiveSummary);
      renderExternalSummary(effectiveSummary);
      return;
    }

    clientMarketData = Array.isArray(markets) ? markets : [];
    creativeState.clientMarkets = clientMarketData;
    if (summary && typeof summary === "object") {
      creativeState.clientSummary = summary;
    }

    clientMarketGrid.innerHTML = "";
    clientMarketGrid.className = "mt-6 grid gap-6 items-start";
    if (!clientMarketData.length) {
      const empty = document.createElement("div");
      empty.className =
        "rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm font-semibold text-slate-500";
      empty.textContent = "No external hours found for the selected month.";
      clientMarketGrid.appendChild(empty);
      renderCompanySummary(creativeState.clientSummary);
      renderExternalSummary(creativeState.clientSummary);
      applySectionCollapsedState("external");
      initializeProjectCards();
      return;
    }

    const marketCount = clientMarketData.length;
    let gridClasses = "mt-6 grid gap-6 items-start";
    if (marketCount >= 2) {
      gridClasses += " sm:grid-cols-2";
    }
    if (marketCount >= 3) {
      gridClasses += " xl:grid-cols-3";
    } else if (marketCount === 2) {
      gridClasses += " xl:grid-cols-2";
    }
    clientMarketGrid.className = gridClasses;

    clientMarketData.forEach((market) => {
      const marketName =
        typeof market?.market === "string" && market.market.trim().length > 0
          ? market.market.trim()
          : "Unnamed Market";
      const normalizedMarket = marketName.toLowerCase().replace(/\s+/g, "-");
      const totalHours =
        typeof market?.total_external_hours === "number" ? market.total_external_hours : 0;
      const totalHoursDisplay =
        typeof market?.total_external_hours_display === "string" &&
          market.total_external_hours_display.trim().length > 0
          ? market.total_external_hours_display.trim()
          : formatHours(totalHours);
      const totalAedValue = Number(market?.total_aed ?? 0);
      const totalAedDisplay =
        typeof market?.total_aed_display === "string" && market.total_aed_display.trim().length > 0
          ? market.total_aed_display.trim()
          : formatAed(totalAedValue);
      const invoiceCount = Number(market?.total_invoices ?? 0);

      const marketCard = document.createElement("article");
      marketCard.className =
        "flex flex-col gap-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-md transition hover:shadow-lg";
      marketCard.dataset.marketCard = normalizedMarket;

      const header = document.createElement("header");
      header.className = "flex flex-wrap items-start justify-between gap-4";

      const headerLeft = document.createElement("div");
      const title = document.createElement("h3");
      title.className = "text-lg font-semibold text-slate-900";
      title.textContent = marketName;
      headerLeft.appendChild(title);

      const summaryLine = document.createElement("p");
      summaryLine.className = "text-xs font-medium text-slate-500";
      summaryLine.innerHTML = `Monthly Hours: <span class="font-semibold text-slate-700">${totalHoursDisplay}</span> - Total AED: <span class="font-semibold text-emerald-600">${totalAedDisplay}</span>`;
      headerLeft.appendChild(summaryLine);

      header.appendChild(headerLeft);

      if (Number.isFinite(invoiceCount) && invoiceCount > 0) {
        const badge = document.createElement("div");
        badge.className =
          "rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600";
        badge.textContent = `${invoiceCount.toLocaleString()} invoice${invoiceCount === 1 ? "" : "s"
          }`;
        header.appendChild(badge);
      }

      marketCard.appendChild(header);

      const projectsContainer = document.createElement("div");
      projectsContainer.className = "space-y-4";
      projectsContainer.dataset.marketProjects = "";

      (Array.isArray(market?.projects) ? market.projects : []).forEach((project) => {
        projectsContainer.appendChild(buildProjectCard(project));
      });

      marketCard.appendChild(projectsContainer);
      clientMarketGrid.appendChild(marketCard);
    });

    renderCompanySummary(creativeState.clientSummary);
    renderExternalSummary(creativeState.clientSummary);
    initializeProjectCards();
    applySectionCollapsedState("external");
  };

  const assignmentFilterModelIsBu = () =>
    Boolean(
      creativeFilterForm?.dataset?.assignmentModel === "bu" || creativeState.useBuAssignmentFilters
    );

  /** Align with backend assignment_service.use_business_unit_model (2026-04-01 cutover). */

  const computeFilteredAggregates = (filteredCreatives, allCreatives) => {
    const totals = { planned: 0.0, logged: 0.0, available: 0.0 };

    filteredCreatives.forEach(creative => {
      totals.planned += Number(creative.planned_hours || 0);
      totals.logged += Number(creative.logged_hours || 0);
      totals.available += Number(creative.available_hours || 0);
    });

    const maxValue = Math.max(totals.planned, totals.logged, totals.available);
    const useBuModel = assignmentFilterModelIsBu();
    const selectedMarkets = getSelectedMarkets();
    const selectedPools = getSelectedPools();
    const selectedBu = getSelectedBusinessUnits();
    const selectedSbu = getSelectedSubBusinessUnits();
    const selectedPod = getSelectedPods();

    const marketFilterSet =
      !useBuModel && Array.isArray(selectedMarkets) && selectedMarkets.length > 0
        ? new Set(selectedMarkets.map((value) => value.toLowerCase()))
        : null;
    const poolFilterSet =
      !useBuModel && Array.isArray(selectedPools) && selectedPools.length > 0
        ? new Set(selectedPools)
        : null;

    const formatHours = (value) => {
      const totalMinutes = Math.round(value * 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      if (minutes === 0) {
        return `${hours}h`;
      }
      return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
    };

    const previousTotals =
      creativeState.hasPreviousMonth && Array.isArray(allCreatives)
        ? useBuModel
          ? sumPreviousTotalsForBuFilters(allCreatives, selectedBu, selectedSbu, selectedPod)
          : sumPreviousTotalsForFilters(allCreatives, marketFilterSet, poolFilterSet)
        : null;
    const comparison =
      creativeState.hasPreviousMonth && previousTotals
        ? buildComparisonFromTotals(totals, previousTotals)
        : null;

    return {
      ...totals,
      max: maxValue,
      display: {
        planned: formatHours(totals.planned),
        logged: formatHours(totals.logged),
        available: formatHours(totals.available),
      },
      comparison,
    };
  };


  const renderFilteredCreatives = () => {
    try {
      const allCreatives = Array.isArray(creativeState.creatives) ? creativeState.creatives : [];
      const useBuModel = assignmentFilterModelIsBu();
      const selectedMarkets = getSelectedMarkets();
      const selectedPools = getSelectedPools();
      const selectedBu = getSelectedBusinessUnits();
      const selectedSbu = getSelectedSubBusinessUnits();
      const selectedPod = getSelectedPods();
      const filtersActive = useBuModel
        ? selectedBu.length > 0 || selectedSbu.length > 0 || selectedPod.length > 0
        : selectedMarkets.length > 0 || selectedPools.length > 0;

      const filteredCreatives = filterCreativesClientSide(
        allCreatives,
        selectedMarkets,
        selectedPools,
        selectedBu,
        selectedSbu,
        selectedPod,
        useBuModel
      );

      const filteredAggregates = filtersActive
        ? computeFilteredAggregates(filteredCreatives, allCreatives)
        : null;
      // Backend now always returns unfiltered tasks_stats, so use allTasksStats for filtering
      // Filter tasks to only those assigned to creatives matching the current filters
      // If allTasksStats is not set yet (initial page load), use tasks_stats or aggregates.tasks_stats
      const tasksStatsToFilter = creativeState.allTasksStats || creativeState.tasks_stats || creativeState.aggregates?.tasks_stats;
      const filteredTasksStats = filtersActive && tasksStatsToFilter
        ? computeFilteredTasksStats(tasksStatsToFilter, filteredCreatives)
        : creativeState.tasks_stats || creativeState.aggregates?.tasks_stats;
      if (filteredAggregates) {
        filteredAggregates.tasks_stats = filteredTasksStats;
      }
      // Filter overtime stats based on filtered creatives
      const overtimeStatsToFilter = creativeState.allOvertimeStats || creativeState.overtime_stats;
      const filteredOvertimeStats = filtersActive && overtimeStatsToFilter
        ? computeFilteredOvertimeStats(overtimeStatsToFilter, filteredCreatives)
        : creativeState.overtime_stats;

      const filteredPoolStats = computeFilteredPoolStats(filteredCreatives);
      const selectedFilterLabels = [];
      if (useBuModel) {
        selectedBu.forEach((v) => {
          if (typeof v === "string" && v.length > 0) selectedFilterLabels.push(v);
        });
        selectedSbu.forEach((v) => {
          if (typeof v === "string" && v.length > 0) selectedFilterLabels.push(v);
        });
        selectedPod.forEach((v) => {
          if (typeof v === "string" && v.length > 0) selectedFilterLabels.push(v);
        });
      } else {
        selectedMarkets.forEach((slug) => {
          const match = allCreatives.find((creative) => creative.market_slug === slug);
          if (match?.market_display) {
            selectedFilterLabels.push(match.market_display);
          } else if (typeof slug === "string" && slug.length > 0) {
            selectedFilterLabels.push(slug.toUpperCase());
          }
        });
        selectedPools.forEach((pool) => {
          if (typeof pool === "string" && pool.length > 0) {
            selectedFilterLabels.push(pool);
          }
        });
      }

      renderCreatives(
        filteredCreatives,
        creativeState.monthName || "",
        null,  // Don't pass stats - let renderCreatives use backend stats from creativeState
        filteredAggregates,
        filteredPoolStats,
        creativeState.clientMarkets || [],
        {
          filtersActive: filtersActive,
          selectedMarkets,
          selectedPools,
          selectedFilterLabels,
          tasks_stats: filteredTasksStats,
          overtime_stats: filteredOvertimeStats,
        }
      );
    } catch (error) {
      console.error("Error rendering creatives:", error);
      showErrorBanner("Failed to render creatives. Please refresh the page.");
    }
  };

  // Creative card rendering lives in cards.js.
  const { renderCreatives } = createCardRenderer({
    grid,
    monthLabel,
    utilizationTitle,
    utilizationTitleDefault,
    creativeState,
    updateMonthLabel,
    updateStats,
    updateAggregates,
    updateHeadcount,
    updateTasks,
    updateOvertime,
    updatePools,
    formatPoolSelectionHeading,
    renderClientMarkets,
    renderSubscriptionMarkets,
    renderSubscriptionUsedHoursChart,
    initializeCollapsibleSections,
  });

  const FILTER_PILL_CLASS_DEFAULT =
    "inline-flex items-center rounded-full border px-4 py-2 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-sky-300 focus:ring-offset-2 border-slate-200 bg-white text-slate-700 hover:bg-slate-50";
  const FILTER_PILL_CLASS_SELECTED =
    "inline-flex items-center rounded-full border px-4 py-2 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-sky-300 focus:ring-offset-2 border-sky-500 bg-sky-50 text-sky-700";

  const captureCreativeFilterSelection = () => ({
    market: [
      ...(creativeFilterForm?.querySelectorAll("[data-creative-filter='market'].border-sky-500") || []),
    ].map((b) => b.dataset.filterValue),
    pool: [
      ...(creativeFilterForm?.querySelectorAll("[data-creative-filter='pool'].border-sky-500") || []),
    ].map((b) => b.dataset.filterValue),
    business_unit: [
      ...(creativeFilterForm?.querySelectorAll(
        "[data-creative-filter='business_unit'].border-sky-500"
      ) || []),
    ].map((b) => b.dataset.filterValue),
    sub_business_unit: [
      ...(creativeFilterForm?.querySelectorAll(
        "[data-creative-filter='sub_business_unit'].border-sky-500"
      ) || []),
    ].map((b) => b.dataset.filterValue),
    pod: [
      ...(creativeFilterForm?.querySelectorAll("[data-creative-filter='pod'].border-sky-500") || []),
    ].map((b) => b.dataset.filterValue),
  });

  const restoreCreativeFilterSelection = (sel) => {
    if (!creativeFilterForm || !sel) return;
    const kinds = ["market", "pool", "business_unit", "sub_business_unit", "pod"];
    kinds.forEach((kind) => {
      const values = new Set(sel[kind] || []);
      creativeFilterForm.querySelectorAll(`[data-creative-filter='${kind}']`).forEach((btn) => {
        const on = values.has(btn.dataset.filterValue);
        btn.className = on ? FILTER_PILL_CLASS_SELECTED : FILTER_PILL_CLASS_DEFAULT;
      });
    });
  };

  const fillCreativeFilterPillContainer = (selector, items, kind) => {
    const wrap = document.querySelector(selector);
    if (!wrap) return;
    wrap.innerHTML = "";
    (items || []).forEach((opt) => {
      if (!opt || opt.value === undefined || opt.value === null) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.creativeFilter = kind;
      btn.dataset.filterValue = String(opt.value);
      btn.className = FILTER_PILL_CLASS_DEFAULT;
      btn.textContent = opt.label != null ? String(opt.label) : String(opt.value);
      wrap.appendChild(btn);
    });
  };

  const rebuildCreativeFilterOptionButtons = (payload) => {
    if (!payload || typeof payload !== "object") return;
    const captured = captureCreativeFilterSelection();
    fillCreativeFilterPillContainer(
      "[data-creative-legacy-market-buttons]",
      payload.available_markets,
      "market"
    );
    fillCreativeFilterPillContainer(
      "[data-creative-legacy-pool-buttons]",
      payload.available_pools,
      "pool"
    );
    fillCreativeFilterPillContainer(
      "[data-creative-bu-business-unit-buttons]",
      payload.available_business_units,
      "business_unit"
    );
    fillCreativeFilterPillContainer(
      "[data-creative-bu-sbu-buttons]",
      payload.available_sub_business_units,
      "sub_business_unit"
    );
    fillCreativeFilterPillContainer("[data-creative-bu-pod-buttons]", payload.available_pods, "pod");
    restoreCreativeFilterSelection(captured);
  };

  const syncCreativesFilterHelpText = () => {
    const help = document.querySelector("[data-creative-filter-help]");
    if (!help) return;
    if (assignmentFilterModelIsBu()) {
      help.textContent =
        "Filter creatives by business unit (BU), sub business unit (SBU), and pod. Click to select multiple options.";
      return;
    }
    const marketSection = document.querySelector("[data-creative-market-filter-section]");
    const showMarket = marketSection && !marketSection.classList.contains("hidden");
    help.textContent = showMarket
      ? "Filter creatives by market and pool. Click to select multiple options."
      : "Filter creatives by pool. Click to select multiple options.";
  };

  const syncCreativeFilterPanelsFromPayload = (payload) => {
    if (!payload || typeof payload !== "object") return;
    if (!Object.prototype.hasOwnProperty.call(payload, "use_bu_assignment_filters")) {
      return;
    }
    const isBu = Boolean(payload.use_bu_assignment_filters);
    creativeState.useBuAssignmentFilters = isBu;
    if (creativeFilterForm) {
      creativeFilterForm.dataset.assignmentModel = isBu ? "bu" : "legacy";
    }
    document.querySelector("[data-creative-filters-legacy]")?.classList.toggle("hidden", isBu);
    document.querySelector("[data-creative-filters-bu]")?.classList.toggle("hidden", !isBu);
    rebuildCreativeFilterOptionButtons(payload);
    syncCreativesFilterHelpText();
  };

  const clearAllCreativeFilterPills = () => {
    creativeFilterForm?.querySelectorAll("[data-creative-filter]").forEach((button) => {
      button.classList.remove("border-sky-500", "bg-sky-50", "text-sky-700");
      button.classList.add("border-slate-200", "bg-white", "text-slate-700");
    });
  };

  const getSelectedMarkets = () => {
    const selected = [];
    creativeFilterForm?.querySelectorAll("[data-creative-filter='market']").forEach((button) => {
      if (button.classList.contains("border-sky-500")) {
        selected.push(button.dataset.filterValue);
      }
    });
    return selected;
  };

  const getSelectedPools = () => {
    const selected = [];
    creativeFilterForm?.querySelectorAll("[data-creative-filter='pool']").forEach((button) => {
      if (button.classList.contains("border-sky-500")) {
        selected.push(button.dataset.filterValue);
      }
    });
    return selected;
  };

  const getSelectedBusinessUnits = () => {
    const selected = [];
    creativeFilterForm?.querySelectorAll("[data-creative-filter='business_unit']").forEach((button) => {
      if (button.classList.contains("border-sky-500")) {
        selected.push(button.dataset.filterValue);
      }
    });
    return selected;
  };

  const getSelectedSubBusinessUnits = () => {
    const selected = [];
    creativeFilterForm
      ?.querySelectorAll("[data-creative-filter='sub_business_unit']")
      .forEach((button) => {
        if (button.classList.contains("border-sky-500")) {
          selected.push(button.dataset.filterValue);
        }
      });
    return selected;
  };

  const getSelectedPods = () => {
    const selected = [];
    creativeFilterForm?.querySelectorAll("[data-creative-filter='pod']").forEach((button) => {
      if (button.classList.contains("border-sky-500")) {
        selected.push(button.dataset.filterValue);
      }
    });
    return selected;
  };

  // API layer (buildApiUrl + fetchCreatives + month cache) lives in api.js.
  const { fetchCreatives, clearMonthPayloadCache } = createCreativesApi({
    getCombinedYm,
    agreementFilterSelect,
    accountFilterSelect,
    creativeState,
    tabButtons,
    loadingOverlay,
    monthLabel,
    subscriptionUsedHoursChart,
    hideErrorBanner,
    showErrorBanner,
    setLoadingState,
    populateClientFilters,
    applyClientFilters,
    renderSubscriptionUsedHoursChart,
    syncCreativeFilterPanelsFromPayload,
    renderFilteredCreatives,
    updateMonthlyUtilizationChart,
    applyMonthKeyToSelects,
  });









  updateMonthLabel(monthLabel?.textContent?.trim() || "");
  if (initialFilterOptions) {
    populateClientFilters(initialFilterOptions, initialSelectedFilters);
  }
  // Initialize allTasksStats from aggregates if available (for initial page load before API call)
  if (!creativeState.allTasksStats && creativeState.aggregates?.tasks_stats) {
    creativeState.allTasksStats = creativeState.aggregates.tasks_stats;
  }
  // Initialize allOvertimeStats from overtime_stats if available (for initial page load before API call)
  if (!creativeState.allOvertimeStats && creativeState.overtime_stats) {
    creativeState.allOvertimeStats = creativeState.overtime_stats;
  }
  applyClientFilters();
  syncHeadcountDetailsBadgesFromLists();
  renderFilteredCreatives();
  setSubscriptionUsedHoursMode(initialUsedHoursMode, { rerender: false });
  renderSubscriptionUsedHoursChart(creativeState.subscriptionUsedHoursSeries);
  initializeCollapsibleSections();
  initializeProjectCards();
  initializeServerRenderedCards();
  initMonthlyUtilizationChart();
  // First view is server-rendered (no fetchCreatives call), so warm the
  // per-card daily hours for the initial period here.
  warmDailyHours(getCombinedYm());
  initTimecardExport({
    creativeState,
    getPeriodValue: getCombinedYm,
    getPeriodLabel: () => monthLabel?.textContent?.trim() || getCombinedYm() || "",
  });


  // Pool filter removed - no event listeners needed

  const handleLoad = () => {
    fetchCreatives(getCombinedYm());
  };

  // The Refresh button always re-fetches from the server, bypassing the
  // session month cache; month/year changes may serve from it.
  const handleForceRefresh = () => {
    fetchCreatives(getCombinedYm(), { forceRefresh: true });
  };

  // Toggling a New Joiner pill: flip the creative's hours locally using the
  // pre-zeroing values the backend ships (new_joiner_raw) and re-render
  // through the same path filters use — instant, no loading overlay. The
  // month payload cache is dropped since the server math has changed; a full
  // refetch only happens if the raw values are missing (old cached payload).
  document.addEventListener("newJoinerInclusionChanged", (event) => {
    const { creativeId, included } = event.detail || {};
    const allCreatives = Array.isArray(creativeState.creatives) ? creativeState.creatives : [];
    const target = allCreatives.find((creative) => creative.id === creativeId);
    if (!target || !applyNewJoinerFlipToCreative(target, included)) {
      handleForceRefresh();
      return;
    }
    creativeState.aggregates = {
      ...computeFilteredAggregates(allCreatives, allCreatives),
      tasks_stats: creativeState.aggregates?.tasks_stats,
    };
    clearMonthPayloadCache();
    renderFilteredCreatives();
  });

  const handleClientFilterChange = () => {
    applyClientFilters();
  };

  if (refreshButton) {
    refreshButton.addEventListener("click", handleForceRefresh);
  }

  if (monthPartSelect) {
    monthPartSelect.addEventListener("change", handleLoad);
  }
  if (yearSelect) {
    yearSelect.addEventListener("change", handleLoad);
  }

  if (agreementFilterSelect) {
    agreementFilterSelect.addEventListener("change", handleClientFilterChange);
  }
  if (accountFilterSelect) {
    accountFilterSelect.addEventListener("change", handleClientFilterChange);
  }

  const toggleCreativeFilterPillButton = (button) => {
    const isSelected = button.classList.contains("border-sky-500");
    if (isSelected) {
      button.classList.remove("border-sky-500", "bg-sky-50", "text-sky-700");
      button.classList.add("border-slate-200", "bg-white", "text-slate-700");
    } else {
      button.classList.remove("border-slate-200", "bg-white", "text-slate-700");
      button.classList.add("border-sky-500", "bg-sky-50", "text-sky-700");
    }
  };

  if (creativeFilterForm) {
    creativeFilterForm.addEventListener("click", (event) => {
      const resetEl = event.target.closest("[data-creative-filter-reset]");
      if (resetEl && creativeFilterForm.contains(resetEl)) {
        clearAllCreativeFilterPills();
        renderFilteredCreatives();
        updateMonthlyUtilizationChart();
        return;
      }
      const button = event.target.closest("[data-creative-filter]");
      if (!button || !creativeFilterForm.contains(button)) {
        return;
      }
      const kind = button.dataset.creativeFilter;
      if (
        kind === "market" ||
        kind === "pool" ||
        kind === "business_unit" ||
        kind === "sub_business_unit" ||
        kind === "pod"
      ) {
        toggleCreativeFilterPillButton(button);
        renderFilteredCreatives();
        updateMonthlyUtilizationChart();
      }
    });
  }

  const creativesMarketFilterSection = document.querySelector("[data-creative-market-filter-section]");
  const creativesFilterHelp = document.querySelector("[data-creative-filter-help]");

  const applyCreativesMarketFilterVisibility = (visible) => {
    const show = Boolean(visible);
    if (creativesMarketFilterSection) {
      creativesMarketFilterSection.classList.toggle("hidden", !show);
    }
    if (assignmentFilterModelIsBu()) {
      syncCreativesFilterHelpText();
    } else if (creativesFilterHelp) {
      creativesFilterHelp.textContent = show
        ? "Filter creatives by market and pool. Click to select multiple options."
        : "Filter creatives by pool. Click to select multiple options.";
    }
    if (!show) {
      document.querySelectorAll("[data-creative-filter='market']").forEach((button) => {
        button.classList.remove("border-sky-500", "bg-sky-50", "text-sky-700");
        button.classList.add("border-slate-200", "bg-white", "text-slate-700");
      });
      renderFilteredCreatives();
      updateMonthlyUtilizationChart();
    }
  };

  window.addEventListener("dashboardAuthResolved", (e) => {
    const v = e.detail?.market_filter_visible;
    if (typeof v === "boolean") {
      applyCreativesMarketFilterVisibility(v);
    }
  });

  // Creative Search and Group Management
  // Creative search + group management lives in groups.js.
  initCreativeGroups({
    creativeState,
    computeFilteredAggregates,
    computeFilteredPoolStats,
    renderCreatives,
  });

  // Initialize new joiners tooltip
  initNewJoinersTooltip();

  /** Sales tab uses the same month/quarter selectors as creatives. */
  const applySalesTabMonthPartOptions = (_targetTab) => {
    void _targetTab;
  };

  // Switch to a tab
  const switchToTab = (targetTab) => {
    // Update button states
    tabButtons.forEach((btn) => {
      btn.dataset.active = "false";
    });
    const activeButton = Array.from(tabButtons).find(btn => btn.dataset.dashboardTab === targetTab);
    if (activeButton) {
      activeButton.dataset.active = "true";
    }

    // Update panel visibility
    panels.forEach((panel) => {
      const panelName = panel.dataset.dashboardPanel;
      if (panelName === targetTab) {
        panel.classList.remove("hidden");
      } else {
        panel.classList.add("hidden");
      }
    });

    // Update dashboard title
    const dashboardTitle = document.querySelector("[data-dashboard-title]");
    if (dashboardTitle) {
      if (targetTab === "sales") {
        dashboardTitle.textContent = "Sales Dashboard";
      } else {
        dashboardTitle.textContent = "Creatives Dashboard";
      }
    }

    applySalesTabMonthPartOptions(targetTab);

    // Dispatch custom event for sales dashboard to handle
    if (targetTab === "sales") {
      const event = new CustomEvent("salesTabActivated", { detail: { month: getCombinedYm() } });
      document.dispatchEvent(event);
    }
  };

  // Tab switching functionality
  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const targetTab = button.dataset.dashboardTab;
      switchToTab(targetTab);
    });
  });

  const initialDashboardTab =
    Array.from(tabButtons).find((b) => b.dataset.active === "true")?.dataset.dashboardTab || "team";
  switchToTab(initialDashboardTab);

  // Number subscription table rows
  const numberSubscriptionTableRows = () => {
    const tableBody = document.querySelector('[data-subscription-table-body]');
    if (tableBody) {
      const rows = tableBody.querySelectorAll('tr:not([colspan])');
      rows.forEach((row, index) => {
        const rowNumberCell = row.querySelector('[data-row-number]');
        if (rowNumberCell) {
          rowNumberCell.textContent = index + 1;
        }
      });
    }
  };

  // Number rows on page load
  numberSubscriptionTableRows();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initDashboard);
} else {
  initDashboard();
}
