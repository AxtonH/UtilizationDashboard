// Daily hours card detail: lazy-loads a per-creative breakdown when a card is
// expanded and renders it as a tabbed, fixed-height region (Daily Hours
// calendar / Worked Projects / Overtime) so every card has identical
// structure and height. Data comes from /api/creatives/<id>/daily-hours,
// bulk-warmed in the background by /api/creatives/daily-hours.

let getPeriodValue = () => null;

export const configureDailyHours = (options = {}) => {
  if (typeof options.getPeriodValue === "function") {
    getPeriodValue = options.getPeriodValue;
  }
};

// Session cache of day payloads so re-expanding a card renders instantly.
// Sized to hold the whole roster for a few periods (bulk warming seeds ~80
// entries per viewed month).
const dayCache = new Map(); // `${creativeId}|${period}` -> Promise<{days, projects, overtime_projects}>
const DAY_CACHE_MAX_ENTRIES = 512;

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

const normalizePayload = (payload) => ({
  days: Array.isArray(payload?.days) ? payload.days : [],
  projects: Array.isArray(payload?.projects) ? payload.projects : [],
  overtime_projects: Array.isArray(payload?.overtime_projects) ? payload.overtime_projects : [],
});

const trimDayCache = () => {
  while (dayCache.size > DAY_CACHE_MAX_ENTRIES) {
    dayCache.delete(dayCache.keys().next().value);
  }
};

