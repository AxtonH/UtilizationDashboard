// Client market/subscription data layer: pure filtering, aggregation and
// top-client math for the client cards. Extracted verbatim from main.js
// (original indentation kept); no DOM access and no dashboard state.
import { formatAed, normalizeClientPoolSlug, CLIENT_POOL_DEFINITIONS } from "./utils.js";

  export const parseDatasetJson = (raw, fallback) => {
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

  export const formatClientHours = (value) => {
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

  export const matchesClientFilters = (entry, agreementFilter, accountFilter) => {
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

  export const normalizeClientKey = (projectId, name, market) => {
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

  export const extractSalesTopClients = (markets) => {
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

  export const extractSubscriptionTopClients = (markets) => {
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

  export const mergeClientTopClients = (subscriptionClients, salesClients, limit = 5) => {
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

  export const inferClientPoolSlug = (tags, ...candidates) => {
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

  export const computeClientPoolSummary = (salesMarkets, subscriptionMarkets) => {
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

  export const normalizeClientPoolSummary = (summary) => {
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

  export const buildFilteredClientData = (salesMarkets, subscriptionMarkets, filters) => {
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
