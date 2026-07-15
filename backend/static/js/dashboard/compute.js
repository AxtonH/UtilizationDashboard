// Pure compute layer for the creatives dashboard: stats/aggregates math and
// client-side filtering of creatives. Extracted verbatim from main.js (original
// indentation kept); no DOM access and no shared dashboard state in here.
import {
  formatHours,
  POOL_DEFINITIONS,
  parseMonthBounds,
  parseDateValue,
  isWithinMonth,
} from "./utils.js";

  // Flip a ramp-period new joiner's hours in place using the pre-zeroing
  // values the backend ships in `new_joiner_raw`. Display/status fields are
  // nulled so the card renderers recompute them from the numbers.
  // Returns false when the creative has no raw data to flip with.
  export const applyNewJoinerFlipToCreative = (creative, included) => {
    if (!creative || typeof creative !== "object") {
      return false;
    }
    const raw = creative.new_joiner_raw;
    if (!raw || typeof raw !== "object") {
      return false;
    }
    const available = included ? Number(raw.available_hours || 0) : 0;
    const planned = included ? Number(raw.planned_hours || 0) : 0;
    const logged = included ? Number(raw.logged_hours || 0) : 0;

    creative.new_joiner_hours_included = included === true;
    creative.available_hours = available;
    creative.planned_hours = planned;
    creative.logged_hours = logged;
    creative.available_hours_display = null;
    creative.planned_hours_display = null;
    creative.logged_hours_display = null;

    const pct = (numerator) => (available > 0 ? (numerator / available) * 100 : 0);
    creative.planned_utilization = pct(planned);
    creative.logged_utilization = pct(logged);
    creative.planned_utilization_display = null;
    creative.logged_utilization_display = null;
    // Null status: resolveUtilizationStatus derives it from the new numbers.
    creative.utilization_status = null;
    return true;
  };

  export const computeStats = (creatives) => {
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

  export const computeAggregates = (creatives) => {
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

  export const calculateExternalHours = (
    clientMarketsAll,
    clientSubscriptionsAll,
    selectedMarkets,
    selectedPools,
    buFilterOptions = null
  ) => {
    const useBuModel = buFilterOptions?.useBuModel === true;
    if (useBuModel) {
      // Caller passes assignmentFiltersActive when any BU/SBU/Pod pill is selected (sales data is not segmented).
      if (buFilterOptions?.assignmentFiltersActive === true) {
        return { hours: 0, shouldShow: false };
      }

      const hasSalesMarkets = Array.isArray(clientMarketsAll) && clientMarketsAll.length > 0;
      const hasSubscriptionMarkets =
        Array.isArray(clientSubscriptionsAll) && clientSubscriptionsAll.length > 0;
      if (!hasSalesMarkets && !hasSubscriptionMarkets) {
        return { hours: 0, shouldShow: false };
      }

      // Full-period totals only when no BU/SBU/Pod pills — sales/subscription data is not segmented like creatives.
      let totalHours = 0;

      if (hasSalesMarkets) {
        clientMarketsAll.forEach((market) => {
          const projects = market?.projects || [];
          projects.forEach((project) => {
            totalHours += Number(project?.total_external_hours || 0);
          });
        });
      }

      if (hasSubscriptionMarkets) {
        clientSubscriptionsAll.forEach((market) => {
          const subscriptions = market?.subscriptions || [];
          subscriptions.forEach((subscription) => {
            totalHours += Number(subscription?.subscription_used_hours || 0);
          });
        });
      }

      return { hours: totalHours, shouldShow: true };
    }

    // Legacy: hide if pool filter is active (with or without market filter)
    if (selectedPools && selectedPools.length > 0) {
      return { hours: 0, shouldShow: false };
    }

    const hasSalesMarketsLegacy = Array.isArray(clientMarketsAll) && clientMarketsAll.length > 0;
    const hasSubscriptionMarketsLegacy =
      Array.isArray(clientSubscriptionsAll) && clientSubscriptionsAll.length > 0;
    if (!hasSalesMarketsLegacy && !hasSubscriptionMarketsLegacy) {
      return { hours: 0, shouldShow: false };
    }

    let totalHours = 0;

    const normalizeMarketName = (marketName) => {
      if (!marketName) return null;
      const normalized = String(marketName).trim().toLowerCase();
      if (normalized === "ksa" || normalized.includes("ksa")) return "ksa";
      if (normalized === "uae" || normalized.includes("uae")) return "uae";
      return normalized;
    };

    let marketsToInclude = null;
    if (selectedMarkets && selectedMarkets.length > 0) {
      marketsToInclude = selectedMarkets.map((m) => normalizeMarketName(m));
    }

    const legacyMarketMatchesSelection = (marketName) => {
      if (!marketsToInclude || marketsToInclude.length === 0) {
        return true;
      }
      const nm = normalizeMarketName(marketName);
      const raw = String(marketName || "").trim().toLowerCase();
      return marketsToInclude.some((sel) => {
        if (!sel) {
          return false;
        }
        return nm === sel || raw.includes(sel) || (nm != null && String(nm).includes(sel));
      });
    };

    if (hasSalesMarketsLegacy) {
      clientMarketsAll.forEach((market) => {
        const marketName = market?.market;

        if (!legacyMarketMatchesSelection(marketName)) {
          return;
        }

        const projects = market?.projects || [];
        projects.forEach((project) => {
          totalHours += Number(project?.total_external_hours || 0);
        });
      });
    }

    if (hasSubscriptionMarketsLegacy) {
      clientSubscriptionsAll.forEach((market) => {
        const marketName = market?.market;

        if (!legacyMarketMatchesSelection(marketName)) {
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

  export const computePoolStats = (creatives) => {
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

  const BU_ASSIGNMENT_CUTOVER_YEAR = 2026;
  const BU_ASSIGNMENT_CUTOVER_MONTH = 4;

  export const monthAnchorUsesBuAssignmentModel = (year, monthNum) => {
    if (!Number.isFinite(year) || !Number.isFinite(monthNum)) {
      return false;
    }
    if (year > BU_ASSIGNMENT_CUTOVER_YEAR) {
      return true;
    }
    if (year === BU_ASSIGNMENT_CUTOVER_YEAR && monthNum >= BU_ASSIGNMENT_CUTOVER_MONTH) {
      return true;
    }
    return false;
  };

  export const splitAssignmentFieldTokens = (value) => {
    if (value == null || typeof value !== "string") {
      return [];
    }
    return value
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  };

  export const creativeMatchesBuClientFilters = (creative, selectedBu, selectedSbu, selectedPod) => {
    const buSel = Array.isArray(selectedBu) ? selectedBu.filter(Boolean) : [];
    const sbuSel = Array.isArray(selectedSbu) ? selectedSbu.filter(Boolean) : [];
    const podSel = Array.isArray(selectedPod) ? selectedPod.filter(Boolean) : [];
    if (!buSel.length && !sbuSel.length && !podSel.length) {
      return true;
    }
    const buTok = new Set(splitAssignmentFieldTokens(creative?.business_unit));
    const sbuTok = new Set(splitAssignmentFieldTokens(creative?.sub_business_unit));
    const podTok = new Set(splitAssignmentFieldTokens(creative?.pod));
    if (buSel.length && !buSel.some((t) => buTok.has(t))) {
      return false;
    }
    if (sbuSel.length && !sbuSel.some((t) => sbuTok.has(t))) {
      return false;
    }
    if (podSel.length && !podSel.some((t) => podTok.has(t))) {
      return false;
    }
    return true;
  };

  export const filterCreativesClientSide = (
    creatives,
    selectedMarkets,
    selectedPools,
    selectedBu,
    selectedSbu,
    selectedPod,
    useBuModel
  ) => {
    if (useBuModel) {
      return creatives.filter((creative) =>
        creativeMatchesBuClientFilters(creative, selectedBu, selectedSbu, selectedPod)
      );
    }
    if (!selectedMarkets.length && !selectedPools.length) {
      return creatives;
    }
    return creatives.filter((creative) => {
      const marketSlug = creative.market_slug;
      const poolName = creative.pool_name;
      const marketMatch = selectedMarkets.length === 0 || selectedMarkets.includes(marketSlug);
      const poolMatch =
        selectedPools.length === 0 || (poolName && selectedPools.includes(poolName));
      return marketMatch && poolMatch;
    });
  };

  export const computeFilteredStats = (filteredCreatives) => {
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


  export const computeFilteredHeadcount = (filteredCreatives, monthValue) => {
    if (!Array.isArray(filteredCreatives)) {
      return null;
    }

    const bounds = parseMonthBounds(monthValue);
    const monthStart = bounds?.start;
    const monthEnd = bounds?.end;

    const hasAssignmentForHeadcount = (creative) =>
      Boolean(
        creative?.market_display ||
          creative?.pool_display ||
          creative?.business_unit ||
          creative?.sub_business_unit ||
          creative?.pod
      );

    const availableCreatives = filteredCreatives.filter(
      (creative) =>
        hasAssignmentForHeadcount(creative) &&
        (Number(creative?.available_hours || 0) > Number(creative?.planned_hours || 0))
    );
    const availableCount = availableCreatives.length;

    const totalCreativesList = filteredCreatives.filter((creative) =>
      hasAssignmentForHeadcount(creative)
    );
    const totalCount = totalCreativesList.length;

    const sortedByName = (list) =>
      list.slice().sort((a, b) => (a?.name || "").localeCompare(b?.name || ""));

    // New joiners: same idea as HeadcountService — anyone in the current view who joined in
    // the period (do not require available_hours > planned_hours; that was wrongly tied to
    // "available" creatives only and desynced the count from the name list).
    const newJoiners = monthStart && monthEnd
      ? sortedByName(
        filteredCreatives.filter((creative) => {
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
      /** Matches creative cards in the grid for the current market/pool selection */
      employee_count: filteredCreatives.length,
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

  export const matchesFiltersForTotals = (marketSlug, poolName, marketFilterSet, poolFilterSet) => {
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

  export const sumPreviousTotalsForBuFilters = (creatives, selectedBu, selectedSbu, selectedPod) => {
    if (!Array.isArray(creatives) || creatives.length === 0) {
      return null;
    }
    let hasData = false;
    const totals = { planned: 0.0, logged: 0.0, available: 0.0 };
    creatives.forEach((creative) => {
      const prev = {
        business_unit: creative?.previous_business_unit,
        sub_business_unit: creative?.previous_sub_business_unit,
        pod: creative?.previous_pod,
      };
      if (!creativeMatchesBuClientFilters(prev, selectedBu, selectedSbu, selectedPod)) {
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

  export const sumPreviousTotalsForFilters = (creatives, marketFilterSet, poolFilterSet) => {
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

  export const buildComparisonFromTotals = (currentTotals, previousTotals) => {
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

  export const computeFilteredTasksStats = (tasksStats, filteredCreatives) => {
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

  export const computeFilteredOvertimeStats = (overtimeStats, filteredCreatives) => {
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

  export const formatOvertimeHours = (hours) => {
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

  export const computeFilteredPoolStats = (filteredCreatives) => {
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
