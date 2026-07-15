// Time card Excel export: a modal for picking creatives (with BU/SBU/Pod
// filter chips) that POSTs a payload assembled from data the browser already
// holds — creative summaries from dashboard state plus the bulk daily-hours
// response (server-cached) — so exporting costs no Odoo work.

let deps = null; // { creativeState, getPeriodValue, getPeriodLabel }
let modal = null;
let selectedIds = new Set();
let activeFilters = { business_unit: new Set(), sub_business_unit: new Set(), pod: new Set() };
let searchTerm = "";

export const initTimecardExport = (options) => {
  deps = options;
  document.querySelectorAll("[data-export-timecards]").forEach((button) => {
    if (button.dataset.exportBound === "true") {
      return;
    }
    button.dataset.exportBound = "true";
    button.addEventListener("click", openExportModal);
  });
};

const creatives = () =>
  Array.isArray(deps?.creativeState?.creatives) ? deps.creativeState.creatives : [];

const buildQuery = (ym) => {
  const params = new URLSearchParams();
  if (ym) {
    const dash = ym.indexOf("-");
    if (dash > 0) {
      params.set("year", ym.slice(0, dash));
      const rest = ym.slice(dash + 1);
      params.set("month", rest.startsWith("Q") ? rest : String(parseInt(rest, 10)));
    }
  }
  const query = params.toString();
  return query ? `?${query}` : "";
};

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

const FILTER_DIMENSIONS = [
  { key: "business_unit", label: "Business unit" },
  { key: "sub_business_unit", label: "Sub business unit" },
  { key: "pod", label: "Pod" },
];

const openExportModal = () => {
  if (!creatives().length) {
    return;
  }
  if (!modal) {
    modal = buildModalShell();
    document.body.appendChild(modal.root);
  }
  // Fresh state on every open: everyone selected, no filters.
  selectedIds = new Set(creatives().map((c) => c.id).filter((id) => Number.isInteger(id)));
  activeFilters = { business_unit: new Set(), sub_business_unit: new Set(), pod: new Set() };
  searchTerm = "";
  modal.search.value = "";
  modal.error.classList.add("hidden");
  renderFilters();
  renderList();
  modal.root.classList.remove("hidden");
};

const closeExportModal = () => modal?.root.classList.add("hidden");

const buildModalShell = () => {
  const root = document.createElement("div");
  root.className = "fixed inset-0 z-50 hidden items-center justify-center bg-slate-900/50 p-4 flex";
  root.addEventListener("click", (event) => {
    if (event.target === root) closeExportModal();
  });

  const panel = document.createElement("div");
  panel.className =
    "flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl";
  root.appendChild(panel);

  panel.innerHTML = `
    <div class="flex items-start justify-between gap-4 px-8 pt-7">
      <div>
        <h2 class="text-lg font-semibold text-slate-900">Export time cards</h2>
        <p class="mt-1 text-xs text-slate-500">
          Each selected creative gets their own sheet in the Excel file.
          Pick filters to select a group, then fine-tune individuals below.
        </p>
      </div>
      <button type="button" data-export-close class="text-slate-400 transition hover:text-slate-600">
        <span class="material-symbols-rounded">close</span>
      </button>
    </div>
    <div class="space-y-2.5 px-8 pt-5" data-export-filters></div>
    <div class="px-8 pt-4">
      <input type="text" data-export-search placeholder="Search creatives…"
        class="w-full rounded-full bg-slate-100 px-5 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-sky-200" />
    </div>
    <div class="mt-2 flex-1 overflow-y-auto px-6 pb-2" data-export-list></div>
    <p class="hidden px-8 pb-1 text-xs text-rose-600" data-export-error></p>
    <div class="flex items-center justify-between gap-3 px-8 pb-6 pt-3">
      <p class="text-xs text-slate-400" data-export-count></p>
      <div class="flex gap-2">
        <button type="button" data-export-cancel
          class="rounded-full px-4 py-2 text-sm font-semibold text-slate-500 transition hover:bg-slate-50 hover:text-slate-700">
          Cancel
        </button>
        <button type="button" data-export-confirm
          class="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-sky-500 via-indigo-500 to-purple-500 px-6 py-2 text-sm font-semibold text-white shadow-lg shadow-sky-200 transition hover:shadow-xl disabled:opacity-50">
          <span class="material-symbols-rounded text-base">download</span>
          <span data-export-confirm-label>Export</span>
        </button>
      </div>
    </div>`;

  const refs = {
    root,
    filters: panel.querySelector("[data-export-filters]"),
    list: panel.querySelector("[data-export-list]"),
    search: panel.querySelector("[data-export-search]"),
    count: panel.querySelector("[data-export-count]"),
    error: panel.querySelector("[data-export-error]"),
    confirm: panel.querySelector("[data-export-confirm]"),
    confirmLabel: panel.querySelector("[data-export-confirm-label]"),
  };

  panel.querySelector("[data-export-close]").addEventListener("click", closeExportModal);
  panel.querySelector("[data-export-cancel]").addEventListener("click", closeExportModal);
  refs.search.addEventListener("input", () => {
    searchTerm = refs.search.value.trim().toLowerCase();
    renderList();
  });
  refs.confirm.addEventListener("click", runExport);
  return refs;
};

const matchesActiveFilters = (creative) => {
  for (const { key } of FILTER_DIMENSIONS) {
    const selected = activeFilters[key];
    if (selected.size > 0 && !selected.has(creative[key] ?? "")) {
      return false;
    }
  }
  return true;
};

