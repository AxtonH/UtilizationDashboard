document.addEventListener("DOMContentLoaded", () => {
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
  const COLLAPSIBLE_SECTIONS = {
    external: {
      selector: '[data-collapsible-section="external"]',
      contentSelector: "[data-collapsible-content]",
    },
    subscription: {
      selector: '[data-collapsible-section="subscription"]',
      contentSelector: "[data-collapsible-content]",
    },
    "sales-overview": {
      selector: '[data-collapsible-section="sales-overview"]',
      contentSelector: "[data-collapsible-content]",
    },
    "subscription-overview": {
      selector: '[data-collapsible-section="subscription-overview"]',
      contentSelector: "[data-collapsible-content]",
    },
    "subscription-used-hours": {
      selector: '[data-collapsible-section="subscription-used-hours"]',
      contentSelector: "[data-collapsible-content]",
    },
    "subscription-top-clients": {
      selector: '[data-collapsible-section="subscription-top-clients"]',
      contentSelector: "[data-collapsible-content]",
    },
    "pool-external-summary": {
      selector: '[data-collapsible-section="pool-external-summary"]',
      contentSelector: "[data-collapsible-content]",
    },
    "company-utilization": {
      selector: '[data-collapsible-section="company-utilization"]',
      contentSelector: "[data-collapsible-content]",
    },
    "creatives-time-cards": {
      selector: '[data-collapsible-section="creatives-time-cards"]',
      contentSelector: "[data-collapsible-content]",
    },
    "creative-overview": {
      selector: '[data-collapsible-section="creative-overview"]',
      contentSelector: "[data-collapsible-content]",
    },
    "monthly-utilization": {
      selector: '[data-collapsible-section="monthly-utilization"]',
      contentSelector: "[data-collapsible-content]",
    },
  };
  const companySummarySection = document.querySelector("[data-company-summary]");
  const summaryProjectsValue = companySummarySection?.querySelector("[data-summary-projects]");
  const summaryHoursValue = companySummarySection?.querySelector("[data-summary-hours]");
  const summaryRevenueValue = companySummarySection?.querySelector("[data-summary-revenue]");
  const monthSelect = document.querySelector("[data-month-select]");
  const monthLabel = document.querySelector("[data-month-label]");
  const refreshButton = document.querySelector("[data-creatives-refresh]");
  const marketFilterButtons = document.querySelectorAll("[data-creative-filter='market']");
  const poolFilterButtons = document.querySelectorAll("[data-creative-filter='pool']");
  const filterResetButton = document.querySelector("[data-creative-filter-reset]");
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
  const poolLabelMap = new Map();

  const registerPoolLabel = (slug, label) => {
    if (!slug) {
      return;
    }
    const key = String(slug).toLowerCase();
    if (poolLabelMap.has(key)) {
      return;
    }
    const resolvedLabel =
      typeof label === "string" && label.trim().length > 0
        ? label.trim()
        : key
          .split(/[-_]/)
          .filter(Boolean)
          .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
          .join(" ");
    poolLabelMap.set(key, resolvedLabel);
  };

  const registerPoolLabelsFromData = (pools) => {
    if (!Array.isArray(pools)) {
      return;
    }
    pools.forEach((pool) => {
      const slug = pool?.slug ?? pool?.name ?? null;
      if (!slug) {
        return;
      }
      const label = pool?.name ?? pool?.label ?? pool?.slug ?? "";
      registerPoolLabel(slug, label);
    });
  };

  const getPoolLabel = (slug) => {
    if (!slug) {
      return "";
    }
    const key = String(slug).toLowerCase();
    if (!poolLabelMap.has(key)) {
      registerPoolLabel(slug, "");
    }
    return poolLabelMap.get(key) ?? String(slug);
  };

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

  const POOL_DEFINITIONS = [
    { slug: "ksa", tag: "ksa" },
    { slug: "uae", tag: "uae" },
  ];
  const CLIENT_POOL_DEFINITIONS = [
    { slug: "ksa", label: "KSA", tag: "ksa" },
    { slug: "uae", label: "UAE", tag: "uae", aliases: ["adeo"] },
  ];
  const CLIENT_POOL_MATCHERS = CLIENT_POOL_DEFINITIONS.map((definition) => {
    const tokens = new Set();
    if (typeof definition.slug === "string" && definition.slug.trim()) {
      tokens.add(definition.slug.trim().toLowerCase());
    }
    if (typeof definition.tag === "string" && definition.tag.trim()) {
      tokens.add(definition.tag.trim().toLowerCase());
    }
    if (Array.isArray(definition.aliases)) {
      definition.aliases.forEach((alias) => {
        if (typeof alias === "string" && alias.trim()) {
          tokens.add(alias.trim().toLowerCase());
        }
      });
    }
    return { slug: definition.slug, label: definition.label, tokens: Array.from(tokens) };
  });
  const CLIENT_POOL_ALIAS_LOOKUP = (() => {
    const map = new Map();
    CLIENT_POOL_MATCHERS.forEach(({ slug, tokens }) => {
      tokens.forEach((token) => {
        if (!map.has(token)) {
          map.set(token, slug);
        }
      });
    });
    return map;
  })();
  CLIENT_POOL_DEFINITIONS.forEach((definition) => {
    registerPoolLabel(definition.slug, definition.label);
  });
  const normalizeClientPoolSlug = (value) => {
    if (value == null) {
      return null;
    }
    const normalized = String(value).trim().toLowerCase();
    if (!normalized) {
      return null;
    }
    if (CLIENT_POOL_ALIAS_LOOKUP.has(normalized)) {
      return CLIENT_POOL_ALIAS_LOOKUP.get(normalized);
    }
    for (const { slug, tokens } of CLIENT_POOL_MATCHERS) {
      if (tokens.some((token) => normalized.includes(token))) {
        return slug;
      }
    }
    return null;
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
    if (monthSelect) {
      monthSelect.disabled = isLoading;
      monthSelect.setAttribute("aria-disabled", isLoading ? "true" : "false");
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

  let activeFetchController = null;
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
  if (clientMarketGrid?.dataset?.clientAll) {
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
  if (clientSubscriptionGrid?.dataset?.clientSubscriptionAll) {
    try {
      const parsed = JSON.parse(clientSubscriptionGrid.dataset.clientSubscriptionAll);
      if (Array.isArray(parsed)) {
        clientSubscriptionAllData = parsed;
      }
    } catch (error) {
      console.warn("Failed to parse complete subscription market data", error);
    }
  }

  const parseDatasetJson = (raw, fallback) => {
    if (!raw) {
      return fallback;
    }
    try {
      const parsed = JSON.parse(raw);
      return parsed ?? fallback;
    } catch (error) {
      console.warn("Failed to parse dataset payload", error);
      return fallback;
    }
  };

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

  const formatClientHours = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || Math.abs(numeric) < 1e-6) {
      return "0h";
    }
    const rounded = Math.round(numeric * 10) / 10;
    if (Math.abs(rounded - Math.round(rounded)) < 0.1) {
      return `${Math.round(rounded).toLocaleString()}h`;
    }
    return `${rounded.toLocaleString(undefined, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    })}h`;
  };

  const matchesClientFilters = (entry, agreementFilter, accountFilter) => {
    if (agreementFilter) {
      const tokens = Array.isArray(entry?._agreement_tokens)
        ? entry._agreement_tokens
          .map((token) => (typeof token === "string" ? token.trim().toLowerCase() : ""))
          .filter(Boolean)
        : [];
      if (!tokens.includes(agreementFilter)) {
        return false;
      }
    }
    if (accountFilter) {
      const entryAccount =
        typeof entry?._account_type === "string" ? entry._account_type.trim().toLowerCase() : "";
      if (entryAccount !== accountFilter) {
        return false;
      }
    }
    return true;
  };

  const normalizeClientKey = (projectId, name, market) => {
    const clientName =
      typeof name === "string" && name.trim().length > 0 ? name.trim() : "Unassigned Client";
    const marketName =
      typeof market === "string" && market.trim().length > 0 ? market.trim() : "Unassigned Market";
    if (Number.isInteger(projectId)) {
      return {
        key: `id::${projectId}`,
        projectId,
        clientName,
        marketName,
      };
    }
    return {
      key: `name::${marketName.toLowerCase()}::${clientName.toLowerCase()}`,
      projectId: null,
      clientName,
      marketName,
    };
  };

  const extractSalesTopClients = (markets) => {
    const clients = [];
    markets.forEach((market) => {
      const marketName =
        typeof market?.market === "string" && market.market.trim().length > 0
          ? market.market
          : "Unassigned Market";
      (Array.isArray(market?.projects) ? market.projects : []).forEach((project) => {
        const revenueValue = Number(project?.total_aed ?? 0) || 0;
        const requestCount = Array.isArray(project?.sales_orders)
          ? project.sales_orders.length
          : 0;
        clients.push({
          project_id: Number.isInteger(project?.project_id) ? project.project_id : null,
          client_name:
            typeof project?.project_name === "string" && project.project_name.trim().length > 0
              ? project.project_name
              : "Unassigned Project",
          market: marketName,
          total_revenue_aed: revenueValue,
          request_count: requestCount,
        });
      });
    });
    return clients;
  };

  const extractSubscriptionTopClients = (markets) => {
    const combined = new Map();
    markets.forEach((market) => {
      const marketName =
        typeof market?.market === "string" && market.market.trim().length > 0
          ? market.market
          : "Unassigned Market";
      (Array.isArray(market?.subscriptions) ? market.subscriptions : []).forEach(
        (subscription) => {
          const { key, projectId, clientName, marketName: normalizedMarket } = normalizeClientKey(
            subscription?.project_id,
            subscription?.project_name,
            marketName
          );
          const entry =
            combined.get(key) ?? {
              project_id: projectId,
              client_name: clientName,
              market: normalizedMarket,
              total_revenue_aed: 0,
              request_count: 0,
            };
          entry.total_revenue_aed += Number(subscription?.aed_total ?? 0) || 0;
          const parentTasks = Array.isArray(subscription?.subscription_parent_tasks)
            ? subscription.subscription_parent_tasks
            : [];
          if (parentTasks.length > entry.request_count) {
            entry.request_count = parentTasks.length;
          }
          combined.set(key, entry);
        }
      );
    });
    return Array.from(combined.values())
      .map((entry) => ({
        ...entry,
        total_revenue_aed_display: formatAed(entry.total_revenue_aed),
      }))
      .sort((a, b) => {
        if (b.total_revenue_aed !== a.total_revenue_aed) {
          return b.total_revenue_aed - a.total_revenue_aed;
        }
        return a.client_name.localeCompare(b.client_name);
      });
  };

  const mergeClientTopClients = (subscriptionClients, salesClients, limit = 5) => {
    const combined = new Map();
    const ingest = (record) => {
      if (!record) {
        return;
      }
      const { key, projectId, clientName, marketName } = normalizeClientKey(
        record.project_id,
        record.client_name,
        record.market
      );
      const entry =
        combined.get(key) ?? {
          project_id: projectId,
          client_name: clientName,
          market: marketName,
          total_revenue_aed: 0,
          request_count: 0,
        };
      entry.total_revenue_aed += Number(record.total_revenue_aed ?? 0) || 0;
      entry.request_count += Number(record.request_count ?? 0) || 0;
      combined.set(key, entry);
    };
    (Array.isArray(subscriptionClients) ? subscriptionClients : []).forEach(ingest);
    (Array.isArray(salesClients) ? salesClients : []).forEach(ingest);
    return Array.from(combined.values())
      .map((entry) => ({
        ...entry,
        total_revenue_aed_display: formatAed(entry.total_revenue_aed),
      }))
      .sort((a, b) => {
        if (b.total_revenue_aed !== a.total_revenue_aed) {
          return b.total_revenue_aed - a.total_revenue_aed;
        }
        return a.client_name.localeCompare(b.client_name);
      })
      .slice(0, limit);
  };

  const inferClientPoolSlug = (tags, ...candidates) => {
    const tokens = [];
    if (Array.isArray(tags)) {
      tags.forEach((tag) => {
        if (typeof tag === "string" && tag.trim()) {
          tokens.push(tag.trim().toLowerCase());
        }
      });
    }
    candidates.forEach((candidate) => {
      if (!candidate) {
        return;
      }
      if (Array.isArray(candidate)) {
        candidate.forEach((item) => {
          if (typeof item === "string" && item.trim()) {
            tokens.push(item.trim().toLowerCase());
          }
        });
      } else if (typeof candidate === "string" && candidate.trim()) {
        tokens.push(candidate.trim().toLowerCase());
      }
    });
    for (const token of tokens) {
      const slug = normalizeClientPoolSlug(token);
      if (slug) {
        return slug;
      }
    }
    return null;
  };

  const computeClientPoolSummary = (salesMarkets, subscriptionMarkets) => {
    const pools = {};
    const totals = {
      projects: new Set(),
      used_hours: 0,
      sold_hours: 0,
      revenue: 0,
      order_keys: new Set(),
      sold_order_keys: new Set(),
      invoice_keys: new Set(),
    };
    CLIENT_POOL_DEFINITIONS.forEach((definition) => {
      pools[definition.slug] = {
        slug: definition.slug,
        label: definition.label,
        projects: new Set(),
        used_hours: 0,
        sold_hours: 0,
        revenue: 0,
        order_keys: new Set(),
        sold_order_keys: new Set(),
        invoice_keys: new Set(),
      };
    });

    (Array.isArray(salesMarkets) ? salesMarkets : []).forEach((market) => {
      const marketName =
        typeof market?.market === "string" && market.market.trim().length > 0
          ? market.market
          : "Unassigned Market";
      (Array.isArray(market?.projects) ? market.projects : []).forEach((project) => {
        const slug = inferClientPoolSlug(project?.tags, project?.project_name, marketName);
        if (!slug || !pools[slug]) {
          return;
        }
        const poolState = pools[slug];
        let projectId = project?.project_id;
        if (typeof projectId !== "number" && typeof projectId !== "string") {
          projectId = project?.project_name || project?.name || "";
        }
        if (projectId !== null && projectId !== undefined && projectId !== "") {
          const identifier = `sales::${projectId}`;
          poolState.projects.add(identifier);
          totals.projects.add(identifier);
        }
        const externalHours = Number(project?.total_external_hours ?? 0) || 0;
        const revenueValue = Number(project?.total_aed ?? 0) || 0;
        poolState.used_hours += externalHours;
        poolState.sold_hours += externalHours;
        poolState.revenue += revenueValue;
        totals.used_hours += externalHours;
        totals.sold_hours += externalHours;
        totals.revenue += revenueValue;
      });
    });

    (Array.isArray(subscriptionMarkets) ? subscriptionMarkets : []).forEach((market) => {
      const marketName =
        typeof market?.market === "string" && market.market.trim().length > 0
          ? market.market
          : "Unassigned Market";
      (Array.isArray(market?.subscriptions) ? market.subscriptions : []).forEach(
        (subscription) => {
          const slug = inferClientPoolSlug(
            subscription?.tags,
            subscription?.project_name,
            marketName
          );
          if (!slug || !pools[slug]) {
            return;
          }
          const poolState = pools[slug];
          // Treat each subscription order as distinct for pool counts
          const orderRefRaw =
            typeof subscription?.order_reference === "string"
              ? subscription.order_reference.trim()
              : "";
          const orderIdentifier = orderRefRaw || subscription?.project_name || marketName;
          if (orderIdentifier) {
            const identifier = `subscription::${orderIdentifier}`;
            poolState.projects.add(identifier);
            totals.projects.add(identifier);
          }
          const orderReference =
            typeof subscription?.order_reference === "string" &&
              subscription.order_reference.trim().length > 0
              ? subscription.order_reference.trim()
              : orderIdentifier || "";
          const usedKey = `${slug}::used::${orderReference}`;
          if (!poolState.order_keys.has(usedKey)) {
            const usedHours = Number(subscription?.subscription_used_hours ?? 0) || 0;
            poolState.used_hours += usedHours;
            totals.used_hours += usedHours;
            poolState.order_keys.add(usedKey);
            totals.order_keys.add(usedKey);
          }
          const soldKey = `${slug}::sold::${orderReference}`;
          if (!poolState.sold_order_keys.has(soldKey)) {
            const soldHours = Number(subscription?.monthly_billable_hours ?? 0) || 0;
            poolState.sold_hours += soldHours;
            totals.sold_hours += soldHours;
            poolState.sold_order_keys.add(soldKey);
            totals.sold_order_keys.add(soldKey);
          }
          const invoiceReference =
            typeof subscription?.invoice_reference === "string"
              ? subscription.invoice_reference.trim()
              : "";
          const invoiceKey = `${slug}::invoice::${orderReference}::${invoiceReference}`;
          if (!poolState.invoice_keys.has(invoiceKey)) {
            const revenueValue = Number(subscription?.aed_total ?? 0) || 0;
            poolState.revenue += revenueValue;
            totals.revenue += revenueValue;
            poolState.invoice_keys.add(invoiceKey);
            totals.invoice_keys.add(invoiceKey);
          }
        }
      );
    });

    const totalProjectCount = totals.projects.size;
    const totalUsedHours = totals.used_hours;
    const totalRevenue = totals.revenue;

    const poolCards = CLIENT_POOL_DEFINITIONS.map((definition) => {
      const state = pools[definition.slug];
      const projectCount = state?.projects.size ?? 0;
      const usedHours = state?.used_hours ?? 0;
      const revenueValue = state?.revenue ?? 0;
      const projectRatio = totalProjectCount ? projectCount / totalProjectCount : 0;
      const usedRatio = totalUsedHours ? usedHours / totalUsedHours : 0;
      const revenueRatio = totalRevenue ? revenueValue / totalRevenue : 0;
      return {
        slug: definition.slug,
        label: definition.label,
        metrics: {
          projects: {
            value: projectCount,
            display: `${projectCount.toLocaleString()}`,
            total_display: `${totalProjectCount.toLocaleString()}`,
            ratio: projectRatio,
          },
          used_hours: {
            value: usedHours,
            display: formatClientHours(usedHours),
            total_display: formatClientHours(totalUsedHours),
            ratio: usedRatio,
          },
          revenue: {
            value: revenueValue,
            display: formatAed(revenueValue),
            total_display: formatAed(totalRevenue),
            ratio: revenueRatio,
          },
        },
      };
    });

    return {
      pools: poolCards,
      totals: {
        projects: totalProjectCount,
        projects_display: `${totalProjectCount.toLocaleString()}`,
        used_hours: totalUsedHours,
        used_hours_display: formatClientHours(totalUsedHours),
        revenue: totalRevenue,
        revenue_display: formatAed(totalRevenue),
      },
    };
  };

  const normalizeClientPoolSummary = (summary) => {
    const base = CLIENT_POOL_DEFINITIONS.reduce((acc, definition) => {
      acc[definition.slug] = {
        slug: definition.slug,
        label: definition.label,
        metrics: {
          projects: { value: 0 },
          used_hours: { value: 0 },
          revenue: { value: 0 },
        },
      };
      return acc;
    }, {});

    const sourcePools = Array.isArray(summary?.pools) ? summary.pools : [];
    sourcePools.forEach((pool) => {
      const targetSlug = normalizeClientPoolSlug(pool?.slug ?? pool?.label ?? "");
      if (!targetSlug || !base[targetSlug]) {
        return;
      }
      const metrics = pool?.metrics ?? {};
      if (metrics.projects) {
        base[targetSlug].metrics.projects.value += Number(metrics.projects.value ?? 0) || 0;
      }
      if (metrics.used_hours) {
        base[targetSlug].metrics.used_hours.value += Number(metrics.used_hours.value ?? 0) || 0;
      }
      if (metrics.revenue) {
        base[targetSlug].metrics.revenue.value += Number(metrics.revenue.value ?? 0) || 0;
      }
    });

    const aggregatedPools = Object.values(base);
    const totals = aggregatedPools.reduce(
      (acc, pool) => {
        acc.projects += pool.metrics.projects.value;
        acc.used_hours += pool.metrics.used_hours.value;
        acc.revenue += pool.metrics.revenue.value;
        return acc;
      },
      { projects: 0, used_hours: 0, revenue: 0 }
    );

    aggregatedPools.forEach((pool) => {
      const projectValue = pool.metrics.projects.value;
      const usedValue = pool.metrics.used_hours.value;
      const revenueValue = pool.metrics.revenue.value;
      pool.metrics.projects = {
        value: projectValue,
        display: `${Math.round(projectValue).toLocaleString()}`,
        total_display: `${Math.round(totals.projects).toLocaleString()}`,
        ratio: totals.projects > 0 ? projectValue / totals.projects : 0,
      };
      pool.metrics.used_hours = {
        value: usedValue,
        display: formatClientHours(usedValue),
        total_display: formatClientHours(totals.used_hours),
        ratio: totals.used_hours > 0 ? usedValue / totals.used_hours : 0,
      };
      pool.metrics.revenue = {
        value: revenueValue,
        display: formatAed(revenueValue),
        total_display: formatAed(totals.revenue),
        ratio: totals.revenue > 0 ? revenueValue / totals.revenue : 0,
      };
    });

    return {
      pools: aggregatedPools,
      totals: {
        projects: totals.projects,
        projects_display: `${Math.round(totals.projects).toLocaleString()}`,
        used_hours: totals.used_hours,
        used_hours_display: formatClientHours(totals.used_hours),
        revenue: totals.revenue,
        revenue_display: formatAed(totals.revenue),
      },
    };
  };

  const buildFilteredClientData = (salesMarkets, subscriptionMarkets, filters) => {
    const agreementFilter =
      typeof filters?.agreementType === "string" && filters.agreementType.trim().length > 0
        ? filters.agreementType.trim().toLowerCase()
        : "";
    const accountFilter =
      typeof filters?.accountType === "string" && filters.accountType.trim().length > 0
        ? filters.accountType.trim().toLowerCase()
        : "";

    const filteredSales = [];
    let totalProjects = 0;
    let totalExternalHours = 0;
    let totalRevenue = 0;
    let totalInvoices = 0;

    (Array.isArray(salesMarkets) ? salesMarkets : []).forEach((market) => {
      const projects = Array.isArray(market?.projects) ? market.projects : [];
      const matchingProjects = projects.filter((project) =>
        matchesClientFilters(project, agreementFilter, accountFilter)
      );
      if (matchingProjects.length === 0) {
        return;
      }
      const marketHours = matchingProjects.reduce(
        (sum, project) => sum + (Number(project?.total_external_hours ?? 0) || 0),
        0
      );
      const marketRevenue = matchingProjects.reduce(
        (sum, project) => sum + (Number(project?.total_aed ?? 0) || 0),
        0
      );
      const marketInvoices = matchingProjects.reduce((sum, project) => {
        const orders = Array.isArray(project?.sales_orders) ? project.sales_orders : [];
        return sum + orders.length;
      }, 0);
      const marketLabel =
        typeof market?.market === "string" && market.market.trim().length > 0
          ? market.market
          : "Unassigned Market";
      filteredSales.push({
        market: marketLabel,
        projects: matchingProjects,
        total_external_hours: marketHours,
        total_external_hours_display: formatClientHours(marketHours),
        total_aed: marketRevenue,
        total_aed_display: formatAed(marketRevenue),
        total_invoices: marketInvoices,
      });
      totalProjects += matchingProjects.length;
      totalExternalHours += marketHours;
      totalRevenue += marketRevenue;
      totalInvoices += marketInvoices;
    });

    const salesSummary = {
      total_projects: totalProjects,
      total_external_hours: totalExternalHours,
      total_external_hours_display: formatClientHours(totalExternalHours),
      total_revenue_aed: totalRevenue,
      total_revenue_aed_display: formatAed(totalRevenue),
      total_invoices: totalInvoices,
    };

    const filteredSubscriptions = [];
    let totalMonthlyHours = 0;
    let totalSubscriptionUsedHours = 0;
    let totalSubscriptionRevenue = 0;
    let subscriptionTotalCount = 0;
    let totalParentTasks = 0;

    (Array.isArray(subscriptionMarkets) ? subscriptionMarkets : []).forEach((market) => {
      const subscriptions = Array.isArray(market?.subscriptions) ? market.subscriptions : [];
      const matchingSubscriptions = subscriptions.filter((subscription) =>
        matchesClientFilters(subscription, agreementFilter, accountFilter)
      );
      if (matchingSubscriptions.length === 0) {
        return;
      }
      // Deduplicate by order reference within a market to avoid duplicate cards
      const orderMap = new Map();
      matchingSubscriptions.forEach((subscription) => {
        const reference =
          typeof subscription?.order_reference === "string" &&
            subscription.order_reference.trim().length > 0
            ? subscription.order_reference.trim()
            : (subscription?.project_name || "");
        if (reference && !orderMap.has(reference)) {
          orderMap.set(reference, subscription);
        }
      });
      const dedupedSubscriptions = Array.from(orderMap.values());
      const marketMonthlyHours = dedupedSubscriptions.reduce(
        (sum, subscription) => sum + (Number(subscription?.monthly_billable_hours ?? 0) || 0),
        0
      );
      const marketUsedHours = dedupedSubscriptions.reduce(
        (sum, subscription) => sum + (Number(subscription?.subscription_used_hours ?? 0) || 0),
        0
      );
      const marketRevenue = dedupedSubscriptions.reduce(
        (sum, subscription) => sum + (Number(subscription?.aed_total ?? 0) || 0),
        0
      );
      // Count parent tasks for this market
      const marketParentTasks = dedupedSubscriptions.reduce((sum, subscription) => {
        const parentTasks = Array.isArray(subscription?.subscription_parent_tasks)
          ? subscription.subscription_parent_tasks
          : [];
        return sum + parentTasks.length;
      }, 0);
      const marketLabel =
        typeof market?.market === "string" && market.market.trim().length > 0
          ? market.market
          : "Unassigned Market";
      // Count one card per unique order reference
      subscriptionTotalCount += dedupedSubscriptions.length;
      filteredSubscriptions.push({
        market: marketLabel,
        subscriptions: dedupedSubscriptions,
        total_monthly_hours: marketMonthlyHours,
        total_monthly_hours_display: formatClientHours(marketMonthlyHours),
        total_aed: marketRevenue,
        total_aed_display: formatAed(marketRevenue),
        total_subscription_used_hours: marketUsedHours,
        total_subscription_used_hours_display: formatClientHours(marketUsedHours),
      });
      totalMonthlyHours += marketMonthlyHours;
      totalSubscriptionUsedHours += marketUsedHours;
      totalSubscriptionRevenue += marketRevenue;
      totalParentTasks += marketParentTasks;
    });

    const subscriptionSummary = {
      total_subscriptions: subscriptionTotalCount,
      total_monthly_hours: totalMonthlyHours,
      total_monthly_hours_display: formatClientHours(totalMonthlyHours),
      total_revenue_aed: totalSubscriptionRevenue,
      total_revenue_aed_display: formatAed(totalSubscriptionRevenue),
      total_subscription_used_hours: totalSubscriptionUsedHours,
      total_subscription_used_hours_display: formatClientHours(totalSubscriptionUsedHours),
      total_parent_tasks: totalParentTasks,
    };

    const salesTopClients = extractSalesTopClients(filteredSales);
    const subscriptionTopClients = extractSubscriptionTopClients(filteredSubscriptions);
    const mergedTopClients = mergeClientTopClients(subscriptionTopClients, salesTopClients);
    const poolSummary = computeClientPoolSummary(filteredSales, filteredSubscriptions);

    return {
      salesMarkets: filteredSales,
      salesSummary,
      subscriptionMarkets: filteredSubscriptions,
      subscriptionSummary,
      topClients: mergedTopClients,
      poolSummary,
    };
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

  function formatHours(value) {
    const totalMinutes = Math.round((Number(value) || 0) * 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    if (minutes === 0) {
      return `${hours}h`;
    }
    return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
  }

  function formatAed(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      if (typeof value === "string" && value.trim()) {
        return value;
      }
      return "0.00 AED";
    }
    return `${numeric.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} AED`;
  }

  const ensureSectionState = (key) => {
    if (!creativeState.sectionCollapsed) {
      creativeState.sectionCollapsed = {};
    }
    if (typeof creativeState.sectionCollapsed[key] !== "boolean") {
      creativeState.sectionCollapsed[key] = false;
    }
  };

  const applySectionCollapsedState = (key) => {
    const config = COLLAPSIBLE_SECTIONS[key];
    if (!config) {
      return;
    }
    const section = document.querySelector(config.selector);
    if (!section) {
      return;
    }
    ensureSectionState(key);
    const collapsed = Boolean(creativeState.sectionCollapsed[key]);
    section.dataset.sectionCollapsed = collapsed ? "true" : "false";
    const content = section.querySelector(config.contentSelector);
    if (content) {
      content.classList.toggle("hidden", collapsed);
    }
    const trigger = section.querySelector(`[data-collapsible-toggle="${key}"]`);
    if (trigger) {
      trigger.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
    const icon = section.querySelector(`[data-collapsible-icon="${key}"]`);
    if (icon) {
      icon.textContent = collapsed ? "expand_more" : "expand_less";
    }
  };

  const initializeCollapsibleSections = () => {
    Object.keys(COLLAPSIBLE_SECTIONS).forEach((key) => {
      const config = COLLAPSIBLE_SECTIONS[key];
      const section = document.querySelector(config.selector);
      if (!section) {
        return;
      }
      const trigger = section.querySelector(`[data-collapsible-toggle="${key}"]`);
      if (!trigger) {
        return;
      }
      if (section.dataset.collapsibleInit === "true") {
        applySectionCollapsedState(key);
        return;
      }
      section.dataset.collapsibleInit = "true";
      trigger.addEventListener("click", () => {
        ensureSectionState(key);
        creativeState.sectionCollapsed[key] = !creativeState.sectionCollapsed[key];
        applySectionCollapsedState(key);

        // Resize chart if it's the monthly utilization chart
        if (key === "monthly-utilization" && monthlyUtilizationChart) {
          setTimeout(() => {
            monthlyUtilizationChart.resize();
          }, 100);
        }
      });
      applySectionCollapsedState(key);
    });
  };

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

  const computeStats = (creatives) => {
    if (!Array.isArray(creatives) || creatives.length === 0) {
      return { total: 0, available: 0, active: 0 };
    }

    return creatives.reduce(
      (acc, creative) => {
        acc.total += 1;
        if ((Number(creative?.available_hours) || 0) > 0) {
          acc.available += 1;
        }
        if ((Number(creative?.logged_hours) || 0) > 0) {
          acc.active += 1;
        }
        return acc;
      },
      { total: 0, available: 0, active: 0 }
    );
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

  const computeAggregates = (creatives) => {
    if (!Array.isArray(creatives) || creatives.length === 0) {
      return { planned: 0, logged: 0, available: 0, max: 0 };
    }

    const totals = creatives.reduce(
      (acc, creative) => {
        acc.planned += Number(creative?.planned_hours) || 0;
        acc.logged += Number(creative?.logged_hours) || 0;
        acc.available += Number(creative?.available_hours) || 0;
        return acc;
      },
      { planned: 0, logged: 0, available: 0 }
    );

    const max = Math.max(totals.planned, totals.logged, totals.available, 0);
    return { ...totals, max };
  };

  const calculateExternalHours = (clientMarketsAll, clientSubscriptionsAll, selectedMarkets, selectedPools) => {
    // Hide if pool filter is active (with or without market filter)
    if (selectedPools && selectedPools.length > 0) {
      return { hours: 0, shouldShow: false };
    }

    // If no markets data, don't show
    if (!Array.isArray(clientMarketsAll) || clientMarketsAll.length === 0) {
      return { hours: 0, shouldShow: false };
    }

    let totalHours = 0;

    // Normalize market names for comparison
    const normalizeMarketName = (marketName) => {
      if (!marketName) return null;
      const normalized = String(marketName).trim().toLowerCase();
      if (normalized === "ksa" || normalized.includes("ksa")) return "ksa";
      if (normalized === "uae" || normalized.includes("uae")) return "uae";
      return normalized;
    };

    // Determine which markets to include
    let marketsToInclude = null;
    if (selectedMarkets && selectedMarkets.length > 0) {
      marketsToInclude = selectedMarkets.map((m) => normalizeMarketName(m));
    }

    // Sum external hours from sales orders
    clientMarketsAll.forEach((market) => {
      const marketName = market?.market;
      const normalizedMarket = normalizeMarketName(marketName);

      // If market filter is active, only include selected markets
      if (marketsToInclude && !marketsToInclude.includes(normalizedMarket)) {
        return;
      }

      const projects = market?.projects || [];
      projects.forEach((project) => {
        totalHours += Number(project?.total_external_hours || 0);
      });
    });

    // Sum subscription used hours if available
    if (Array.isArray(clientSubscriptionsAll) && clientSubscriptionsAll.length > 0) {
      clientSubscriptionsAll.forEach((market) => {
        const marketName = market?.market;
        const normalizedMarket = normalizeMarketName(marketName);

        // If market filter is active, only include selected markets
        if (marketsToInclude && !marketsToInclude.includes(normalizedMarket)) {
          return;
        }

        const subscriptions = market?.subscriptions || [];
        subscriptions.forEach((subscription) => {
          totalHours += Number(subscription?.subscription_used_hours || 0);
        });
      });
    }

    return { hours: totalHours, shouldShow: true };
  };

  // Update headcount metrics
  const updateTasks = (tasksStats) => {
    if (!tasksStats) return;

    const totalEl = document.querySelector("[data-tasks-total]");
    const totalTasksEl = document.querySelector("[data-total-tasks-value]");
    const adhocEl = document.querySelector("[data-tasks-adhoc]");
    const frameworkEl = document.querySelector("[data-tasks-framework]");
    const retainerEl = document.querySelector("[data-tasks-retainer]");

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

    if (adhocEl) {
      adhocEl.textContent = tasksStats.adhoc || 0;
    }

    if (frameworkEl) {
      frameworkEl.textContent = tasksStats.framework || 0;
    }

    if (retainerEl) {
      retainerEl.textContent = tasksStats.retainer || 0;
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

    const totalEl = document.querySelector("[data-headcount-total]");
    const availableEl = document.querySelector("[data-headcount-available]");
    const newJoinersEl = document.querySelector("[data-headcount-new-joiners]");
    const offboardedEl = document.querySelector("[data-headcount-offboarded]");

    // Store the initial server-rendered total value on first call
    // This prevents JavaScript from overwriting it with filtered data
    if (totalEl && !totalEl.dataset.serverTotal) {
      totalEl.dataset.serverTotal = totalEl.textContent.trim();
    }

    if (totalEl) {
      // Always use the server-rendered total instead of filtered total
      const serverTotal = totalEl.dataset.serverTotal || headcount.total || 0;
      totalEl.textContent = serverTotal;
    }

    if (availableEl) {
      availableEl.textContent = headcount.available || 0;
    }

    if (newJoinersEl) {
      const count = headcount.new_joiners_count || 0;
      newJoinersEl.textContent = count;

      // Update native browser tooltip with joiner names
      const names = headcount.new_joiners_names || [];
      const tooltipText = names.length > 0 ? names.join(", ") : "No new joiners";
      newJoinersEl.setAttribute("title", tooltipText);
      newJoinersEl.removeAttribute("data-tooltip-content");
    }

    if (offboardedEl) {
      const count = headcount.offboarded_count || 0;
      offboardedEl.textContent = count;

      // Update native browser tooltip with offboarded names
      const names = headcount.offboarded_names || [];
      const tooltipText = names.length > 0 ? names.join(", ") : "No offboarded creatives";
      offboardedEl.setAttribute("title", tooltipText);
      offboardedEl.removeAttribute("data-tooltip-content");
    }
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
          label: "Utilization %",
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
                return `Utilization: ${context.parsed.y.toFixed(1)}%`;
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

    // Get selected filters using the same helper functions as other components
    const selectedMarkets = getSelectedMarkets();
    const selectedPools = getSelectedPools();

    // Process and aggregate data with filtering
    const chartData = monthlyData.map(monthData => {
      const creatives = monthData.creatives || [];

      // Filter creatives based on selected filters
      // When NO filters are selected, include ALL creatives (company-wide utilization)
      const filteredCreatives = creatives.filter(creative => {
        // Market filter - only apply if markets are selected
        if (selectedMarkets.length > 0) {
          // If creative has no market_slug, exclude it when filtering by market
          if (!creative.market_slug) {
            return false;
          }
          // If creative's market is not in selected markets, exclude it
          if (!selectedMarkets.includes(creative.market_slug)) {
            return false;
          }
        }

        // Pool filter - only apply if pools are selected
        if (selectedPools.length > 0) {
          // If creative has no pool_name, exclude it when filtering by pool
          if (!creative.pool_name) {
            return false;
          }
          // If creative's pool is not in selected pools, exclude it
          if (!selectedPools.includes(creative.pool_name)) {
            return false;
          }
        }

        // Include creative if no filters are selected, or if it passes all active filters
        return true;
      });

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

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || 'Failed to refresh data');
      }

      const data = await response.json();

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

    // Calculate external hours based on current filters
    const selectedMarkets = getSelectedMarkets();
    const selectedPools = getSelectedPools();
    const externalHoursData = calculateExternalHours(
      creativeState.clientMarketsAll || [],
      creativeState.clientSubscriptionsAll || [],
      selectedMarkets,
      selectedPools
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
      if (externalHoursData.shouldShow) {
        externalHoursContainer.style.display = "flex";
      } else {
        externalHoursContainer.style.display = "none";
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
        display: formatHours(externalHoursData.hours),
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

    // Update new metrics list (Available, Planned, Logged) with raw numbers
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

  const computePoolStats = (creatives) => {
    const base = POOL_DEFINITIONS.reduce((acc, pool) => {
      acc[pool.slug] = {
        total_creatives: 0,
        available_creatives: 0,
        active_creatives: 0,
        available_hours: 0,
        available_hours_display: formatHours(0),
        planned_hours: 0,
        planned_hours_display: formatHours(0),
        logged_hours: 0,
        logged_hours_display: formatHours(0),
      };
      return acc;
    }, {});

    if (!Array.isArray(creatives) || creatives.length === 0) {
      return base;
    }

    creatives.forEach((creative) => {
      // Use market_slug instead of tags
      const marketSlug = creative.market_slug;
      if (!marketSlug) {
        return;
      }

      const bucket = base[marketSlug];
      if (!bucket) {
        return;
      }

      bucket.total_creatives += 1;
      if ((Number(creative?.available_hours) || 0) > 0) {
        bucket.available_creatives += 1;
      }
      if ((Number(creative?.logged_hours) || 0) > 0) {
        bucket.active_creatives += 1;
      }
      bucket.available_hours += Number(creative?.available_hours) || 0;
      bucket.planned_hours += Number(creative?.planned_hours) || 0;
      bucket.logged_hours += Number(creative?.logged_hours) || 0;
    });

    Object.values(base).forEach((pool) => {
      pool.available_hours_display = formatHours(pool.available_hours);
      pool.planned_hours_display = formatHours(pool.planned_hours);
      pool.logged_hours_display = formatHours(pool.logged_hours);
    });

    return base;
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

  // Pool filter removed - all creatives are displayed (they're already filtered by market in backend)
  const filterCreativesClientSide = (creatives, selectedMarkets, selectedPools) => {
    if (!selectedMarkets.length && !selectedPools.length) {
      return creatives;
    }

    return creatives.filter(creative => {
      const marketSlug = creative.market_slug;
      const poolName = creative.pool_name;

      // Market filter: if markets selected, creative must match one
      const marketMatch = selectedMarkets.length === 0 || selectedMarkets.includes(marketSlug);

      // Pool filter: if pools selected, creative must match one
      const poolMatch = selectedPools.length === 0 || (poolName && selectedPools.includes(poolName));

      // Both filters must pass (AND logic)
      return marketMatch && poolMatch;
    });
  };

  const computeFilteredStats = (filteredCreatives) => {
    const total = filteredCreatives.length;
    let available = 0;
    let active = 0;

    filteredCreatives.forEach(creative => {
      const availableHours = Number(creative.available_hours || 0);
      if (availableHours > 0) {
        available++;
      }
      const loggedHours = Number(creative.logged_hours || 0);
      if (loggedHours > 0) {
        active++;
      }
    });

    return { total, available, active };
  };

  const parseDateValue = (value) => {
    if (value instanceof Date) {
      return value;
    }
    if (typeof value === "string") {
      const normalized = value.split("T")[0];
      const [yearStr, monthStr, dayStr] = normalized.split("-");
      const year = Number(yearStr);
      const month = Number(monthStr);
      const day = Number(dayStr);
      if (
        Number.isInteger(year) &&
        Number.isInteger(month) &&
        Number.isInteger(day) &&
        month >= 1 &&
        month <= 12 &&
        day >= 1 &&
        day <= 31
      ) {
        const parsed = new Date(Date.UTC(year, month - 1, day));
        if (!Number.isNaN(parsed.getTime())) {
          return parsed;
        }
      }
      const fallback = new Date(value);
      if (!Number.isNaN(fallback.getTime())) {
        return fallback;
      }
    }
    return null;
  };

  const parseMonthBounds = (monthValue) => {
    if (typeof monthValue !== "string") {
      return null;
    }
    const [yearStr, monthStr] = monthValue.split("-");
    const year = Number(yearStr);
    const month = Number(monthStr);
    if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
      return null;
    }
    const start = new Date(Date.UTC(year, month - 1, 1));
    const end = month === 12 ? new Date(Date.UTC(year + 1, 0, 1)) : new Date(Date.UTC(year, month, 1));
    return { start, end };
  };

  const isWithinMonth = (dateValue, start, end) => {
    if (!(dateValue instanceof Date) || Number.isNaN(dateValue.getTime()) || !start || !end) {
      return false;
    }
    return dateValue >= start && dateValue < end;
  };

  const computeFilteredHeadcount = (filteredCreatives, monthValue) => {
    if (!Array.isArray(filteredCreatives)) {
      return null;
    }

    const bounds = parseMonthBounds(monthValue);
    const monthStart = bounds?.start;
    const monthEnd = bounds?.end;

    const availableCreatives = filteredCreatives.filter(
      (creative) =>
        (creative?.market_display || creative?.pool_display) &&
        (Number(creative?.available_hours || 0) > Number(creative?.planned_hours || 0))
    );
    const availableCount = availableCreatives.length;

    // Total creatives should be all filtered creatives with a market/pool, ignoring the hours condition
    const totalCreativesList = filteredCreatives.filter(
      (creative) => creative?.market_display || creative?.pool_display
    );
    const totalCount = totalCreativesList.length;

    const sortedByName = (list) =>
      list.slice().sort((a, b) => (a?.name || "").localeCompare(b?.name || ""));

    const newJoiners = monthStart && monthEnd
      ? sortedByName(
        availableCreatives.filter((creative) => {
          const joiningDate = parseDateValue(creative?.x_studio_joining_date);
          return joiningDate ? isWithinMonth(joiningDate, monthStart, monthEnd) : false;
        })
      )
      : [];

    const offboarded = monthStart && monthEnd
      ? sortedByName(
        filteredCreatives.filter((creative) => {
          const endDate = parseDateValue(creative?.x_studio_rf_contract_end_date);
          return endDate ? isWithinMonth(endDate, monthStart, monthEnd) : false;
        })
      )
      : [];

    return {
      total: totalCount,
      available: availableCount,
      new_joiners: newJoiners,
      new_joiners_count: newJoiners.length,
      new_joiners_names: newJoiners.map((creative) => creative?.name || "Unknown"),
      offboarded,
      offboarded_count: offboarded.length,
      offboarded_names: offboarded.map((creative) => creative?.name || "Unknown"),
    };
  };

  const matchesFiltersForTotals = (marketSlug, poolName, marketFilterSet, poolFilterSet) => {
    if (marketFilterSet) {
      if (typeof marketSlug !== "string" || !marketFilterSet.has(marketSlug.toLowerCase())) {
        return false;
      }
    }
    if (poolFilterSet) {
      if (typeof poolName !== "string" || !poolFilterSet.has(poolName)) {
        return false;
      }
    }
    return true;
  };

  const sumPreviousTotalsForFilters = (creatives, marketFilterSet, poolFilterSet) => {
    if (!Array.isArray(creatives) || creatives.length === 0) {
      return null;
    }
    let hasData = false;
    const totals = { planned: 0.0, logged: 0.0, available: 0.0 };
    creatives.forEach((creative) => {
      const prevMarket = creative?.previous_market_slug;
      const prevPool = creative?.previous_pool_name;
      if (!matchesFiltersForTotals(prevMarket, prevPool, marketFilterSet, poolFilterSet)) {
        return;
      }
      const prevAvailableRaw = creative?.previous_available_hours;
      const prevPlannedRaw = creative?.previous_planned_hours;
      const prevLoggedRaw = creative?.previous_logged_hours;
      const hasRawValue =
        prevAvailableRaw !== null && prevAvailableRaw !== undefined ||
        prevPlannedRaw !== null && prevPlannedRaw !== undefined ||
        prevLoggedRaw !== null && prevLoggedRaw !== undefined;
      if (!hasRawValue) {
        return;
      }
      hasData = true;
      const prevAvailable =
        prevAvailableRaw === null || prevAvailableRaw === undefined
          ? null
          : Number(prevAvailableRaw);
      const prevPlanned =
        prevPlannedRaw === null || prevPlannedRaw === undefined ? null : Number(prevPlannedRaw);
      const prevLogged =
        prevLoggedRaw === null || prevLoggedRaw === undefined ? null : Number(prevLoggedRaw);
      if (Number.isFinite(prevAvailable)) {
        totals.available += prevAvailable;
      }
      if (Number.isFinite(prevPlanned)) {
        totals.planned += prevPlanned;
      }
      if (Number.isFinite(prevLogged)) {
        totals.logged += prevLogged;
      }
    });
    return hasData ? totals : null;
  };

  const buildComparisonFromTotals = (currentTotals, previousTotals) => {
    if (!previousTotals) {
      return null;
    }
    const change = (currentValue, previousValue) => {
      if (previousValue === 0) {
        if (currentValue === 0) {
          return null;
        }
        return 100;
      }
      return ((currentValue - previousValue) / previousValue) * 100;
    };
    const currentAvailable = currentTotals.available;
    const currentPlanned = currentTotals.planned;
    const currentLogged = currentTotals.logged;
    const previousAvailable = previousTotals.available;
    const previousPlanned = previousTotals.planned;
    const previousLogged = previousTotals.logged;
    const currentUtilization =
      currentAvailable > 0 ? (currentLogged / currentAvailable) * 100 : 0;
    const previousUtilization =
      previousAvailable > 0 ? (previousLogged / previousAvailable) * 100 : 0;
    const currentBooking = currentAvailable > 0 ? (currentPlanned / currentAvailable) * 100 : 0;
    const previousBooking =
      previousAvailable > 0 ? (previousPlanned / previousAvailable) * 100 : 0;
    return {
      available: {
        value: currentAvailable,
        change: change(currentAvailable, previousAvailable),
      },
      planned: {
        value: currentPlanned,
        change: change(currentPlanned, previousPlanned),
      },
      logged: {
        value: currentLogged,
        change: change(currentLogged, previousLogged),
      },
      utilization: {
        value: currentUtilization,
        change: change(currentUtilization, previousUtilization),
      },
      booking_capacity: {
        value: currentBooking,
        change: change(currentBooking, previousBooking),
      },
    };
  };

  const computeFilteredAggregates = (
    filteredCreatives,
    allCreatives,
    selectedMarkets,
    selectedPools
  ) => {
    const totals = { planned: 0.0, logged: 0.0, available: 0.0 };

    filteredCreatives.forEach(creative => {
      totals.planned += Number(creative.planned_hours || 0);
      totals.logged += Number(creative.logged_hours || 0);
      totals.available += Number(creative.available_hours || 0);
    });

    const maxValue = Math.max(totals.planned, totals.logged, totals.available);
    const marketFilterSet =
      Array.isArray(selectedMarkets) && selectedMarkets.length > 0
        ? new Set(selectedMarkets.map((value) => value.toLowerCase()))
        : null;
    const poolFilterSet =
      Array.isArray(selectedPools) && selectedPools.length > 0 ? new Set(selectedPools) : null;

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
        ? sumPreviousTotalsForFilters(allCreatives, marketFilterSet, poolFilterSet)
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

  const computeFilteredTasksStats = (tasksStats, filteredCreatives) => {
    if (!tasksStats || !Array.isArray(tasksStats.tasks)) {
      return tasksStats || null;
    }
    if (!filteredCreatives || filteredCreatives.length === 0) {
      // If no filtered creatives, return empty stats
      return {
        total: 0,
        adhoc: 0,
        framework: 0,
        retainer: 0,
        average_per_creator: 0,
        by_market: {},
        project_ids: [],
        tasks: [],
        comparison: null,
        previous_total: null,
      };
    }
    // Create a Set of allowed creative IDs for fast lookup
    const allowedCreators = new Set(
      (filteredCreatives || []).map((c) => {
        // Handle both number and string IDs
        const id = c.id;
        if (typeof id === "number") return id;
        if (typeof id === "string") {
          const parsed = parseInt(id, 10);
          return isNaN(parsed) ? null : parsed;
        }
        return null;
      }).filter(id => id !== null && id > 0)
    );

    if (allowedCreators.size === 0) {
      // No valid creative IDs found
      return {
        total: 0,
        adhoc: 0,
        framework: 0,
        retainer: 0,
        average_per_creator: 0,
        by_market: {},
        project_ids: [],
        tasks: [],
        comparison: null,
        previous_total: null,
      };
    }

    // Filter tasks: include only tasks where at least one creator is in the filtered creatives list
    const filteredTasks = tasksStats.tasks.filter((task) => {
      const creators = Array.isArray(task.creator_ids) ? task.creator_ids : [];
      if (creators.length === 0) return false;
      // Check if any creator ID matches the allowed creators
      return creators.some((id) => {
        // Normalize ID to number for comparison
        const normalizedId = typeof id === "number" ? id : (typeof id === "string" ? parseInt(id, 10) : null);
        return normalizedId !== null && !isNaN(normalizedId) && allowedCreators.has(normalizedId);
      });
    });
    if (filteredTasks.length === 0) {
      return {
        total: 0,
        adhoc: 0,
        framework: 0,
        retainer: 0,
        average_per_creator: 0,
        by_market: {},
        project_ids: [],
        tasks: [],
      };
    }

    const categorize = (agreement, tags) => {
      const tokens = [];
      const addTokens = (raw) => {
        if (raw == null) return;
        if (typeof raw === "string") {
          tokens.push(...raw.split(/[,/&|]+/).map((p) => p.trim()).filter(Boolean));
        } else if (Array.isArray(raw)) {
          raw.forEach(addTokens);
        }
      };
      addTokens(agreement);
      addTokens(tags);
      const normalized = tokens.map((t) => t.toLowerCase());
      if (normalized.some((t) => t.includes("retainer") || t.includes("subscription") || t.includes("subscr"))) {
        return "retainer";
      }
      if (normalized.some((t) => t.includes("framework"))) {
        return "framework";
      }
      if (normalized.some((t) => t.includes("ad-hoc") || t.includes("adhoc") || t.includes("ad hoc"))) {
        return "ad-hoc";
      }
      return "other";
    };

    let total = 0;
    let adhoc = 0;
    let framework = 0;
    let retainer = 0;
    const marketCounts = {};
    const projectIds = new Set();
    const allParentTasks = new Set();

    // Sets to track unique parent tasks per category
    const adhocParentTasks = new Set();
    const frameworkParentTasks = new Set();
    const retainerParentTasks = new Set();

    filteredTasks.forEach((task) => {
      const category = categorize(task.agreement_type, task.tags);
      if (category === "ad-hoc") adhoc += 1;
      else if (category === "framework") framework += 1;
      else if (category === "retainer") retainer += 1;

      const market = (task.market || "").toString().trim();
      if (market) {
        marketCounts[market] = (marketCounts[market] || 0) + 1;
      }
      const pid = task.project_id;
      if (typeof pid === "number") {
        projectIds.add(pid);
      }

      // Aggregate parent tasks - only include tasks worked on by filtered creatives
      // Use parent_tasks_with_creators if available (new data structure),
      // otherwise fall back to parent_tasks (backwards compatibility)
      const parentTasksWithCreators = task.parent_tasks_with_creators;
      const currentTaskParentTasks = new Set();

      if (Array.isArray(parentTasksWithCreators)) {
        // New data structure: each entry has {task, creator_ids}
        // Only include parent tasks where at least one creator_id is in filteredCreatives
        const filteredCreativeIds = new Set(filteredCreatives.map(c => c.id));
        parentTasksWithCreators.forEach(ptData => {
          const taskName = ptData.task;
          const creatorIds = ptData.creator_ids || [];
          // Check if ANY of the creators who worked on this task are in our filtered list
          const hasMatchingCreator = creatorIds.some(creatorId => filteredCreativeIds.has(creatorId));
          if (hasMatchingCreator && taskName) {
            allParentTasks.add(taskName);
            currentTaskParentTasks.add(taskName);
          }
        });
      } else {
        // Fallback to old data structure (backwards compatibility)
        const parentTasks = Array.isArray(task.parent_tasks) ? task.parent_tasks : [];
        parentTasks.forEach(pt => {
          if (pt) {
            allParentTasks.add(pt);
            currentTaskParentTasks.add(pt);
          }
        });
      }

      // Add parent tasks to category sets
      if (category === "ad-hoc") {
        currentTaskParentTasks.forEach(pt => adhocParentTasks.add(pt));
      } else if (category === "framework") {
        currentTaskParentTasks.forEach(pt => frameworkParentTasks.add(pt));
      } else if (category === "retainer") {
        currentTaskParentTasks.forEach(pt => retainerParentTasks.add(pt));
      }

      total += 1;
    });

    // NOTE: Client-side parent task aggregation has a known limitation:
    // When a project has creatives from multiple pools and you filter by one pool,
    // ALL parent tasks from that project are included if ANY creative matches the filter.
    // This can result in overcounting parent tasks that belong only to creatives outside the filter.
    // For accurate parent task counts, the backend should recalculate when filters change.

    return {
      total,
      total_tasks: allParentTasks.size,
      adhoc,
      framework,
      retainer,
      adhoc_tasks: adhocParentTasks.size,
      framework_tasks: frameworkParentTasks.size,
      retainer_tasks: retainerParentTasks.size,
      average_per_creator: (filteredCreatives.length > 0 ? total / filteredCreatives.length : 0).toFixed(2) * 1,
      average_tasks_per_creator: (filteredCreatives.length > 0 ? allParentTasks.size / filteredCreatives.length : 0).toFixed(2) * 1,
      by_market: marketCounts,
      project_ids: Array.from(projectIds).sort(),
      parent_task_names: Array.from(allParentTasks).sort(),
      tasks: filteredTasks,
      comparison: null,
      tasks_comparison: null,
      previous_total: null,
      previous_total_tasks: null,
    };
  };

  const computeFilteredOvertimeStats = (overtimeStats, filteredCreatives) => {
    if (!overtimeStats || !Array.isArray(overtimeStats.requests)) {
      return overtimeStats || null;
    }
    if (!filteredCreatives || filteredCreatives.length === 0) {
      // If no filtered creatives, return empty stats
      return {
        total_hours: 0.0,
        total_hours_display: "0h",
        top_projects: [],
        requests: [],
      };
    }

    // Create a Set of allowed creative IDs for fast lookup
    const allowedCreators = new Set(
      (filteredCreatives || []).map((c) => {
        // Handle both number and string IDs
        const id = c.id;
        if (typeof id === "number") return id;
        if (typeof id === "string") {
          const parsed = parseInt(id, 10);
          return isNaN(parsed) ? null : parsed;
        }
        return null;
      }).filter(id => id !== null && id > 0)
    );

    if (allowedCreators.size === 0) {
      // No valid creative IDs found
      return {
        total_hours: 0.0,
        total_hours_display: "0h",
        top_projects: [],
        requests: [],
      };
    }

    // Filter requests: include only requests where creative_id matches filtered creatives
    const filteredRequests = overtimeStats.requests.filter((request) => {
      const creativeId = request.creative_id;
      if (creativeId === null || creativeId === undefined) {
        return false;  // Skip requests that couldn't be matched to a creative
      }
      // Normalize ID to number for comparison
      const normalizedId = typeof creativeId === "number" ? creativeId : (typeof creativeId === "string" ? parseInt(creativeId, 10) : null);
      return normalizedId !== null && !isNaN(normalizedId) && allowedCreators.has(normalizedId);
    });

    if (filteredRequests.length === 0) {
      return {
        total_hours: 0.0,
        total_hours_display: "0h",
        top_projects: [],
        requests: [],
      };
    }

    // Recalculate statistics from filtered requests
    const total_hours = filteredRequests.reduce((sum, req) => sum + (req.hours || 0), 0);

    // Group by project
    const projectHours = {};
    filteredRequests.forEach((req) => {
      const projectName = req.project_name || "Unassigned Project";
      projectHours[projectName] = (projectHours[projectName] || 0) + (req.hours || 0);
    });

    // Get top 5 projects
    const top_projects = Object.entries(projectHours)
      .map(([name, hours]) => ({
        project_name: name,
        hours: hours,
        hours_display: formatOvertimeHours(hours),
      }))
      .sort((a, b) => b.hours - a.hours)
      .slice(0, 5);

    return {
      total_hours: total_hours,
      total_hours_display: formatOvertimeHours(total_hours),
      top_projects: top_projects,
      requests: filteredRequests,
    };
  };

  const formatOvertimeHours = (hours) => {
    if (hours == 0) {
      return "0h";
    }
    if (hours < 1) {
      const minutes = Math.floor(hours * 60);
      return `${minutes}m`;
    }
    if (hours == Math.floor(hours)) {
      return `${Math.floor(hours)}h`;
    }
    return `${hours.toFixed(1)}h`;
  };

  const computeFilteredPoolStats = (filteredCreatives) => {
    const poolStatsMap = new Map();

    filteredCreatives.forEach(creative => {
      const marketSlug = creative.market_slug;
      if (!marketSlug) return;

      if (!poolStatsMap.has(marketSlug)) {
        poolStatsMap.set(marketSlug, {
          name: creative.market_display || marketSlug.toUpperCase(),
          slug: marketSlug,
          total_creatives: 0,
          available_creatives: 0,
          active_creatives: 0,
          available_hours: 0,
          planned_hours: 0,
          logged_hours: 0,
        });
      }

      const pool = poolStatsMap.get(marketSlug);
      pool.total_creatives++;

      const availableHours = Number(creative.available_hours || 0);
      if (availableHours > 0) {
        pool.available_creatives++;
      }
      pool.available_hours += availableHours;

      const loggedHours = Number(creative.logged_hours || 0);
      if (loggedHours > 0) {
        pool.active_creatives++;
      }
      pool.logged_hours += loggedHours;

      pool.planned_hours += Number(creative.planned_hours || 0);
    });

    const formatHours = (value) => {
      const totalMinutes = Math.round(value * 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      if (minutes === 0) {
        return `${hours}h`;
      }
      return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
    };

    return Array.from(poolStatsMap.values()).map(pool => ({
      ...pool,
      available_hours_display: formatHours(pool.available_hours),
      planned_hours_display: formatHours(pool.planned_hours),
      logged_hours_display: formatHours(pool.logged_hours),
    }));
  };

  const renderFilteredCreatives = () => {
    try {
      const allCreatives = Array.isArray(creativeState.creatives) ? creativeState.creatives : [];
      const selectedMarkets = getSelectedMarkets();
      const selectedPools = getSelectedPools();
      const filtersActive = selectedMarkets.length > 0 || selectedPools.length > 0;

      // Filter creatives client-side
      const filteredCreatives = filterCreativesClientSide(allCreatives, selectedMarkets, selectedPools);

      // Compute aggregates and pool stats from filtered creatives only when filters are active
      // When filters are NOT active, pass null so renderCreatives uses backend aggregates
      const filteredAggregates = filtersActive
        ? computeFilteredAggregates(filteredCreatives, allCreatives, selectedMarkets, selectedPools)
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
      const filteredHeadcount = computeFilteredHeadcount(
        filteredCreatives,
        creativeState.selectedMonthValue
      );
      const selectedFilterLabels = [];
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
          headcount: filteredHeadcount,
          tasks_stats: filteredTasksStats,
          overtime_stats: filteredOvertimeStats,
        }
      );
    } catch (error) {
      console.error("Error rendering creatives:", error);
      showErrorBanner("Failed to render creatives. Please refresh the page.");
    }
  };

  const CARD_STATUS_CLASSES = {
    healthy: "border-slate-200 bg-white hover:border-slate-300",
    warning: "border-amber-300 bg-amber-50 hover:border-amber-400",
    critical: "border-rose-300 bg-rose-50 hover:border-rose-400",
  };

  const CARD_BASE_CLASS =
    "group rounded-2xl border p-5 shadow-sm transition data-[expanded='true']:shadow-lg data-[expanded='true']:ring-1 data-[expanded='true']:ring-slate-200/60 data-[expanded='true']:ring-offset-1 data-[expanded='true']:ring-offset-white";

  const resolveUtilizationStatus = (creative) => {
    if (typeof creative?.utilization_status === "string") {
      const normalized = creative.utilization_status.trim().toLowerCase();
      if (normalized) {
        return normalized;
      }
    }

    const available = Number(creative?.available_hours ?? 0);
    const plannedPercent = Number.isFinite(Number(creative?.planned_utilization))
      ? Number(creative.planned_utilization)
      : available > 0
        ? (Number(creative?.planned_hours ?? 0) / available) * 100
        : 0;
    const loggedPercent = Number.isFinite(Number(creative?.logged_utilization))
      ? Number(creative.logged_utilization)
      : available > 0
        ? (Number(creative?.logged_hours ?? 0) / available) * 100
        : 0;

    if (plannedPercent < 50 || loggedPercent < 50) {
      return "critical";
    }
    if (plannedPercent < 75 || loggedPercent < 75) {
      return "warning";
    }
    return "healthy";
  };

  const createTagPill = (label, variant = "primary") => {
    const tag = document.createElement("span");
    if (variant === "primary") {
      tag.className =
        "inline-flex items-center rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700";
    } else {
      tag.className =
        "rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700 shadow-sm";
    }
    tag.textContent = label;
    return tag;
  };

  const getUtilizationDisplay = (displayValue, numericValue) => {
    if (typeof displayValue === "string" && displayValue.trim().length > 0) {
      return displayValue;
    }
    const percent = Number(numericValue);
    if (!Number.isFinite(percent) || percent <= 0) {
      return "0%";
    }
    const rounded = Math.round(percent * 10) / 10;
    return Number.isInteger(rounded) ? `${rounded}%` : `${rounded.toFixed(1)}%`;
  };

  const getHoursDisplay = (displayValue, numericValue) => {
    if (typeof displayValue === "string" && displayValue.trim().length > 0) {
      return displayValue;
    }
    return formatHours(numericValue);
  };

  const createMetricBlock = (label, value, options = {}) => {
    const wrapper = document.createElement("div");
    wrapper.className =
      options.wrapperClass ?? "rounded-xl border border-slate-200 bg-white/80 px-4 py-3";

    const title = document.createElement("dt");
    title.className =
      options.labelClass ?? "text-xs font-semibold uppercase tracking-wide text-slate-500";
    title.textContent = label;
    wrapper.appendChild(title);

    const content = document.createElement("dd");
    content.className = options.valueClass ?? "mt-1 text-sm font-semibold text-slate-900";
    content.textContent = value;
    wrapper.appendChild(content);
    return wrapper;
  };

  const createUtilizationSummary = (creative) => {
    const summary = document.createElement("dl");
    summary.className = "grid gap-3 sm:grid-cols-2";

    summary.appendChild(
      createMetricBlock(
        "Logged Utilization",
        getUtilizationDisplay(creative.logged_utilization_display, creative.logged_utilization),
        {
          valueClass: "mt-1 text-2xl font-semibold text-slate-900",
        }
      )
    );

    summary.appendChild(
      createMetricBlock(
        "Planned Utilization",
        getUtilizationDisplay(creative.planned_utilization_display, creative.planned_utilization),
        {
          valueClass: "mt-1 text-2xl font-semibold text-slate-900",
        }
      )
    );

    return summary;
  };

  const createHoursDetails = (creative, extraTags) => {
    const details = document.createElement("div");
    details.className = "mt-4 hidden border-t border-slate-200 pt-4";
    details.dataset.cardDetails = "true";

    const metrics = document.createElement("dl");
    metrics.className = "grid gap-3 sm:grid-cols-2 lg:grid-cols-3";

    metrics.appendChild(
      createMetricBlock(
        "Available Hours",
        getHoursDisplay(creative.available_hours_display, creative.available_hours),
        {
          wrapperClass: "rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-center",
          labelClass: "text-xs font-semibold uppercase tracking-wide text-slate-500",
          valueClass: "mt-1 text-sm font-semibold text-slate-800",
        }
      )
    );

    metrics.appendChild(
      createMetricBlock("Base Hours", getHoursDisplay(creative.base_hours_display, creative.base_hours), {
        wrapperClass: "rounded-xl border border-slate-200 bg-purple-50 px-3 py-2 text-center",
        labelClass: "text-xs font-semibold uppercase tracking-wide text-purple-600",
        valueClass: "mt-1 text-sm font-semibold text-purple-700",
      })
    );

    metrics.appendChild(
      createMetricBlock("Time Off", getHoursDisplay(creative.time_off_hours_display, creative.time_off_hours), {
        wrapperClass: "rounded-xl border border-slate-200 bg-orange-50 px-3 py-2 text-center",
        labelClass: "text-xs font-semibold uppercase tracking-wide text-orange-600",
        valueClass: "mt-1 text-sm font-semibold text-orange-700",
      })
    );

    metrics.appendChild(
      createMetricBlock("Public Holiday", getHoursDisplay(creative.public_holiday_hours_display, creative.public_holiday_hours), {
        wrapperClass: "rounded-xl border border-slate-200 bg-red-50 px-3 py-2 text-center",
        labelClass: "text-xs font-semibold uppercase tracking-wide text-red-600",
        valueClass: "mt-1 text-sm font-semibold text-red-700",
      })
    );

    metrics.appendChild(
      createMetricBlock("Planned Hours", getHoursDisplay(creative.planned_hours_display, creative.planned_hours), {
        wrapperClass: "rounded-xl border border-slate-200 bg-blue-50 px-3 py-2 text-center",
        labelClass: "text-xs font-semibold uppercase tracking-wide text-blue-600",
        valueClass: "mt-1 text-sm font-semibold text-blue-700",
      })
    );

    metrics.appendChild(
      createMetricBlock("Logged Hours", getHoursDisplay(creative.logged_hours_display, creative.logged_hours), {
        wrapperClass: "rounded-xl border border-slate-200 bg-indigo-50 px-3 py-2 text-center",
        labelClass: "text-xs font-semibold uppercase tracking-wide text-indigo-600",
        valueClass: "mt-1 text-sm font-semibold text-indigo-700",
      })
    );

    details.appendChild(metrics);

    // Add public holiday breakdown if available
    if (creative.public_holiday_details && Array.isArray(creative.public_holiday_details) && creative.public_holiday_details.length > 0) {
      const breakdownContainer = document.createElement("div");
      breakdownContainer.className = "col-span-full rounded-xl border border-red-200 bg-red-50 px-3 py-2 mt-2";

      const breakdownTitle = document.createElement("dt");
      breakdownTitle.className = "text-xs font-semibold uppercase tracking-wide text-red-600 mb-2";
      breakdownTitle.textContent = "Public Holiday Breakdown";
      breakdownContainer.appendChild(breakdownTitle);

      const breakdownList = document.createElement("dd");
      breakdownList.className = "space-y-1";

      creative.public_holiday_details.forEach((holiday) => {
        const holidayRow = document.createElement("div");
        holidayRow.className = "flex items-center justify-between text-xs";

        const holidayName = document.createElement("span");
        holidayName.className = "text-red-700";
        holidayName.textContent = holiday.name || "Unknown Holiday";
        holidayRow.appendChild(holidayName);

        const holidayHours = document.createElement("span");
        holidayHours.className = "font-semibold text-red-800";
        holidayHours.textContent = `${holiday.hours?.toFixed(1) || "0.0"}h`;
        holidayRow.appendChild(holidayHours);

        breakdownList.appendChild(holidayRow);

        // Add date range if available
        if (holiday.date_from || holiday.date_to) {
          const dateRow = document.createElement("div");
          dateRow.className = "text-xs text-red-600 ml-2";

          const dateFrom = holiday.date_from ? holiday.date_from.substring(0, 10) : "";
          const dateTo = holiday.date_to ? holiday.date_to.substring(0, 10) : "";
          const dateText = dateFrom === dateTo ? dateFrom : `${dateFrom}${dateTo ? ` - ${dateTo}` : ""}`;

          dateRow.textContent = dateText;
          breakdownList.appendChild(dateRow);
        }
      });

      breakdownContainer.appendChild(breakdownList);
      details.appendChild(breakdownContainer);
    }

    if (extraTags.length > 0) {
      const tagContainer = document.createElement("div");
      tagContainer.className = "mt-4 flex flex-wrap gap-2";
      extraTags.forEach((tag) => tagContainer.appendChild(createTagPill(tag, "secondary")));
      details.appendChild(tagContainer);
    }

    return details;
  };

  const bindCardToggle = (card, toggle, details) => {
    if (!card || !toggle || !details) {
      return;
    }

    toggle.setAttribute("aria-expanded", "false");

    toggle.addEventListener("click", () => {
      const isExpanded = card.dataset.expanded === "true";
      const nextState = !isExpanded;
      card.dataset.expanded = nextState ? "true" : "false";
      toggle.setAttribute("aria-expanded", nextState ? "true" : "false");
      details.classList.toggle("hidden", !nextState);
    });
  };

  const buildCard = (creative) => {
    const status = resolveUtilizationStatus(creative);
    const marketDisplay = creative.market_display || null;
    const poolDisplay = creative.pool_display && creative.pool_display !== "No Pool" ? creative.pool_display : null;

    const card = document.createElement("article");
    card.dataset.utilizationStatus = status;
    card.dataset.expanded = "false";
    card.className = `${CARD_BASE_CLASS} ${CARD_STATUS_CLASSES[status] ?? CARD_STATUS_CLASSES.healthy}`;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.dataset.cardToggle = "true";
    toggle.className =
      "flex w-full flex-col gap-4 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent";

    const header = document.createElement("div");
    header.className = "flex items-start justify-between gap-3";

    const headerContent = document.createElement("div");
    headerContent.className = "space-y-1";

    const name = document.createElement("h3");
    name.className = "text-lg font-semibold text-slate-900";
    name.textContent = creative.name ?? "Unnamed Creative";
    headerContent.appendChild(name);

    if (creative.department) {
      const department = document.createElement("p");
      department.className = "text-xs font-medium uppercase tracking-wider text-slate-500";
      department.textContent = creative.department;
      headerContent.appendChild(department);
    }

    if (marketDisplay) {
      headerContent.appendChild(createTagPill(marketDisplay));
    }

    if (poolDisplay) {
      const poolPill = document.createElement("span");
      poolPill.className = "inline-flex items-center rounded-full bg-purple-50 px-3 py-1 text-xs font-semibold text-purple-700";
      poolPill.textContent = poolDisplay;
      headerContent.appendChild(poolPill);
    }

    header.appendChild(headerContent);

    const icon = document.createElement("span");
    icon.className =
      "material-symbols-rounded text-base text-slate-400 transition group-data-[expanded='true']:rotate-180";
    icon.textContent = "expand_more";
    header.appendChild(icon);

    toggle.appendChild(header);
    toggle.appendChild(createUtilizationSummary(creative));
    card.appendChild(toggle);

    const details = createHoursDetails(creative, []);
    card.appendChild(details);

    bindCardToggle(card, toggle, details);
    return card;
  };

  const initializeServerRenderedCards = () => {
    document.querySelectorAll("[data-creative-card]").forEach((card) => {
      const toggle = card.querySelector("[data-card-toggle]");
      const details = card.querySelector("[data-card-details]");
      if (details && card.dataset.expanded !== "true") {
        details.classList.add("hidden");
      }
      const status = card.dataset.utilizationStatus ?? "healthy";
      card.className = `${CARD_BASE_CLASS} ${CARD_STATUS_CLASSES[status] ?? CARD_STATUS_CLASSES.healthy}`;
      bindCardToggle(card, toggle, details);
    });
  };

  const renderCreatives = (
    creatives,
    monthName,
    stats,
    aggregates,
    pools,
    clientMarkets,
    options = {}
  ) => {
    const {
      filtersActive = false,
      selectedMarkets = [],
      selectedPools = [],
      selectedFilterLabels = [],
      headcount: filteredHeadcount = null,
      tasks_stats: filteredTasksStats = null,
      overtime_stats: filteredOvertimeStats = null,
    } = options;
    if (!grid) {
      return;
    }

    grid.innerHTML = "";
    if (Array.isArray(creatives) && creatives.length > 0) {
      creatives.forEach((creative) => grid.appendChild(buildCard(creative)));
    } else {
      const empty = document.createElement("div");
      empty.className = "rounded-xl border border-slate-200 bg-slate-50 p-6 text-center";
      empty.innerHTML =
        '<p class="text-sm text-slate-500">No creatives match the current filters.</p>';
      grid.appendChild(empty);
    }

    updateMonthLabel(monthName || monthLabel?.textContent || "");
    const filteredCreatives = Array.isArray(creatives) ? creatives : [];
    const allCreatives = Array.isArray(creativeState.creatives) ? creativeState.creatives : [];
    const statsSource = filtersActive
      ? filteredCreatives
      : allCreatives.length > 0
        ? allCreatives
        : filteredCreatives;
    // Always use backend stats for total count, even when filters are active
    const globalStats = stats ?? creativeState.stats ?? null;
    const globalAggregates = filtersActive
      ? aggregates ?? null
      : aggregates ?? creativeState.aggregates ?? null;
    const globalHeadcount = filteredHeadcount ?? creativeState.headcount ?? null;
    updateStats(globalStats, statsSource);
    // Don't update tasks from aggregates when filters are active - we'll handle it separately below
    // Create a modified aggregates object without tasks_stats when filters are active to prevent override
    const aggregatesForUpdate = filtersActive && filteredTasksStats && globalAggregates
      ? { ...globalAggregates, tasks_stats: undefined }
      : globalAggregates;
    updateAggregates(aggregatesForUpdate, statsSource);

    // Update headcount if available
    // IMPORTANT: Always preserve the unfiltered total count, even when filters are active

    // Store the unfiltered headcount in creativeState when no filters are active
    if (!filtersActive && globalHeadcount && !creativeState.headcount) {
      creativeState.headcount = globalHeadcount;
    }

    if (globalHeadcount) {
      const headcountToUpdate = filtersActive && creativeState.headcount?.total
        ? { ...globalHeadcount, total: creativeState.headcount.total }
        : globalHeadcount;
      updateHeadcount(headcountToUpdate);
    } else if (globalAggregates?.headcount) {
      const headcountToUpdate = filtersActive && creativeState.headcount?.total
        ? { ...globalAggregates.headcount, total: creativeState.headcount.total }
        : globalAggregates.headcount;
      updateHeadcount(headcountToUpdate);
    }

    // Update tasks (use filtered payload when filters are active)
    // Priority: options.tasks_stats (filtered) > aggregates?.tasks_stats > creativeState.tasks_stats
    const currentTasksStats = filtersActive
      ? filteredTasksStats ?? aggregates?.tasks_stats ?? creativeState.tasks_stats ?? null
      : creativeState.tasks_stats ?? aggregates?.tasks_stats ?? null;
    if (currentTasksStats) {
      updateTasks(currentTasksStats);
    }

    // Update overtime (use filtered payload when filters are active)
    // Priority: options.overtime_stats (filtered) > creativeState.overtime_stats > aggregates?.overtime_stats
    const currentOvertimeStats = filtersActive
      ? filteredOvertimeStats ?? creativeState.overtime_stats ?? null
      : creativeState.overtime_stats ?? null;
    if (currentOvertimeStats) {
      updateOvertime(currentOvertimeStats);
    } else if (globalAggregates?.overtime_stats) {
      updateOvertime(globalAggregates.overtime_stats);
    }
    registerPoolLabelsFromData(pools ?? creativeState.pools ?? []);
    updatePools(
      filtersActive ? null : pools ?? creativeState.pools ?? null,
      statsSource
    );
    if (utilizationTitle) {
      const labels =
        Array.isArray(selectedFilterLabels) && selectedFilterLabels.length > 0
          ? selectedFilterLabels
          : Array.isArray(selectedMarkets) && selectedMarkets.length > 0
            ? selectedMarkets.map((slug) =>
              typeof slug === "string" ? slug.toUpperCase() : ""
            )
            : Array.isArray(selectedPools)
              ? selectedPools.map((slug) => getPoolLabel(slug))
              : [];
      const heading = filtersActive
        ? formatPoolSelectionHeading(labels)
        : utilizationTitleDefault;
      utilizationTitle.textContent = heading;
    }
    renderClientMarkets(
      Array.isArray(clientMarkets) ? clientMarkets : creativeState.clientMarkets,
      creativeState.clientSummary
    );
    renderSubscriptionMarkets(
      Array.isArray(creativeState.clientSubscriptions)
        ? creativeState.clientSubscriptions
        : [],
      creativeState.subscriptionSummary
    );
    renderSubscriptionUsedHoursChart(creativeState.subscriptionUsedHoursSeries);
    initializeCollapsibleSections();
  };

  const getSelectedMarkets = () => {
    const selected = [];
    marketFilterButtons.forEach(button => {
      if (button.classList.contains('border-sky-500')) {
        selected.push(button.dataset.filterValue);
      }
    });
    return selected;
  };

  const getSelectedPools = () => {
    const selected = [];
    poolFilterButtons.forEach(button => {
      if (button.classList.contains('border-sky-500')) {
        selected.push(button.dataset.filterValue);
      }
    });
    return selected;
  };

  const buildApiUrl = (monthValue) => {
    const params = new URLSearchParams();
    const month = monthValue ?? monthSelect?.value;
    if (month) {
      params.set("month", month);
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







  const fetchCreatives = async (monthValue) => {
    if (activeFetchController) {
      activeFetchController.abort();
    }

    const controller = new AbortController();
    activeFetchController = controller;

    hideErrorBanner();
    setLoadingState(true);
    if (loadingOverlay) {
      loadingOverlay.classList.remove("hidden");
    }

    try {
      const response = await fetch(buildApiUrl(monthValue), {
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = response.statusText || `status ${response.status}`;
        throw new Error(`Request failed (${detail})`);
      }
      const payload = await response.json();
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
      const payloadClientMarketsAll = Array.isArray(payload.client_external_hours_all)
        ? payload.client_external_hours_all
        : Array.isArray(payload.client_external_hours)
          ? payload.client_external_hours
          : [];
      const payloadClientSubscriptionsAll = Array.isArray(payload.client_subscription_hours_all)
        ? payload.client_subscription_hours_all
        : Array.isArray(payload.client_subscription_hours)
          ? payload.client_subscription_hours
          : [];
      creativeState.clientMarketsAll = payloadClientMarketsAll;
      creativeState.clientSubscriptionsAll = payloadClientSubscriptionsAll;
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
      renderFilteredCreatives();
      if (monthSelect && payload.selected_month) {
        monthSelect.value = payload.selected_month;
      }
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
        if (loadingOverlay) {
          loadingOverlay.classList.add("hidden");
        }
        setLoadingState(false);
      }
    }
  };

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
  renderFilteredCreatives();
  setSubscriptionUsedHoursMode(initialUsedHoursMode, { rerender: false });
  renderSubscriptionUsedHoursChart(creativeState.subscriptionUsedHoursSeries);
  initializeCollapsibleSections();
  initializeProjectCards();
  initializeServerRenderedCards();
  initMonthlyUtilizationChart();


  const setActiveTab = (target) => {
    const validTabs = ["team", "client"];
    const normalized = validTabs.includes(target) ? target : "team";
    tabButtons.forEach((button) => {
      const isActive = button.dataset.dashboardTab === normalized;
      button.dataset.active = isActive ? "true" : "false";
    });
    panels.forEach((panel) => {
      if (!panel.dataset.dashboardPanel) {
        return;
      }
      if (panel.dataset.dashboardPanel === normalized) {
        panel.classList.remove("hidden");
      } else {
        panel.classList.add("hidden");
      }
    });

    // Show/hide creative filters based on active tab
    const creativeFiltersPanel = document.querySelector("[data-creative-filters-panel]");
    if (creativeFiltersPanel) {
      if (normalized === "team") {
        creativeFiltersPanel.classList.remove("hidden");
      } else {
        creativeFiltersPanel.classList.add("hidden");
      }
    }
  };

  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setActiveTab(button.dataset.dashboardTab);
    });
  });

  setActiveTab("team");

  // Pool filter removed - no event listeners needed

  const handleLoad = (event) => {
    const value = event?.target?.value;
    fetchCreatives(value);

  };

  const handleClientFilterChange = () => {
    applyClientFilters();
  };

  if (refreshButton) {
    refreshButton.addEventListener("click", handleLoad);
  }

  if (monthSelect) {
    monthSelect.addEventListener("change", handleLoad);
  }

  if (agreementFilterSelect) {
    agreementFilterSelect.addEventListener("change", handleClientFilterChange);
  }
  if (accountFilterSelect) {
    accountFilterSelect.addEventListener("change", handleClientFilterChange);
  }

  // Market and Pool filter event listeners - instant filtering
  marketFilterButtons.forEach(button => {
    button.addEventListener("click", () => {
      // Toggle selected state
      const isSelected = button.classList.contains('border-sky-500');
      if (isSelected) {
        button.classList.remove('border-sky-500', 'bg-sky-50', 'text-sky-700');
        button.classList.add('border-slate-200', 'bg-white', 'text-slate-700');
      } else {
        button.classList.remove('border-slate-200', 'bg-white', 'text-slate-700');
        button.classList.add('border-sky-500', 'bg-sky-50', 'text-sky-700');
      }

      // Update clear button visibility
      updateClearButtonVisibility();

      // Apply filter instantly without server refresh
      renderFilteredCreatives();
      updateMonthlyUtilizationChart();
    });
  });

  poolFilterButtons.forEach(button => {
    button.addEventListener("click", () => {
      // Toggle selected state
      const isSelected = button.classList.contains('border-sky-500');
      if (isSelected) {
        button.classList.remove('border-sky-500', 'bg-sky-50', 'text-sky-700');
        button.classList.add('border-slate-200', 'bg-white', 'text-slate-700');
      } else {
        button.classList.remove('border-slate-200', 'bg-white', 'text-slate-700');
        button.classList.add('border-sky-500', 'bg-sky-50', 'text-sky-700');
      }

      // Update clear button visibility
      updateClearButtonVisibility();

      // Apply filter instantly without server refresh
      renderFilteredCreatives();
      updateMonthlyUtilizationChart();
    });
  });

  const updateClearButtonVisibility = () => {
    // Clear button is now always visible, no need to toggle visibility
  };

  if (filterResetButton) {
    filterResetButton.addEventListener("click", () => {
      // Clear market filters
      marketFilterButtons.forEach(button => {
        button.classList.remove('border-sky-500', 'bg-sky-50', 'text-sky-700');
        button.classList.add('border-slate-200', 'bg-white', 'text-slate-700');
      });

      // Clear pool filters
      poolFilterButtons.forEach(button => {
        button.classList.remove('border-sky-500', 'bg-sky-50', 'text-sky-700');
        button.classList.add('border-slate-200', 'bg-white', 'text-slate-700');
      });

      // Hide clear button
      updateClearButtonVisibility();

      // Apply filter instantly without server refresh
      renderFilteredCreatives();
      updateMonthlyUtilizationChart();
    });
  }

  // Creative Search and Group Management
  const creativeSearchInput = document.querySelector("[data-creative-search]");
  const filterMenuToggle = document.querySelector("[data-creative-filter-menu-toggle]");
  const filterMenuDropdown = document.querySelector("[data-creative-filter-menu-dropdown]");
  const filterTypeRadios = document.querySelectorAll("[data-filter-type]");
  const individualCreativesSelector = document.querySelector("[data-individual-creatives-selector]");
  const groupsSelector = document.querySelector("[data-groups-selector]");
  const creativeCheckboxesContainer = document.querySelector("[data-creative-checkboxes]");
  const groupsListContainer = document.querySelector("[data-groups-list]");
  const createGroupBtn = document.querySelector("[data-create-group-btn]");
  const createGroupBtnHeader = document.querySelector("[data-create-group-btn-header]");
  const groupModal = document.querySelector("[data-group-modal]");
  const groupModalTitle = document.querySelector("[data-group-modal-title]");
  const groupModalClose = document.querySelector("[data-group-modal-close]");
  const groupModalCancel = document.querySelector("[data-group-modal-cancel]");
  const groupModalSave = document.querySelector("[data-group-modal-save]");
  const groupNameInput = document.querySelector("[data-group-name-input]");
  const groupCreativeCheckboxes = document.querySelector("[data-group-creative-checkboxes]");

  let creativeGroups = [];
  let currentFilterType = "all";
  let selectedCreativeIds = [];
  let selectedGroupId = null;
  let searchQuery = "";
  let editingGroupId = null;

  // Load creative groups from API
  const loadCreativeGroups = async () => {
    try {
      const response = await fetch("/api/creative-groups");
      if (response.ok) {
        const data = await response.json();
        creativeGroups = data.groups || [];
        renderGroupsList();
      }
    } catch (error) {
      console.error("Error loading creative groups:", error);
    }
  };

  // Render groups list
  const renderGroupsList = () => {
    if (!groupsListContainer) return;

    groupsListContainer.innerHTML = "";

    if (creativeGroups.length === 0) {
      const empty = document.createElement("p");
      empty.className = "text-sm text-slate-500 text-center py-4";
      empty.textContent = "No saved groups. Create one to get started.";
      groupsListContainer.appendChild(empty);
      return;
    }

    creativeGroups.forEach((group) => {
      const label = document.createElement("label");
      label.className = "flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-slate-50 cursor-pointer";

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "group-selection";
      radio.value = group.id;
      radio.className = "h-4 w-4 text-sky-500 focus:ring-sky-300";
      radio.addEventListener("change", () => {
        selectedGroupId = parseInt(radio.value);
        applyCreativeFilters();
      });

      const span = document.createElement("span");
      span.className = "flex-1 text-sm font-medium text-slate-700";
      span.textContent = group.name;

      const actions = document.createElement("div");
      actions.className = "flex items-center gap-1";

      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "inline-flex h-6 w-6 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-sky-600";
      editBtn.innerHTML = '<span class="material-symbols-rounded text-sm">edit</span>';
      editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openGroupModal(group);
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "inline-flex h-6 w-6 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-rose-600";
      deleteBtn.innerHTML = '<span class="material-symbols-rounded text-sm">delete</span>';
      deleteBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (confirm(`Delete group "${group.name}"?`)) {
          await deleteGroup(group.id);
        }
      });

      actions.appendChild(editBtn);
      actions.appendChild(deleteBtn);

      label.appendChild(radio);
      label.appendChild(span);
      label.appendChild(actions);
      groupsListContainer.appendChild(label);
    });
  };

  // Render individual creative checkboxes
  const renderIndividualCreativeCheckboxes = () => {
    if (!creativeCheckboxesContainer) return;

    const allCreatives = Array.isArray(creativeState.creatives) ? creativeState.creatives : [];
    creativeCheckboxesContainer.innerHTML = "";

    allCreatives.forEach((creative) => {
      const label = document.createElement("label");
      label.className = "flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-slate-50 cursor-pointer";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = creative.id;
      checkbox.className = "h-4 w-4 text-sky-500 focus:ring-sky-300";
      checkbox.checked = selectedCreativeIds.includes(creative.id);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          selectedCreativeIds.push(creative.id);
        } else {
          selectedCreativeIds = selectedCreativeIds.filter(id => id !== creative.id);
        }
        applyCreativeFilters();
      });

      const span = document.createElement("span");
      span.className = "text-sm font-medium text-slate-700";
      span.textContent = creative.name || `Creative ${creative.id}`;

      label.appendChild(checkbox);
      label.appendChild(span);
      creativeCheckboxesContainer.appendChild(label);
    });
  };

  // Render group modal creative checkboxes
  const renderGroupModalCheckboxes = (preselectedIds = []) => {
    if (!groupCreativeCheckboxes) return;

    const allCreatives = Array.isArray(creativeState.creatives) ? creativeState.creatives : [];
    groupCreativeCheckboxes.innerHTML = "";

    allCreatives.forEach((creative) => {
      const label = document.createElement("label");
      label.className = "flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-slate-50 cursor-pointer";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = creative.id;
      checkbox.className = "h-4 w-4 text-sky-500 focus:ring-sky-300";
      checkbox.checked = preselectedIds.includes(creative.id);

      const span = document.createElement("span");
      span.className = "text-sm font-medium text-slate-700";
      span.textContent = creative.name || `Creative ${creative.id}`;

      label.appendChild(checkbox);
      label.appendChild(span);
      groupCreativeCheckboxes.appendChild(label);
    });
  };

  // Apply creative filters based on current selection
  const applyCreativeFilters = () => {
    let filteredCreatives = Array.isArray(creativeState.creatives) ? creativeState.creatives : [];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filteredCreatives = filteredCreatives.filter(creative => {
        const name = (creative.name || "").toLowerCase();
        return name.includes(query);
      });
    }

    // Apply filter type
    if (currentFilterType === "individual" && selectedCreativeIds.length > 0) {
      filteredCreatives = filteredCreatives.filter(creative =>
        selectedCreativeIds.includes(creative.id)
      );
    } else if (currentFilterType === "group" && selectedGroupId) {
      const group = creativeGroups.find(g => g.id === selectedGroupId);
      if (group && group.creative_ids) {
        const groupIds = Array.isArray(group.creative_ids) ? group.creative_ids : [];
        filteredCreatives = filteredCreatives.filter(creative =>
          groupIds.includes(creative.id)
        );
      }
    }

    // Re-render creatives with filtered list
    const filteredAggregates = computeFilteredAggregates(filteredCreatives, null, [], []);
    const filteredPoolStats = computeFilteredPoolStats(filteredCreatives);

    renderCreatives(
      filteredCreatives,
      creativeState.monthName || "",
      null,
      filteredAggregates,
      filteredPoolStats,
      creativeState.clientMarkets || [],
      {
        filtersActive: currentFilterType !== "all" || searchQuery.trim().length > 0,
        selectedMarkets: [],
        selectedPools: [],
        selectedFilterLabels: [],
      }
    );
  };

  // Open group modal
  const openGroupModal = (group = null) => {
    if (!groupModal) return;

    editingGroupId = group ? group.id : null;
    groupModalTitle.textContent = group ? `Edit Group: ${group.name}` : "Create New Group";
    groupNameInput.value = group ? group.name : "";

    const preselectedIds = group && group.creative_ids ? group.creative_ids : [];
    renderGroupModalCheckboxes(preselectedIds);

    groupModal.classList.remove("hidden");
    groupModal.classList.add("flex");
  };

  // Close group modal
  const closeGroupModal = () => {
    if (!groupModal) return;
    groupModal.classList.add("hidden");
    groupModal.classList.remove("flex");
    editingGroupId = null;
    groupNameInput.value = "";
  };

  // Save group
  const saveGroup = async () => {
    const name = groupNameInput.value.trim();
    if (!name) {
      alert("Please enter a group name");
      return;
    }

    const checkboxes = groupCreativeCheckboxes.querySelectorAll("input[type='checkbox']:checked");
    const creativeIds = Array.from(checkboxes).map(cb => parseInt(cb.value));

    if (creativeIds.length === 0) {
      alert("Please select at least one creative");
      return;
    }

    try {
      const url = editingGroupId
        ? `/api/creative-groups/${editingGroupId}`
        : "/api/creative-groups";
      const method = editingGroupId ? "PUT" : "POST";

      const response = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name,
          creative_ids: creativeIds,
        }),
      });

      if (response.ok) {
        await loadCreativeGroups();
        closeGroupModal();
        if (currentFilterType === "group" && editingGroupId === selectedGroupId) {
          applyCreativeFilters();
        }
      } else {
        const data = await response.json();
        alert(data.error || "Failed to save group");
      }
    } catch (error) {
      console.error("Error saving group:", error);
      alert("Failed to save group. Please try again.");
    }
  };

  // Delete group
  const deleteGroup = async (groupId) => {
    try {
      const response = await fetch(`/api/creative-groups/${groupId}`, {
        method: "DELETE",
      });

      if (response.ok) {
        await loadCreativeGroups();
        if (selectedGroupId === groupId) {
          selectedGroupId = null;
          currentFilterType = "all";
          document.querySelector("[data-filter-type='all']").checked = true;
          individualCreativesSelector?.classList.add("hidden");
          groupsSelector?.classList.add("hidden");
          applyCreativeFilters();
        }
      } else {
        const data = await response.json();
        alert(data.error || "Failed to delete group");
      }
    } catch (error) {
      console.error("Error deleting group:", error);
      alert("Failed to delete group. Please try again.");
    }
  };

  // Event listeners
  if (creativeSearchInput) {
    let searchDebounceTimer;
    creativeSearchInput.addEventListener("input", (e) => {
      searchQuery = e.target.value;
      // Debounce search for 300ms to avoid excessive filtering
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        applyCreativeFilters();
      }, 300);
    });
  }

  if (filterMenuToggle && filterMenuDropdown) {
    filterMenuToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      filterMenuDropdown.classList.toggle("hidden");
    });

    document.addEventListener("click", (e) => {
      if (!filterMenuToggle.contains(e.target) && !filterMenuDropdown.contains(e.target)) {
        filterMenuDropdown.classList.add("hidden");
      }
    });
  }

  filterTypeRadios.forEach((radio) => {
    radio.addEventListener("change", (e) => {
      currentFilterType = e.target.value;
      selectedCreativeIds = [];
      selectedGroupId = null;

      if (currentFilterType === "all") {
        individualCreativesSelector?.classList.add("hidden");
        groupsSelector?.classList.add("hidden");
        createGroupBtnHeader?.classList.add("hidden");
      } else if (currentFilterType === "individual") {
        individualCreativesSelector?.classList.remove("hidden");
        groupsSelector?.classList.add("hidden");
        createGroupBtnHeader?.classList.add("hidden");
        renderIndividualCreativeCheckboxes();
      } else if (currentFilterType === "group") {
        individualCreativesSelector?.classList.add("hidden");
        groupsSelector?.classList.remove("hidden");
        createGroupBtnHeader?.classList.remove("hidden");
      }

      applyCreativeFilters();
    });
  });

  if (createGroupBtn) {
    createGroupBtn.addEventListener("click", () => {
      openGroupModal();
    });
  }

  if (createGroupBtnHeader) {
    createGroupBtnHeader.addEventListener("click", () => {
      openGroupModal();
    });
  }

  if (groupModalClose) {
    groupModalClose.addEventListener("click", closeGroupModal);
  }

  if (groupModalCancel) {
    groupModalCancel.addEventListener("click", closeGroupModal);
  }

  if (groupModalSave) {
    groupModalSave.addEventListener("click", saveGroup);
  }

  // Close modal on backdrop click
  if (groupModal) {
    groupModal.addEventListener("click", (e) => {
      if (e.target === groupModal) {
        closeGroupModal();
      }
    });
  }

  // Load groups on page load
  loadCreativeGroups();

  // Initialize new joiners tooltip
  initNewJoinersTooltip();

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

    // Dispatch custom event for sales dashboard to handle
    if (targetTab === "sales") {
      const event = new CustomEvent("salesTabActivated", { detail: { month: monthSelect?.value } });
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
});