const fetchDays = (creativeId, period) => {
  const key = `${creativeId}|${period ?? ""}`;
  const cached = dayCache.get(key);
  if (cached) {
    return cached;
  }
  const promise = fetch(`/api/creatives/${creativeId}/daily-hours${buildQuery(period)}`)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Request failed (${response.statusText || response.status})`);
      }
      return response.json();
    })
    .then(normalizePayload);
  // Drop failed fetches from the cache so Retry can re-request.
  promise.catch(() => dayCache.delete(key));
  dayCache.delete(key);
  dayCache.set(key, promise);
  trimDayCache();
  return promise;
};

// Bulk warm: one background request seeds the cache for EVERY creative in the
// period (~5 batched Odoo queries server-side), fired by api.js after the
// dashboard payload has rendered so it never competes with the initial load.
const warmedPeriods = new Set();

export const warmDailyHours = (period) => {
  const key = period ?? "";
  if (warmedPeriods.has(key)) {
    return;
  }
  warmedPeriods.add(key);
  fetch(`/api/creatives/daily-hours${buildQuery(key)}`)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
      }
      return response.json();
    })
    .then((payload) => {
      const perCreative = payload?.creatives;
      if (!perCreative || typeof perCreative !== "object") {
        return;
      }
      Object.entries(perCreative).forEach(([id, data]) => {
        dayCache.set(`${id}|${key}`, Promise.resolve(normalizePayload(data)));
      });
      trimDayCache();
    })
    .catch(() => {
      // Allow a retry on the next payload apply; per-card fetches still work.
      warmedPeriods.delete(key);
    });
};

// Warm the fetch cache when the cursor enters a card so the data is usually
// already loaded by the time the user clicks to expand. No DOM changes.
export const prefetchDailyHours = (card) => {
  const creativeId = Number.parseInt(card?.dataset?.creativeId ?? "", 10);
  if (!Number.isInteger(creativeId) || creativeId <= 0) {
    return;
  }
  fetchDays(creativeId, getPeriodValue() ?? "").catch(() => {});
};

const fmtHours = (value) => {
  const num = Number(value) || 0;
  if (num === 0) {
    return "0";
  }
  return Number.isInteger(num) ? `${num}` : num.toFixed(1).replace(/\.0$/, "");
};

const WEEKDAY_HEADERS = ["S", "M", "T", "W", "T", "F", "S"]; // Sun-first

const dayTooltip = (day, dateObj) => {
  const label = dateObj.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
  const parts = [`Logged ${fmtHours(day.logged)}h`, `Booked ${fmtHours(day.booked)}h`];
  if (day.overtime > 0) {
    parts.push(`Overtime ${fmtHours(day.overtime)}h`);
  }
  if (day.time_off > 0) {
    parts.push(`Time off ${fmtHours(day.time_off)}h`);
  }
  if (day.holiday > 0) {
    parts.push(`Holiday ${fmtHours(day.holiday)}h`);
  }
  return `${label} — ${parts.join(" · ")}`;
};

const buildDayCell = (day, todayKey) => {
  const dateObj = new Date(`${day.date}T00:00:00`);
  const isToday = day.date === todayKey;
  const isFuture = day.date > todayKey;
  const hasActivity = day.logged > 0 || day.booked > 0 || day.overtime > 0;
  const isWeekend = (day.expected ?? 0) === 0;
  const fullHoliday = day.holiday > 0 && day.holiday >= (day.expected || 0) && !hasActivity;
  const fullTimeOff =
    day.time_off > 0 && (day.expected || 0) > 0 && day.time_off >= day.expected && !hasActivity;
  const partialTimeOff = day.time_off > 0 && !fullTimeOff;

  const cell = document.createElement("div");
  cell.setAttribute("title", dayTooltip(day, dateObj));

  // Fixed cell height: a day with an OT badge or TO/PH marker must not be
  // taller than an empty weekend cell, or week rows render unevenly.
  let cellClass = "flex h-12 flex-col items-center rounded-md border px-0.5 py-1 text-center";
  let dayNumClass = "text-[9px] font-medium text-slate-400";
  let valueHtml = "";

  if (fullHoliday) {
    cellClass += " border-red-100 bg-red-50";
    valueHtml = '<div class="text-[10px] font-semibold leading-tight text-red-600">PH</div>';
  } else if (fullTimeOff) {
    cellClass += " border-orange-100 bg-orange-50";
    valueHtml = '<div class="text-[10px] font-semibold leading-tight text-orange-600">TO</div>';
  } else if (isWeekend && !hasActivity) {
    cellClass += " border-transparent bg-slate-50";
    dayNumClass = "text-[9px] font-medium text-slate-300";
  } else if (isFuture) {
    cellClass += " border-slate-100 bg-white opacity-70";
    if (day.booked > 0) {
      valueHtml = `<div class="text-[10px] font-semibold leading-tight text-slate-400">&ndash;/${fmtHours(day.booked)}</div>`;
    }
  } else {
    // Past or current workday (or weekend with activity): status tint.
    const logged = Number(day.logged) || 0;
    const booked = Number(day.booked) || 0;
    if (logged > 0 && logged >= booked - 0.01) {
      cellClass += " border-emerald-100 bg-emerald-50";
    } else if (logged > 0) {
      cellClass += " border-amber-200 bg-amber-50";
    } else if (booked > 0 || (!isWeekend && !partialTimeOff)) {
      cellClass += " border-rose-200 bg-rose-50";
    } else {
      cellClass += " border-slate-200 bg-white";
    }
    valueHtml = `<div class="text-[10px] font-semibold leading-tight text-slate-700">${fmtHours(logged)}/${fmtHours(booked)}</div>`;
  }

  if (isToday) {
    cellClass += " ring-1 ring-sky-300";
  }
  cell.className = cellClass;

  const marker = partialTimeOff
    ? ' <span class="inline-block h-1 w-1 rounded-full bg-orange-400 align-middle"></span>'
    : "";
  const overtimeHtml =
    day.overtime > 0
      ? `<div class="mt-0.5 text-[9px] font-bold leading-none text-violet-700">${fmtHours(day.overtime)} OT</div>`
      : "";

  cell.innerHTML =
    `<div class="${dayNumClass}">${dateObj.getDate()}${marker}</div>` + valueHtml + overtimeHtml;
  return cell;
};

const buildMonthGrid = (days, todayKey, showTitle) => {
  const wrapper = document.createElement("div");

  if (showTitle && days.length > 0) {
    const first = new Date(`${days[0].date.slice(0, 7)}-01T00:00:00`);
    const title = document.createElement("p");
    title.className = "mb-1 text-xs font-semibold text-slate-600";
    title.textContent = first.toLocaleDateString("en-US", { month: "long", year: "numeric" });
    wrapper.appendChild(title);
  }

  const grid = document.createElement("div");
  grid.className = "grid grid-cols-7 gap-1";

  WEEKDAY_HEADERS.forEach((label) => {
    const header = document.createElement("div");
    header.className = "text-center text-[9px] font-semibold uppercase text-slate-400";
    header.textContent = label;
    grid.appendChild(header);
  });

  let cellCount = 0;
  if (days.length > 0) {
    const leadingBlanks = new Date(`${days[0].date}T00:00:00`).getDay(); // 0 = Sunday
    for (let i = 0; i < leadingBlanks; i += 1) {
      grid.appendChild(document.createElement("div"));
    }
    cellCount = leadingBlanks;
  }

  days.forEach((day) => grid.appendChild(buildDayCell(day, todayKey)));
  cellCount += days.length;

  // Pad every grid to 6 full week rows (42 cells) so calendars are the same
  // height on every card regardless of how the month falls.
  while (cellCount < 42) {
    grid.appendChild(document.createElement("div"));
    cellCount += 1;
  }

  wrapper.appendChild(grid);
  return wrapper;
};

const buildLegend = () => {
  const legend = document.createElement("div");
  legend.className = "mt-2 space-y-1 text-[9px] text-slate-500";
  const swatch = (classes) =>
    `<span class="inline-block h-2 w-2 rounded-sm border ${classes} align-middle"></span>`;
  const row = (items) =>
    `<div class="flex flex-wrap items-center gap-x-3 gap-y-1">${items
      .map((item) => `<span class="inline-flex items-center gap-1">${item}</span>`)
      .join("")}</div>`;
  legend.innerHTML =
    row([
      `${swatch("border-emerald-100 bg-emerald-50")} logged &ge; booked`,
      `${swatch("border-amber-200 bg-amber-50")} under-logged`,
      `${swatch("border-rose-200 bg-rose-50")} no hours`,
    ]) +
    row([
      '<span class="font-semibold text-orange-600">TO</span> time off',
      '<span class="font-semibold text-red-600">PH</span> PrezHoliday',
      '<span class="font-bold text-violet-700">OT</span> overtime',
    ]);
  return legend;
};

// ---------------------------------------------------------------------------
// Tabbed detail region. The Daily Hours panel stays in normal flow and
// defines the region's height (its 6-week grid is deterministic), while the
// Projects/Overtime panels are absolutely stacked inside the same box and
// scroll when longer. No hardcoded heights, no dead space, and switching
// tabs never changes the card height.
// ---------------------------------------------------------------------------

const OVERLAY_PANEL_CLASS = "absolute inset-0 overflow-y-auto";

const buildEmptyState = (message) => {
  const empty = document.createElement("div");
  empty.className = "flex h-full items-center justify-center py-10 text-xs text-slate-400";
  empty.textContent = message;
  return empty;
};

const buildHintRow = (text) => {
  const hint = document.createElement("p");
  hint.className = "mb-1 text-right text-[9px] text-slate-400";
  hint.textContent = text;
  return hint;
};

const buildStackedList = (entries, { valueText, valueTitle, valueClass }) => {
  const list = document.createElement("div");
  list.className = "divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white/70 px-3";
  entries.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "flex items-center justify-between gap-3 py-1.5";

    const name = document.createElement("span");
    name.className = "min-w-0 truncate text-[11px] font-medium text-slate-600";
    name.textContent = entry.project_name ?? "Unassigned Project";
    name.title = name.textContent;
    row.appendChild(name);

    const value = document.createElement("span");
    value.className = `whitespace-nowrap text-[11px] font-semibold ${valueClass}`;
    value.textContent = valueText(entry);
    value.title = valueTitle(entry);
    row.appendChild(value);

    list.appendChild(row);
  });
  return list;
};

const buildDaysPanel = (days, todayKey) => {
  const panel = document.createElement("div");
  if (!days.length) {
    panel.appendChild(buildEmptyState("No daily data for this period."));
    return panel;
  }

  // Group by month so quarter views render one grid per month.
  const months = new Map();
  days.forEach((day) => {
    const key = String(day.date).slice(0, 7);
    if (!months.has(key)) {
      months.set(key, []);
    }
    months.get(key).push(day);
  });

  const monthsWrapper = document.createElement("div");
  monthsWrapper.className = "space-y-3";
  const showTitles = months.size > 1;
  months.forEach((monthDays) => {
    monthsWrapper.appendChild(buildMonthGrid(monthDays, todayKey, showTitles));
  });
  panel.appendChild(monthsWrapper);
  panel.appendChild(buildLegend());
  return panel;
};

const buildProjectsPanel = (projects) => {
  const panel = document.createElement("div");
  panel.className = OVERLAY_PANEL_CLASS;
  if (!projects.length) {
    panel.appendChild(buildEmptyState("No projects this period."));
    return panel;
  }
  panel.appendChild(buildHintRow("logged/booked"));
  panel.appendChild(
    buildStackedList(projects, {
      valueClass: "text-slate-800",
      valueText: (p) => `${fmtHours(p.logged)}/${fmtHours(p.booked)}`,
      valueTitle: (p) => `Logged ${fmtHours(p.logged)}h · Booked ${fmtHours(p.booked)}h`,
    })
  );
  return panel;
};

const buildOvertimePanel = (entries) => {
  const panel = document.createElement("div");
  panel.className = OVERLAY_PANEL_CLASS;
  if (!entries.length) {
    panel.appendChild(buildEmptyState("No overtime this period."));
    return panel;
  }
  panel.appendChild(buildHintRow("overtime/logged"));
  panel.appendChild(
    buildStackedList(entries, {
      valueClass: "text-slate-800",
      valueText: (e) => `${fmtHours(e.overtime)}/${fmtHours(e.logged_overtime)}`,
      valueTitle: (e) =>
        `Overtime taken ${fmtHours(e.overtime)}h · Logged over booked ${fmtHours(e.logged_overtime)}h`,
    })
  );
  return panel;
};

const TAB_BASE = "flex-1 rounded-full px-2 py-1 text-center text-[10px] font-semibold transition";
const TAB_ACTIVE = `${TAB_BASE} bg-white text-slate-800 shadow-sm`;
const TAB_INACTIVE = `${TAB_BASE} text-slate-500 hover:text-slate-700`;

const buildTabbedDetail = (payload, todayKey) => {
  const root = document.createElement("div");

  // Full-width segmented control: three equal segments, no dead space.
  const bar = document.createElement("div");
  bar.className = "flex w-full rounded-full bg-slate-100 p-0.5";

  const region = document.createElement("div");
  region.className = "relative mt-2";

  const panels = {
    days: buildDaysPanel(payload.days, todayKey),
    projects: buildProjectsPanel(payload.projects),
    overtime: buildOvertimePanel(payload.overtime_projects),
  };
  const labels = {
    days: "Daily Hours",
    projects: payload.projects.length ? `Projects (${payload.projects.length})` : "Projects",
    overtime: payload.overtime_projects.length
      ? `Overtime (${payload.overtime_projects.length})`
      : "Overtime",
  };

  const buttons = {};
  const activate = (activeKey) => {
    Object.keys(panels).forEach((key) => {
      if (key === "days") {
        // The days panel defines the region height, so it stays in the
        // layout and is only visually hidden when another tab is active.
        panels.days.classList.toggle("invisible", activeKey !== "days");
      } else {
        panels[key].classList.toggle("hidden", key !== activeKey);
      }
      buttons[key].className = key === activeKey ? TAB_ACTIVE : TAB_INACTIVE;
    });
  };

  Object.keys(panels).forEach((key) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = labels[key];
    button.addEventListener("click", () => activate(key));
    buttons[key] = button;
    bar.appendChild(button);
    region.appendChild(panels[key]);
  });
  activate("days");

  root.appendChild(bar);
  root.appendChild(region);
  return root;
};

export const mountDailyHours = (card) => {
  const creativeId = Number.parseInt(card?.dataset?.creativeId ?? "", 10);
  const details = card?.querySelector?.("[data-card-details]");
  if (!Number.isInteger(creativeId) || creativeId <= 0 || !details) {
    return;
  }

  let container = details.querySelector("[data-daily-hours]");
  if (!container) {
    container = document.createElement("div");
    container.dataset.dailyHours = "true";
    container.className = "mt-4 border-t border-slate-200 pt-3";
    details.appendChild(container);
  }

  const period = getPeriodValue() ?? "";
  const mountKey = `${creativeId}|${period}`;
  if (container.dataset.mountKey === mountKey) {
    return;
  }
  container.dataset.mountKey = mountKey;

  container.innerHTML =
    '<p class="text-xs text-slate-400">Loading daily hours&hellip;</p>';

  const now = new Date();
  const todayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
    now.getDate()
  ).padStart(2, "0")}`;
  fetchDays(creativeId, period)
    .then((payload) => {
      if (container.dataset.mountKey !== mountKey) {
        return; // A newer mount (period switch) superseded this one.
      }
      container.innerHTML = "";
      container.appendChild(buildTabbedDetail(payload, todayKey));
    })
    .catch(() => {
      if (container.dataset.mountKey !== mountKey) {
        return;
      }
      container.innerHTML = "";
      const error = document.createElement("p");
      error.className = "text-xs text-rose-500";
      error.textContent = "Couldn't load daily hours. ";
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "font-semibold text-sky-600 hover:underline";
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        delete container.dataset.mountKey;
        mountDailyHours(card);
      });
      error.appendChild(retry);
      container.appendChild(error);
    });
};