const matchesFilters = (creative) => {
  if (!matchesActiveFilters(creative)) {
    return false;
  }
  if (searchTerm) {
    return String(creative.name ?? "").toLowerCase().includes(searchTerm);
  }
  return true;
};

const visibleCreatives = () => creatives().filter(matchesFilters);

// Filters drive selection: everyone matching the active filters is selected,
// everyone else is deselected (no filters = everyone). Checkboxes remain for
// fine-tuning individuals afterwards.
const applyFilterSelection = () => {
  selectedIds = new Set(
    creatives()
      .filter(matchesActiveFilters)
      .map((c) => c.id)
      .filter((id) => Number.isInteger(id))
  );
};

const renderFilters = () => {
  modal.filters.innerHTML = "";
  FILTER_DIMENSIONS.forEach(({ key, label }) => {
    const values = [...new Set(creatives().map((c) => c[key]).filter(Boolean))].sort();
    if (!values.length) {
      return;
    }
    const row = document.createElement("div");
    row.className = "flex flex-wrap items-center gap-1.5";
    const caption = document.createElement("span");
    caption.className = "mr-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400";
    caption.textContent = label;
    row.appendChild(caption);
    values.forEach((value) => {
      const chip = document.createElement("button");
      chip.type = "button";
      const applyState = () => {
        const active = activeFilters[key].has(value);
        chip.className = `rounded-full border px-3 py-1 text-xs font-semibold transition ${
          active
            ? "border-sky-500 bg-sky-50 text-sky-700"
            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
        }`;
      };
      chip.textContent = value;
      chip.addEventListener("click", () => {
        if (activeFilters[key].has(value)) activeFilters[key].delete(value);
        else activeFilters[key].add(value);
        applyState();
        applyFilterSelection();
        renderList();
      });
      applyState();
      row.appendChild(chip);
    });
    modal.filters.appendChild(row);
  });
};

const renderList = () => {
  const visible = visibleCreatives();
  modal.list.innerHTML = "";
  visible.forEach((creative) => {
    const row = document.createElement("label");
    row.className =
      "flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2 transition hover:bg-slate-50";
    const left = document.createElement("span");
    left.className = "flex items-center gap-3 min-w-0";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "accent-sky-600";
    checkbox.checked = selectedIds.has(creative.id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedIds.add(creative.id);
      else selectedIds.delete(creative.id);
      updateFooter();
    });
    const name = document.createElement("span");
    name.className = "truncate text-sm text-slate-800";
    name.textContent = creative.name ?? "";
    left.appendChild(checkbox);
    left.appendChild(name);
    const meta = document.createElement("span");
    meta.className = "shrink-0 text-[10px] text-slate-400";
    meta.textContent = [creative.business_unit, creative.pod].filter(Boolean).join(" · ");
    row.appendChild(left);
    row.appendChild(meta);
    modal.list.appendChild(row);
  });
  if (!visible.length) {
    modal.list.innerHTML =
      '<p class="py-8 text-center text-sm text-slate-400">No creatives match these filters.</p>';
  }
  updateFooter();
};

const updateFooter = () => {
  modal.count.textContent = `${selectedIds.size} of ${creatives().length} creatives selected`;
  modal.confirm.disabled = selectedIds.size === 0;
};

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

const SUMMARY_FIELDS = [
  "id", "name", "department", "business_unit", "sub_business_unit", "pod",
  "market_display", "pool_display", "logged_utilization", "planned_utilization",
  "available_hours", "base_hours", "time_off_hours", "public_holiday_hours",
  "planned_hours", "logged_hours", "overtime_hours",
];

const runExport = async () => {
  if (!selectedIds.size || modal.confirm.disabled) {
    return;
  }
  modal.confirm.disabled = true;
  modal.confirmLabel.textContent = "Generating…";
  modal.error.classList.add("hidden");
  try {
    const period = deps.getPeriodValue?.() ?? "";
    // Bulk daily data for everyone (server caches this for 2 minutes, and it
    // is usually already warm from the dashboard's background prefetch).
    const dailyResponse = await fetch(`/api/creatives/daily-hours${buildQuery(period)}`);
    if (!dailyResponse.ok) {
      throw new Error(`Daily data request failed (${dailyResponse.status})`);
    }
    const daily = (await dailyResponse.json())?.creatives ?? {};

    const rows = creatives()
      .filter((c) => selectedIds.has(c.id))
      .map((c) => {
        const summary = {};
        SUMMARY_FIELDS.forEach((field) => {
          summary[field] = c[field] ?? null;
        });
        const extra = daily[String(c.id)] ?? {};
        summary.days = Array.isArray(extra.days) ? extra.days : [];
        summary.projects = Array.isArray(extra.projects) ? extra.projects : [];
        summary.overtime_projects = Array.isArray(extra.overtime_projects)
          ? extra.overtime_projects
          : [];
        return summary;
      });

    const response = await fetch("/api/creatives/export-xlsx", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_month: period,
        period_label: deps.getPeriodLabel?.() ?? period,
        creatives: rows,
      }),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.error || `Export failed (${response.status})`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `creative-timecards-${period || "export"}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    closeExportModal();
  } catch (error) {
    modal.error.textContent = error?.message || "Export failed. Please try again.";
    modal.error.classList.remove("hidden");
  } finally {
    modal.confirmLabel.textContent = "Export";
    updateFooter();
  }
};
