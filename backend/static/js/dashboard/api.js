// API layer for the creatives dashboard: builds /api/creatives URLs, fetches
// month payloads (with the 10-minute session cache), and applies the payload
// to dashboard state + renderers supplied by main.js. Bodies are verbatim
// from main.js (original indentation kept).
import { registerPoolLabelsFromData } from "./utils.js";
import { warmDailyHours } from "./daycal.js";

export function createCreativesApi({
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
}) {
  let activeFetchController = null;

  const buildApiUrl = (monthValue) => {
    const params = new URLSearchParams();
    const ym = monthValue ?? getCombinedYm();
    if (ym) {
      const dash = ym.indexOf("-");
      if (dash > 0) {
        const yPart = ym.slice(0, dash);
        const rest = ym.slice(dash + 1);
        params.set("year", yPart);
        if (rest.startsWith("Q")) {
          params.set("month", rest);
        } else {
          params.set("month", String(parseInt(rest, 10)));
        }
      }
    }

    // Market and pool filters are handled client-side only
    // Do not send these parameters to the backend to ensure we always get all creatives
    // This prevents filter state corruption when refreshing with active filters

    const agreementValue = agreementFilterSelect?.value?.trim();
    if (agreementValue) {
      params.set("agreement_type", agreementValue);
    }
    const accountValue = accountFilterSelect?.value?.trim();
    if (accountValue) {
      params.set("account_type", accountValue);
    }
    const query = params.toString();
    return query ? `/api/creatives?${query}` : "/api/creatives";
  };

  // Session cache of raw /api/creatives responses so flipping back to a
  // recently viewed month renders instantly. Stores the response TEXT and
  // re-parses on every hit, so later state mutations can never leak into the
  // cache. The Refresh button always bypasses and overwrites it.
  const monthPayloadCache = new Map();
  const MONTH_PAYLOAD_CACHE_TTL_MS = 10 * 60 * 1000;
  const MONTH_PAYLOAD_CACHE_MAX_ENTRIES = 12;

  const fetchCreatives = async (monthValue, options = {}) => {
    const forceRefresh = Boolean(options.forceRefresh);
    if (activeFetchController) {
      activeFetchController.abort();
    }

    const controller = new AbortController();
    activeFetchController = controller;

    hideErrorBanner();
    setLoadingState(true);
    // Only show the global loading overlay when the creatives tab is active.
    // When on Sales, the sales dashboard handles its own overlay so we avoid hiding it prematurely.
    const getActiveTab = () =>
      Array.from(tabButtons).find((btn) => btn.dataset.active === "true")?.dataset.dashboardTab;
    const isSalesTabActive = getActiveTab() === "sales";
    if (loadingOverlay && !isSalesTabActive) {
      loadingOverlay.classList.remove("hidden");
    }

    try {
      const apiUrl = buildApiUrl(monthValue);
      let payload;
      const cachedEntry = monthPayloadCache.get(apiUrl);
      if (
        !forceRefresh &&
        cachedEntry &&
        Date.now() - cachedEntry.at < MONTH_PAYLOAD_CACHE_TTL_MS
      ) {
        payload = JSON.parse(cachedEntry.text);
      } else {
        const response = await fetch(apiUrl, {
          signal: controller.signal,
        });
        if (!response.ok) {
          const detail = response.statusText || `status ${response.status}`;
          throw new Error(`Request failed (${detail})`);
        }
        const responseText = await response.text();
        payload = JSON.parse(responseText);
        monthPayloadCache.delete(apiUrl);
        monthPayloadCache.set(apiUrl, { at: Date.now(), text: responseText });
        while (monthPayloadCache.size > MONTH_PAYLOAD_CACHE_MAX_ENTRIES) {
          monthPayloadCache.delete(monthPayloadCache.keys().next().value);
        }
      }
      const creatives = Array.isArray(payload.creatives) ? payload.creatives : [];
      creativeState.creatives = creatives;
      creativeState.hasPreviousMonth = Boolean(payload.has_previous_month);
      if (typeof payload.selected_month === "string") {
        creativeState.selectedMonthValue = payload.selected_month;
      }
      creativeState.stats = payload.stats ?? null;
      creativeState.aggregates = payload.aggregates ?? null;
      creativeState.headcount = payload.headcount ?? null;
      creativeState.tasks_stats = payload.tasks_stats ?? null;
      // Backend now always returns unfiltered tasks_stats (all tasks for all creatives)
      // Store it as the baseline for client-side filtering
      if (payload.tasks_stats) {
        creativeState.allTasksStats = payload.tasks_stats;
      }
      // Also ensure allTasksStats is set if not already set (for initial page load)
      if (!creativeState.allTasksStats && (creativeState.tasks_stats || creativeState.aggregates?.tasks_stats)) {
        creativeState.allTasksStats = creativeState.tasks_stats || creativeState.aggregates?.tasks_stats;
      }
      creativeState.overtime_stats = payload.overtime_stats ?? null;
      // Backend now returns overtime_stats with individual requests for client-side filtering
      // Store it as the baseline for client-side filtering
      if (payload.overtime_stats) {
        creativeState.allOvertimeStats = payload.overtime_stats;
      }
      creativeState.pools = payload.pool_stats ?? null;
      registerPoolLabelsFromData(creativeState.pools ?? []);
      creativeState.monthName =
        payload.readable_month ?? monthLabel?.textContent ?? creativeState.monthName;
      if (Array.isArray(payload.client_external_hours_all)) {
        creativeState.clientMarketsAll = payload.client_external_hours_all;
      } else if (Array.isArray(payload.client_external_hours)) {
        creativeState.clientMarketsAll = payload.client_external_hours;
      }
      if (Array.isArray(payload.client_subscription_hours_all)) {
        creativeState.clientSubscriptionsAll = payload.client_subscription_hours_all;
      } else if (Array.isArray(payload.client_subscription_hours)) {
        creativeState.clientSubscriptionsAll = payload.client_subscription_hours;
      }
      // Previous-period breakdown for the External Hours Used trend badge;
      // must track the viewed month, so a payload without it clears the old
      // value.
      const previousExternal = payload.client_external_hours_previous;
      creativeState.clientExternalPrevious =
        previousExternal &&
        typeof previousExternal === "object" &&
        typeof previousExternal.total === "number"
          ? previousExternal
          : null;
      creativeState.clientFilterOptions =
        payload.client_filter_options ?? creativeState.clientFilterOptions;
      creativeState.clientSummary = payload.client_sales_summary ?? creativeState.clientSummary;
      creativeState.subscriptionSummary =
        payload.client_subscription_summary ?? creativeState.subscriptionSummary;
      creativeState.subscriptionOverview =
        payload.client_subscription_summary ?? creativeState.subscriptionOverview;
      creativeState.subscriptionTopClients = Array.isArray(payload.client_subscription_top_clients)
        ? payload.client_subscription_top_clients
        : creativeState.subscriptionTopClients;
      if (payload.client_filter_options) {
        populateClientFilters(payload.client_filter_options, payload.selected_filters);
      } else if (creativeState.clientFilterOptions) {
        populateClientFilters(creativeState.clientFilterOptions, payload.selected_filters);
      }
      creativeState.subscriptionUsedHoursSeries = Array.isArray(
        payload.client_subscription_used_hours_series
      )
        ? payload.client_subscription_used_hours_series
        : creativeState.subscriptionUsedHoursSeries;
      if (payload.client_filter_options) {
        populateClientFilters(payload.client_filter_options, payload.selected_filters);
      }
      if (typeof payload.client_subscription_used_hours_year === "number") {
        creativeState.subscriptionUsedHoursYear = Number(payload.client_subscription_used_hours_year);
      }
      if (typeof payload.client_subscription_used_hours_year === "number") {
        creativeState.subscriptionUsedHoursYear = Number(payload.client_subscription_used_hours_year);
      } else if (Array.isArray(creativeState.subscriptionUsedHoursSeries) && creativeState.subscriptionUsedHoursSeries.length > 0) {
        const derivedYear = Number(creativeState.subscriptionUsedHoursSeries[0]?.year);
        if (Number.isFinite(derivedYear)) {
          creativeState.subscriptionUsedHoursYear = derivedYear;
        }
      }
      if (subscriptionUsedHoursChart && Number.isFinite(creativeState.subscriptionUsedHoursYear)) {
        subscriptionUsedHoursChart.dataset.usedHoursYear = String(creativeState.subscriptionUsedHoursYear);
      }
      applyClientFilters();
      renderSubscriptionUsedHoursChart(creativeState.subscriptionUsedHoursSeries);
      syncCreativeFilterPanelsFromPayload(payload);
      renderFilteredCreatives();
      updateMonthlyUtilizationChart();
      if (payload.selected_month) {
        applyMonthKeyToSelects(payload.selected_month);
      }
      // Dashboard is rendered: warm every card's daily hours in the
      // background (one bulk request) so expands are instant. Deliberately
      // AFTER the payload applies — it must never compete with the main load.
      warmDailyHours(payload.selected_month ?? getCombinedYm());
    } catch (error) {
      if (!controller.signal.aborted) {
        console.error("Failed to fetch creatives", error);
        const message =
          error instanceof Error && typeof error.message === "string" && error.message.trim()
            ? error.message
            : "Unable to load the selected month. Please try again.";
        showErrorBanner(message);
      }
    } finally {
      if (activeFetchController === controller) {
        activeFetchController = null;
        // Re-evaluate the active tab when finishing; if we're back on creatives, we can hide the overlay.
        const activeTabNow = getActiveTab();
        const isSalesTabActiveNow = activeTabNow === "sales";
        if (loadingOverlay && !isSalesTabActiveNow) {
          loadingOverlay.classList.add("hidden");
        }
        setLoadingState(false);
      }
    }
  };

  // Local mutations (e.g. the New Joiner inclusion toggle) change server-side
  // math: the cached month payloads no longer match and must be dropped.
  const clearMonthPayloadCache = () => monthPayloadCache.clear();

  return { fetchCreatives, buildApiUrl, clearMonthPayloadCache };
}
