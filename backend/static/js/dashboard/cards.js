// Creative card rendering: card DOM builders (tier 1, self-contained) and the
// renderCreatives orchestrator (tier 2, behind a factory). Bodies verbatim
// from main.js (original indentation kept).
import { formatHours, registerPoolLabelsFromData, getPoolLabel } from "./utils.js";
import { computeFilteredHeadcount } from "./compute.js";
import { mountDailyHours, prefetchDailyHours } from "./daycal.js";

  export const CARD_STATUS_CLASSES = {
    healthy: "border-slate-200 bg-white hover:border-slate-300",
    warning: "border-amber-300 bg-amber-50 hover:border-amber-400",
    critical: "border-rose-300 bg-rose-50 hover:border-rose-400",
  };

  export const CARD_BASE_CLASS =
    "group rounded-2xl border p-5 shadow-sm transition data-[expanded='true']:shadow-lg data-[expanded='true']:ring-1 data-[expanded='true']:ring-slate-200/60 data-[expanded='true']:ring-offset-1 data-[expanded='true']:ring-offset-white";

  export const resolveUtilizationStatus = (creative) => {
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

  // New joiner pill: shown for the whole 3-month ramp, clickable to toggle
  // whether the person's hours count toward utilization (persisted server-side).
  const NJ_PILL_BASE =
    "inline-flex cursor-pointer items-center rounded-full px-3 py-1 text-xs font-semibold transition";
  // Table rows are far denser than cards: same colors and behavior, but a
  // tiny "NJ" chip (opt in via data-nj-compact="true" on the pill element).
  const NJ_PILL_COMPACT_BASE =
    "inline-flex shrink-0 cursor-pointer items-center rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide transition";
  const NJ_PILL_EXCLUDED = "bg-emerald-50 text-emerald-800 hover:bg-emerald-100";
  const NJ_PILL_INCLUDED = "border border-emerald-300 bg-white text-emerald-700 hover:bg-emerald-50";
  const NJ_TITLE_EXCLUDED =
    "New joiner (first 3 months): hours are excluded from utilization totals. Click to count their hours.";
  const NJ_TITLE_INCLUDED =
    "New joiner: hours currently count toward utilization totals. Click to exclude them.";

  export const applyNewJoinerPillState = (pill, included) => {
    pill.dataset.included = included ? "true" : "false";
    const compact = pill.dataset.njCompact === "true";
    const base = compact ? NJ_PILL_COMPACT_BASE : NJ_PILL_BASE;
    pill.className = `${base} ${included ? NJ_PILL_INCLUDED : NJ_PILL_EXCLUDED}`;
    pill.textContent = compact
      ? included
        ? "NJ ✓"
        : "NJ"
      : included
        ? "New Joiner • counted"
        : "New Joiner";
    pill.title = included ? NJ_TITLE_INCLUDED : NJ_TITLE_EXCLUDED;
  };

  export const bindNewJoinerToggle = (pill, creativeId) => {
    if (!pill || !Number.isInteger(creativeId) || creativeId <= 0) {
      return;
    }
    if (pill.dataset.toggleBound === "true") {
      return;
    }
    pill.dataset.toggleBound = "true";
    pill.addEventListener("click", async (event) => {
      // The pill lives inside the card's expand button: keep the click local.
      event.stopPropagation();
      event.preventDefault();
      if (pill.dataset.busy === "true") {
        return;
      }
      const nextIncluded = pill.dataset.included !== "true";
      pill.dataset.busy = "true";
      pill.classList.add("opacity-50");
      try {
        const response = await fetch(`/api/creatives/${creativeId}/new-joiner-inclusion`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ included: nextIncluded }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.success !== true) {
          throw new Error(payload.error || `Request failed (${response.status})`);
        }
        applyNewJoinerPillState(pill, nextIncluded);
        // main.js refetches the month payload so stats reflect the change.
        document.dispatchEvent(
          new CustomEvent("newJoinerInclusionChanged", {
            detail: { creativeId, included: nextIncluded },
          })
        );
      } catch (error) {
        console.error("Failed to toggle new joiner inclusion", error);
      } finally {
        pill.dataset.busy = "false";
        pill.classList.remove("opacity-50");
      }
    });
  };

  export const createTagPill = (label, variant = "primary") => {
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

  export const getUtilizationDisplay = (displayValue, numericValue) => {
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

  export const getHoursDisplay = (displayValue, numericValue) => {
    if (typeof displayValue === "string" && displayValue.trim().length > 0) {
      return displayValue;
    }
    return formatHours(numericValue);
  };

  export const createMetricBlock = (label, value, options = {}) => {
    const wrapper = document.createElement("div");
    wrapper.className =
      options.wrapperClass ?? "rounded-xl border border-slate-200 bg-white/80 px-4 py-3";

    const title = document.createElement("dt");
    title.className =
      options.labelClass ?? "text-xs font-semibold uppercase tracking-wide text-slate-500";
    title.textContent = label;
    if (options.tooltip) {
      title.classList.add("cursor-help");
      title.setAttribute("title", options.tooltip);
    }
    wrapper.appendChild(title);

    const content = document.createElement("dd");
    content.className = options.valueClass ?? "mt-1 text-sm font-semibold text-slate-900";
    content.textContent = value;
    wrapper.appendChild(content);
    return wrapper;
  };

  export const createUtilizationSummary = (creative) => {
    const summary = document.createElement("dl");
    summary.className = "grid gap-3 sm:grid-cols-2";

    summary.appendChild(
      createMetricBlock(
        "Logged Utilization",
        getUtilizationDisplay(creative.logged_utilization_display, creative.logged_utilization),
        {
          valueClass: "mt-1 text-2xl font-semibold text-slate-900",
          tooltip: "Percentage of hours already logged against available hours",
        }
      )
    );

    summary.appendChild(
      createMetricBlock(
        "Booked Utilization",
        getUtilizationDisplay(creative.planned_utilization_display, creative.planned_utilization),
        {
          valueClass: "mt-1 text-2xl font-semibold text-slate-900",
          tooltip: "Percentage of hours scheduled hours on the Planning App.",
        }
      )
    );

    return summary;
  };

  export const createMetricRow = (label, value, options = {}) => {
    const row = document.createElement("div");
    row.className = "flex items-center justify-between gap-3 py-1.5";

    const title = document.createElement("dt");
    title.className =
      options.labelClass ?? "text-[11px] font-semibold uppercase tracking-wide text-slate-500";
    title.textContent = label;
    if (options.tooltip) {
      title.classList.add("cursor-help");
      title.setAttribute("title", options.tooltip);
    }
    row.appendChild(title);

    const content = document.createElement("dd");
    content.className = options.valueClass ?? "text-xs font-semibold text-slate-800";
    content.textContent = value;
    row.appendChild(content);
    return row;
  };

  export const createHoursDetails = (creative, extraTags) => {
    const details = document.createElement("div");
    details.className = "mt-4 hidden border-t border-slate-200 pt-4";
    details.dataset.cardDetails = "true";

    const metrics = document.createElement("dl");
    metrics.className =
      "divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white/70 px-3";

    metrics.appendChild(
      createMetricRow(
        "Available Hours",
        getHoursDisplay(creative.available_hours_display, creative.available_hours),
        { tooltip: "Total hours available for work" }
      )
    );

    metrics.appendChild(
      createMetricRow("Base Hours", getHoursDisplay(creative.base_hours_display, creative.base_hours), {
        labelClass: "text-[11px] font-semibold uppercase tracking-wide text-teal-600",
        valueClass: "text-xs font-semibold text-teal-700",
        tooltip: "Standard working hours in the period",
      })
    );

    metrics.appendChild(
      createMetricRow("Time Off", getHoursDisplay(creative.time_off_hours_display, creative.time_off_hours), {
        labelClass: "text-[11px] font-semibold uppercase tracking-wide text-orange-600",
        valueClass: "text-xs font-semibold text-orange-700",
        tooltip: "Approved leaves",
      })
    );

    metrics.appendChild(
      createMetricRow("Public Holiday", getHoursDisplay(creative.public_holiday_hours_display, creative.public_holiday_hours), {
        labelClass: "text-[11px] font-semibold uppercase tracking-wide text-red-600",
        valueClass: "text-xs font-semibold text-red-700",
        tooltip: "Holiday hours",
      })
    );

    metrics.appendChild(
      createMetricRow("Booked Hours", getHoursDisplay(creative.planned_hours_display, creative.planned_hours), {
        labelClass: "text-[11px] font-semibold uppercase tracking-wide text-blue-600",
        valueClass: "text-xs font-semibold text-blue-700",
        tooltip: "Work scheduled on Planning App.",
      })
    );

    metrics.appendChild(
      createMetricRow("Logged Hours", getHoursDisplay(creative.logged_hours_display, creative.logged_hours), {
        labelClass: "text-[11px] font-semibold uppercase tracking-wide text-indigo-600",
        valueClass: "text-xs font-semibold text-indigo-700",
        tooltip: "Work actually recorded",
      })
    );

    metrics.appendChild(
      createMetricRow("Overtime", getHoursDisplay(creative.overtime_hours_display, creative.overtime_hours), {
        labelClass: "text-[11px] font-semibold uppercase tracking-wide text-violet-600",
        valueClass: "text-xs font-semibold text-violet-700",
        tooltip: "Approved overtime requests in the period",
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

  export const bindCardToggle = (card, toggle, details) => {
    if (!card || !toggle || !details) {
      return;
    }
    // Idempotence: a second binding would make each click toggle twice
    // (expand + collapse), so cards would appear to not react at all.
    if (toggle.dataset.toggleBound === "true") {
      return;
    }
    toggle.dataset.toggleBound = "true";

    toggle.setAttribute("aria-expanded", "false");

    toggle.addEventListener("pointerenter", () => prefetchDailyHours(card), { passive: true });

    toggle.addEventListener("click", () => {
      const isExpanded = card.dataset.expanded === "true";
      const nextState = !isExpanded;
      card.dataset.expanded = nextState ? "true" : "false";
      toggle.setAttribute("aria-expanded", nextState ? "true" : "false");
      details.classList.toggle("hidden", !nextState);
      if (nextState) {
        mountDailyHours(card);
      }
    });
  };

  export const buildCard = (creative) => {
    const status = resolveUtilizationStatus(creative);
    const marketDisplay = creative.market_display || null;
    const poolDisplay = creative.pool_display && creative.pool_display !== "No Pool" ? creative.pool_display : null;

    const card = document.createElement("article");
    card.dataset.utilizationStatus = status;
    card.dataset.expanded = "false";
    if (Number.isInteger(creative.id)) {
      card.dataset.creativeId = String(creative.id);
    }
    card.className = `${CARD_BASE_CLASS} ${CARD_STATUS_CLASSES[status] ?? CARD_STATUS_CLASSES.healthy}`;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.dataset.cardToggle = "true";
    toggle.className =
      "flex w-full flex-col gap-4 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent";

    const header = document.createElement("div");
    header.className = "flex items-start justify-between gap-3";

    const headerContent = document.createElement("div");
    headerContent.className = "flex-1 space-y-1";

    // The name slot reserves two lines and the pill zone reserves two rows so
    // every card's sections below the header start at the same height,
    // regardless of how long the name is or how many pills a creative has.
    const name = document.createElement("h3");
    name.className = "min-h-14 text-lg font-semibold text-slate-900";
    name.textContent = creative.name ?? "Unnamed Creative";
    headerContent.appendChild(name);

    if (creative.department) {
      const department = document.createElement("p");
      department.className = "text-xs font-medium uppercase tracking-wider text-slate-500";
      department.textContent = creative.department;
      headerContent.appendChild(department);
    }

    const pillZone = document.createElement("div");
    pillZone.className = "flex min-h-14 flex-wrap content-start items-start gap-1";

    // Post-2026-04-01 model: render BU / SBU / Pod pills when present.
    // Pre-cutover the legacy market_display / pool_display pills are used.
    const businessUnit = creative.business_unit || null;
    const subBusinessUnit = creative.sub_business_unit || null;
    const pod = creative.pod || null;

    if (businessUnit) {
      const buPill = document.createElement("span");
      buPill.className = "inline-flex items-center rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700";
      buPill.title = "Business Unit";
      buPill.textContent = businessUnit;
      pillZone.appendChild(buPill);

      if (subBusinessUnit) {
        const sbuPill = document.createElement("span");
        sbuPill.className = "inline-flex items-center rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700";
        sbuPill.title = "Sub Business Unit";
        sbuPill.textContent = subBusinessUnit;
        pillZone.appendChild(sbuPill);
      }

      if (pod) {
        const podPill = document.createElement("span");
        podPill.className = "inline-flex items-center rounded-full bg-purple-50 px-3 py-1 text-xs font-semibold text-purple-700";
        podPill.title = "Pod";
        podPill.textContent = pod;
        pillZone.appendChild(podPill);
      }
    } else {
      if (marketDisplay) {
        pillZone.appendChild(createTagPill(marketDisplay));
      }

      if (poolDisplay) {
        const poolPill = document.createElement("span");
        poolPill.className = "inline-flex items-center rounded-full bg-purple-50 px-3 py-1 text-xs font-semibold text-purple-700";
        poolPill.textContent = poolDisplay;
        pillZone.appendChild(poolPill);
      }
    }

    if (creative.is_new_joiner_ramp) {
      const nj = document.createElement("span");
      nj.dataset.njToggle = "true";
      nj.setAttribute("role", "button");
      applyNewJoinerPillState(nj, creative.new_joiner_hours_included === true);
      bindNewJoinerToggle(nj, creative.id);
      pillZone.appendChild(nj);
    }

    headerContent.appendChild(pillZone);
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

  export const initializeServerRenderedCards = () => {
    document.querySelectorAll("[data-creative-card]").forEach((card) => {
      const toggle = card.querySelector("[data-card-toggle]");
      const details = card.querySelector("[data-card-details]");
      if (details && card.dataset.expanded !== "true") {
        details.classList.add("hidden");
      }
      const status = card.dataset.utilizationStatus ?? "healthy";
      card.className = `${CARD_BASE_CLASS} ${CARD_STATUS_CLASSES[status] ?? CARD_STATUS_CLASSES.healthy}`;
      bindCardToggle(card, toggle, details);

      const njPill = card.querySelector("[data-nj-toggle]");
      if (njPill) {
        applyNewJoinerPillState(njPill, njPill.dataset.included === "true");
        bindNewJoinerToggle(njPill, Number.parseInt(card.dataset.creativeId ?? "", 10));
      }
    });
  };

export function createCardRenderer({
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
}) {
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
    updateStats(globalStats, statsSource);
    // Don't update tasks from aggregates when filters are active - we'll handle it separately below
    // Create a modified aggregates object without tasks_stats when filters are active to prevent override
    const aggregatesForUpdate = filtersActive && filteredTasksStats && globalAggregates
      ? { ...globalAggregates, tasks_stats: undefined }
      : globalAggregates;
    updateAggregates(aggregatesForUpdate, statsSource);

    // Headcount / joiners / offboarding: always derive from the same list as the grid + selected
    // period. Do not use API headcount alone — paths like applyCreativeFilters omit options.headcount
    // and stale API objects can have new_joiners_count without names, desyncing badge vs SSR list.
    const viewingCount = filteredCreatives.length;
    const computedHeadcount = computeFilteredHeadcount(
      filteredCreatives,
      creativeState.selectedMonthValue
    );
    const headcountForUi =
      computedHeadcount != null
        ? { ...computedHeadcount, employee_count: viewingCount }
        : {
            employee_count: viewingCount,
            new_joiners_count: 0,
            new_joiners_names: [],
            offboarded_count: 0,
            offboarded_names: [],
          };
    updateHeadcount(headcountForUi);

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

  return { renderCreatives };
}
