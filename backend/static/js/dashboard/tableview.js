// Table view for the Creatives Time Cards section: one row per creative, one
// column per day of the selected period (same logged/booked color language as
// the daily-hours calendar in daycal.js), plus a totals block carrying every
// hour metric from the grid cards and a dark sticky Logged anchor column.
// Expanding a row reveals per-project sub-rows (period totals only — the
// daily-hours API has no per-project daily split). Day data comes from the
// same bulk endpoint daycal.js warms at page load, so switching views is
// usually instant.
import { formatHours } from "./utils.js";
import {
  fetchBulkDailyHours,
  fmtHours,
  buildDayTooltipHtml,
  buildProjectsByDate,
} from "./daycal.js";
import { showTooltip, hideTooltip } from "./tooltip.js";
import {
  getHoursDisplay,
  getUtilizationDisplay,
  resolveUtilizationStatus,
  applyNewJoinerPillState,
  bindNewJoinerToggle,
} from "./cards.js";

const STATUS_DOT_CLASSES = {
  healthy: "bg-emerald-400",
  warning: "bg-amber-400",
  critical: "bg-rose-400",
};

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );

const formatPercent = (numerator, denominator) => {
  if (!(denominator > 0)) {
    return "—";
  }
  const rounded = Math.round((numerator / denominator) * 1000) / 10;
  return Number.isInteger(rounded) ? `${rounded}%` : `${rounded.toFixed(1)}%`;
};

// Totals block: the hour metrics from the grid cards, in card order. Logged
// hours render separately as the sticky dark anchor column on the far right.
// `projectValue` marks the columns that also carry per-project sub-row data.
const TOTAL_COLUMNS = [
  {
    label: "Base",
    tooltip: "Standard working hours in the period",
    textClass: "text-teal-700",
    value: (c) => getHoursDisplay(c.base_hours_display, c.base_hours),
    footer: (sums) => formatHours(sums.base),
  },
  {
    label: "Time Off",
    tooltip: "Approved leaves",
    textClass: "text-orange-700",
    value: (c) => getHoursDisplay(c.time_off_hours_display, c.time_off_hours),
    footer: (sums) => formatHours(sums.timeOff),
  },
  {
    label: "Holiday",
    tooltip: "Public holiday hours",
    textClass: "text-red-700",
    value: (c) => getHoursDisplay(c.public_holiday_hours_display, c.public_holiday_hours),
    footer: (sums) => formatHours(sums.holiday),
  },
  {
    label: "Available",
    tooltip: "Total hours available for work",
    textClass: "text-slate-800",
    value: (c) => getHoursDisplay(c.available_hours_display, c.available_hours),
    footer: (sums) => formatHours(sums.available),
  },
  {
    label: "Booked",
    tooltip: "Work scheduled on Planning App",
    textClass: "text-blue-700",
    value: (c) => getHoursDisplay(c.planned_hours_display, c.planned_hours),
    footer: (sums) => formatHours(sums.booked),
    projectValue: (p) => (p.booked > 0 ? formatHours(p.booked) : ""),
  },
  {
    label: "OT",
    tooltip: "Approved overtime requests in the period",
    textClass: "text-violet-700",
    value: (c) => getHoursDisplay(c.overtime_hours_display, c.overtime_hours),
    footer: (sums) => formatHours(sums.overtime),
    projectValue: (p) => (p.overtime > 0 ? formatHours(p.overtime) : ""),
  },
  {
    label: "Booked %",
    tooltip: "Percentage of available hours scheduled on the Planning App",
    textClass: "text-slate-800",
    value: (c) => getUtilizationDisplay(c.planned_utilization_display, c.planned_utilization),
    footer: (sums) => formatPercent(sums.booked, sums.available),
  },
  {
    label: "Logged %",
    tooltip: "Percentage of available hours already logged",
    textClass: "text-slate-800",
    value: (c) => getUtilizationDisplay(c.logged_utilization_display, c.logged_utilization),
    footer: (sums) => formatPercent(sums.logged, sums.available),
  },
];

// Merge the projects (logged/booked, plus the per-day `days` map) and
// overtime_projects (overtime) lists into one per-project entry so a sub-row
// can show all of them.
const mergeProjects = (detail) => {
  const map = new Map();
  const entryFor = (rawName) => {
    const name = rawName ?? "Unassigned Project";
    if (!map.has(name)) {
      map.set(name, { name, logged: 0, booked: 0, overtime: 0, days: {} });
    }
    return map.get(name);
  };
  (detail?.projects ?? []).forEach((p) => {
    const entry = entryFor(p.project_name);
    entry.logged = Number(p.logged) || 0;
    entry.booked = Number(p.booked) || 0;
    if (p.days && typeof p.days === "object") {
      // Shallow copy: the OT merge below layers onto these entries and the
      // payload objects are shared via daycal's cache.
      entry.days = { ...p.days };
    }
  });
  (detail?.overtime_projects ?? []).forEach((p) => {
    const entry = entryFor(p.project_name);
    entry.overtime = Number(p.overtime) || 0;
    Object.entries(p.days ?? {}).forEach(([date, hours]) => {
      entry.days[date] = { ...(entry.days[date] ?? {}), overtime: Number(hours) || 0 };
    });
  });
  return [...map.values()].sort((a, b) => b.logged - a.logged);
};

const DAY_CELL_BASE =
  "min-w-11 border-b border-r border-slate-200 px-1 py-1 text-center align-middle text-[10px] font-semibold leading-tight";

// Same day semantics as daycal.js buildDayCell, laid out for a table cell
// (no day number — the column header carries the date). The data-day-cell
// attribute feeds the delegated rich tooltip (shared with the calendar).
const dayCellHtml = (day, todayKey) => {
  if (!day) {
    return `<td class="${DAY_CELL_BASE} text-slate-300">&ndash;</td>`;
  }
  const isToday = day.date === todayKey;
  const isFuture = day.date > todayKey;
  const logged = Number(day.logged) || 0;
  const booked = Number(day.booked) || 0;
  const overtime = Number(day.overtime) || 0;
  const hasActivity = logged > 0 || booked > 0 || overtime > 0;
  const isWeekend = (day.expected ?? 0) === 0;
  const fullHoliday = day.holiday > 0 && day.holiday >= (day.expected || 0) && !hasActivity;
  const fullTimeOff =
    day.time_off > 0 && (day.expected || 0) > 0 && day.time_off >= day.expected && !hasActivity;
  const partialTimeOff = day.time_off > 0 && !fullTimeOff;

  let tint = "";
  let content = "";
  if (fullHoliday) {
    tint = "bg-red-50";
    content = '<div class="text-red-600">PH</div>';
  } else if (fullTimeOff) {
    tint = "bg-orange-50";
    content = '<div class="text-orange-600">TO</div>';
  } else if (isWeekend && !hasActivity) {
    tint = "bg-slate-50";
  } else if (isFuture) {
    if (booked > 0) {
      content = `<div class="text-slate-400">&ndash;/${fmtHours(booked)}</div>`;
    }
  } else {
    if (logged > 0 && logged >= booked - 0.01) {
      tint = "bg-emerald-50";
    } else if (logged > 0) {
      tint = "bg-amber-50";
    } else if (booked > 0 || (!isWeekend && !partialTimeOff)) {
      tint = "bg-rose-50";
    }
    const marker = partialTimeOff
      ? ' <span class="inline-block h-1 w-1 rounded-full bg-orange-400 align-middle"></span>'
      : "";
    content = `<div class="text-slate-700">${fmtHours(logged)}/${fmtHours(booked)}${marker}</div>`;
  }
  if (overtime > 0) {
    content += `<div class="text-[9px] font-bold text-violet-700">${fmtHours(overtime)} OT</div>`;
  }
  const todayRing = isToday ? " ring-1 ring-inset ring-sky-300" : "";
  return `<td data-day-cell="${day.date}" class="${DAY_CELL_BASE} ${tint}${todayRing}">${content}</td>`;
};

const dayHeaderHtml = (dateStr, todayKey, workdayDates, multiMonth) => {
  const dateObj = new Date(`${dateStr}T00:00:00`);
  const isToday = dateStr === todayKey;
  const isOffDay = !workdayDates.has(dateStr);
  const monthTag =
    multiMonth && dateObj.getDate() === 1
      ? `<div class="text-[8px] font-bold text-sky-600">${dateObj.toLocaleDateString("en-US", {
          month: "short",
        })}</div>`
      : "";
  const toneClass = isToday
    ? "bg-sky-100 text-sky-700"
    : isOffDay
      ? "bg-slate-50 text-slate-300"
      : "bg-slate-50";
  return `<th data-day-col="${dateStr}" class="min-w-11 border-b border-r border-slate-200 border-b-slate-300 px-1 py-1.5 text-center ${toneClass}" title="${escapeHtml(
    dateObj.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })
  )}">${monthTag}<div class="text-[9px] font-semibold uppercase">${dateObj.toLocaleDateString(
    "en-US",
    { weekday: "narrow" }
  )}</div><div class="text-[11px] font-semibold">${dateObj.getDate()}</div></th>`;
};

const TOTAL_CELL_BASE =
  "whitespace-nowrap border-b border-r border-slate-200 px-2 py-1 text-right text-[11px] font-semibold";
// The frozen Logged anchor column: light sky so it reads as part of the table
// rather than a floating panel; the sky-300 left edge is its only seam.
const LOGGED_CELL_BASE =
  "sticky right-0 z-10 whitespace-nowrap border-b border-l border-sky-200 border-l-sky-300 bg-sky-50 px-3 py-1 text-right text-[11px]";
const LOGGED_CELL_MAIN = `${LOGGED_CELL_BASE} font-bold text-sky-900`;
const LOGGED_CELL_PROJECT = `${LOGGED_CELL_BASE} font-semibold text-sky-700`;

const creativeRowHtml = (creative, dates, dayData, todayKey, expandedIds) => {
  const detail = dayData?.[String(creative.id)] ?? null;
  const daysByDate = new Map((detail?.days ?? []).map((d) => [d.date, d]));
  const projects = mergeProjects(detail);
  const hasProjects = projects.length > 0;
  const expanded = hasProjects && expandedIds.has(String(creative.id));
  const status = resolveUtilizationStatus(creative);

  const njHtml = creative.is_new_joiner_ramp
    ? `<span data-nj-toggle data-nj-compact="true" role="button" data-included="${
        creative.new_joiner_hours_included === true ? "true" : "false"
      }"></span>`
    : "";
  const chevron = hasProjects
    ? `<span data-row-chevron class="material-symbols-rounded shrink-0 text-sm text-slate-400 transition${
        expanded ? " rotate-180" : ""
      }">expand_more</span>`
    : "";
  const deptHtml = creative.department
    ? `<div class="truncate text-[10px] font-medium uppercase tracking-wide text-slate-400">${escapeHtml(
        creative.department
      )}</div>`
    : "";
  const nameCell = `<td class="sticky left-0 z-10 min-w-52 max-w-64 border-b border-r border-slate-200 border-r-slate-300 bg-white px-3 py-1.5 transition group-hover:bg-slate-50"><div class="flex items-center gap-2"><span class="h-2 w-2 shrink-0 rounded-full ${
    STATUS_DOT_CLASSES[status] ?? STATUS_DOT_CLASSES.healthy
  }" title="Utilization: ${escapeHtml(status)}"></span><div class="min-w-0 flex-1"><div class="flex items-center gap-1.5"><span class="truncate text-xs font-semibold text-slate-800" title="${escapeHtml(
    creative.name ?? ""
  )}">${escapeHtml(creative.name ?? "Unnamed Creative")}</span>${njHtml}</div>${deptHtml}</div>${chevron}</div></td>`;

  const dayCells = dates.map((date) => dayCellHtml(daysByDate.get(date), todayKey)).join("");
  const totalCells = TOTAL_COLUMNS.map(
    (col) =>
      `<td class="${TOTAL_CELL_BASE} ${col.textClass}">${escapeHtml(col.value(creative))}</td>`
  ).join("");
  const loggedCell = `<td class="${LOGGED_CELL_MAIN}">${escapeHtml(
    getHoursDisplay(creative.logged_hours_display, creative.logged_hours)
  )}</td>`;

  const mainRow = `<tr data-creative-row="${creative.id}" data-has-projects="${
    hasProjects ? "true" : "false"
  }" data-expanded="${expanded ? "true" : "false"}" class="group${
    hasProjects ? " cursor-pointer" : ""
  } transition hover:bg-slate-50">${nameCell}${dayCells}${totalCells}${loggedCell}</tr>`;

  const projectRows = projects
    .map((p) => {
      const projectTotals = TOTAL_COLUMNS.map(
        (col) =>
          `<td class="${TOTAL_CELL_BASE} ${col.textClass}">${
            col.projectValue ? escapeHtml(col.projectValue(p)) : ""
          }</td>`
      ).join("");
      // Per-day logged/booked for this project (from the payload's `days`
      // map); quiet days stay blank so the parent row's tints keep the focus.
      const projectDayCells = dates
        .map((date) => {
          const day = p.days?.[date];
          const logged = Number(day?.logged) || 0;
          const booked = Number(day?.booked) || 0;
          const overtime = Number(day?.overtime) || 0;
          if (logged <= 0 && booked <= 0 && overtime <= 0) {
            return '<td class="min-w-11 border-b border-r border-slate-200 px-1 py-1"></td>';
          }
          const titleParts = [`Logged ${fmtHours(logged)}h`, `Booked ${fmtHours(booked)}h`];
          if (overtime > 0) {
            titleParts.push(`Overtime ${fmtHours(overtime)}h`);
          }
          const hoursHtml =
            logged > 0 || booked > 0 ? `<div>${fmtHours(logged)}/${fmtHours(booked)}</div>` : "";
          const overtimeHtml =
            overtime > 0
              ? `<div class="text-[9px] font-bold text-violet-700">${fmtHours(overtime)} OT</div>`
              : "";
          return `<td class="min-w-11 border-b border-r border-slate-200 px-1 py-1 text-center text-[10px] font-medium leading-tight text-slate-500" title="${escapeHtml(
            `${p.name} — ${titleParts.join(" · ")}`
          )}">${hoursHtml}${overtimeHtml}</td>`;
        })
        .join("");
      return `<tr data-project-row-for="${creative.id}" class="${
        expanded ? "" : "hidden "
      }bg-slate-50/60"><td class="sticky left-0 z-10 min-w-52 max-w-64 border-b border-r border-slate-200 border-r-slate-300 bg-slate-50 py-1 pl-9 pr-3"><div class="line-clamp-2 break-words text-[11px] font-medium leading-snug text-slate-600" title="${escapeHtml(
        p.name
      )}">${escapeHtml(p.name)}</div></td>${projectDayCells}${projectTotals}<td class="${LOGGED_CELL_PROJECT}">${
        p.logged > 0 ? formatHours(p.logged) : ""
      }</td></tr>`;
    })
    .join("");

  return mainRow + projectRows;
};

const footerRowHtml = (creatives, dates, dayData) => {
  const sums = creatives.reduce(
    (acc, c) => {
      acc.base += Number(c.base_hours) || 0;
      acc.timeOff += Number(c.time_off_hours) || 0;
      acc.holiday += Number(c.public_holiday_hours) || 0;
      acc.available += Number(c.available_hours) || 0;
      acc.booked += Number(c.planned_hours) || 0;
      acc.overtime += Number(c.overtime_hours) || 0;
      acc.logged += Number(c.logged_hours) || 0;
      return acc;
    },
    { base: 0, timeOff: 0, holiday: 0, available: 0, booked: 0, overtime: 0, logged: 0 }
  );

  const dayCells = dates
    .map((date) => {
      let logged = 0;
      let booked = 0;
      creatives.forEach((c) => {
        const day = dayData?.[String(c.id)]?.days?.find?.((d) => d.date === date);
        if (day) {
          logged += Number(day.logged) || 0;
          booked += Number(day.booked) || 0;
        }
      });
      return `<td class="border-r border-t border-slate-200 border-t-slate-300 bg-slate-50 px-1 py-1.5 text-center text-[10px] font-semibold text-slate-600" title="Logged ${fmtHours(
        logged
      )}h · Booked ${fmtHours(booked)}h">${logged > 0 ? fmtHours(logged) : ""}</td>`;
    })
    .join("");

  const totalCells = TOTAL_COLUMNS.map(
    (col) =>
      `<td class="whitespace-nowrap border-r border-t border-slate-200 border-t-slate-300 bg-slate-50 px-2 py-1.5 text-right text-[11px] font-bold ${col.textClass}">${escapeHtml(
        col.footer(sums)
      )}</td>`
  ).join("");

  return `<tr><td class="sticky left-0 z-10 border-r border-t border-slate-300 bg-slate-50 px-3 py-1.5 text-[11px] font-bold text-slate-700">All creatives (${
    creatives.length
  })</td>${dayCells}${totalCells}<td class="sticky right-0 z-10 whitespace-nowrap border-l border-t border-slate-300 border-l-sky-300 bg-sky-100 px-3 py-1.5 text-right text-[11px] font-bold text-sky-900">${formatHours(
    sums.logged
  )}</td></tr>`;
};

const LEGEND_HTML = `<div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-slate-500">
  <span class="inline-flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-sm border border-emerald-100 bg-emerald-50 align-middle"></span> logged &ge; booked</span>
  <span class="inline-flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-sm border border-amber-200 bg-amber-50 align-middle"></span> under-logged</span>
  <span class="inline-flex items-center gap-1"><span class="inline-block h-2 w-2 rounded-sm border border-rose-200 bg-rose-50 align-middle"></span> no hours</span>
  <span class="inline-flex items-center gap-1"><span class="font-semibold text-orange-600">TO</span> time off</span>
  <span class="inline-flex items-center gap-1"><span class="font-semibold text-red-600">PH</span> PrezHoliday</span>
  <span class="inline-flex items-center gap-1"><span class="font-bold text-violet-700">OT</span> overtime</span>
  <span class="text-slate-400">Cells show logged/booked hours per day. Click a row to see its projects.</span>
</div>`;

const DAY_DATA_NOTICE_HTML = `<div class="mb-3 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
  <span class="material-symbols-rounded text-sm" aria-hidden="true">warning</span>
  <span>Couldn't load the daily breakdown for this period; totals are still accurate.</span>
  <button type="button" data-table-retry class="font-semibold text-sky-600 hover:underline">Retry</button>
</div>`;

const buildTableHtml = (creatives, dayData, expandedIds) => {
  // Day columns: union of dates across the visible roster (they normally all
  // span the same period). A date column counts as a working day if ANY
  // creative has expected hours on it — used only for header shading.
  const dateSet = new Set();
  const workdayDates = new Set();
  creatives.forEach((c) => {
    (dayData?.[String(c.id)]?.days ?? []).forEach((day) => {
      dateSet.add(day.date);
      if ((day.expected ?? 0) > 0) {
        workdayDates.add(day.date);
      }
    });
  });
  const dates = [...dateSet].sort();
  const multiMonth = dates.length > 0 && dates.some((d) => !d.startsWith(dates[0].slice(0, 7)));

  const now = new Date();
  const todayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
    now.getDate()
  ).padStart(2, "0")}`;

  const headerCells =
    `<th class="sticky left-0 z-10 min-w-52 border-b border-r border-slate-300 bg-slate-50 px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-500">Creative</th>` +
    dates.map((date) => dayHeaderHtml(date, todayKey, workdayDates, multiMonth)).join("") +
    TOTAL_COLUMNS.map(
      (col) =>
        `<th class="whitespace-nowrap border-b border-r border-slate-200 border-b-slate-300 bg-slate-50 px-2 py-2 text-right text-[10px] font-semibold uppercase tracking-wide text-slate-500 cursor-help" title="${escapeHtml(
          col.tooltip
        )}">${escapeHtml(col.label)}</th>`
    ).join("") +
    `<th data-logged-col class="sticky right-0 z-10 whitespace-nowrap border-b border-l border-slate-300 border-l-sky-300 bg-sky-100 px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wide text-sky-800 cursor-help" title="Work actually recorded in the period">Logged</th>`;

  const bodyRows = creatives
    .map((creative) => creativeRowHtml(creative, dates, dayData, todayKey, expandedIds))
    .join("");

  return `${dayData ? "" : DAY_DATA_NOTICE_HTML}<div data-table-scroll class="relative overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
  <table class="w-full min-w-max border-separate border-spacing-0">
    <thead><tr>${headerCells}</tr></thead>
    <tbody>${bodyRows}</tbody>
    <tfoot>${footerRowHtml(creatives, dates, dayData)}</tfoot>
  </table>
</div>${LEGEND_HTML}`;
};

// Seam fit: make the frozen columns read as "just more columns". The strip
// between the frozen name column and the frozen Logged column is divided into
// an exact whole number of day columns (each at least MIN_DAY_COL_PX wide),
// and the scroll position moves in whole columns — so BOTH seams always land
// on cell boundaries with no half-visible cell peeking out at either edge.
// The initial position puts today as the last fully visible day; CSS
// scroll-snap eases user scrolling back onto clean boundaries afterwards.
const MIN_DAY_COL_PX = 44; // keep in sync with min-w-11 on the day cells

const fitAndSnapDayColumns = (container) => {
  const scroller = container.querySelector("[data-table-scroll]");
  const loggedHeader = scroller?.querySelector("[data-logged-col]");
  const nameHeader = scroller?.querySelector("thead th");
  const dayHeaders = scroller ? [...scroller.querySelectorAll("th[data-day-col]")] : [];
  if (!scroller || !loggedHeader || !nameHeader || dayHeaders.length === 0) {
    return;
  }

  const strip = scroller.clientWidth - nameHeader.offsetWidth - loggedHeader.offsetWidth;
  if (strip < MIN_DAY_COL_PX) {
    return;
  }
  const visibleCount = Math.min(
    dayHeaders.length,
    Math.max(1, Math.floor(strip / MIN_DAY_COL_PX))
  );
  const colWidth = strip / visibleCount;
  dayHeaders.forEach((th) => {
    const width = `${colWidth}px`;
    th.style.width = width;
    th.style.minWidth = width;
    th.style.maxWidth = width;
    th.style.scrollSnapAlign = "start";
  });
  scroller.style.scrollSnapType = "x proximity";
  // Snap boundaries sit where a day column's left edge meets the seam of the
  // frozen name column, i.e. whole multiples of colWidth.
  scroller.style.scrollPaddingLeft = `${nameHeader.offsetWidth}px`;

  const now = new Date();
  const todayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
    now.getDate()
  ).padStart(2, "0")}`;
  const todayIndex = dayHeaders.findIndex((th) => th.dataset.dayCol === todayKey);
  const firstVisible = todayIndex >= 0 ? Math.max(0, todayIndex - visibleCount + 1) : 0;
  scroller.scrollLeft = firstVisible * colWidth;
};

export function createTableView({ container, getPeriodValue }) {
  let creatives = [];
  let active = false;
  let renderToken = 0;
  const expandedIds = new Set();

  // Day-cell tooltips: same rich panel as the calendar view, built on demand
  // from the last render's day data (delegated — the table has thousands of
  // cells, so no per-cell listeners).
  let hoverDayData = null;
  const projectsByDateCache = new Map(); // creative id -> Map(date -> breakdown)

  // Page-viewport sticky header. The table scrolls horizontally inside its
  // own container, so a CSS-sticky thead can't pin to the page. Instead a
  // fixed clone of the header (appended to <body>, column widths copied from
  // the live cells) fades in whenever the real header scrolls above the
  // viewport, and mirrors the scroller's scrollLeft — its own overflow-hidden
  // wrapper is a scrollport, so the frozen name/Logged cells keep sticking.
  let floatingHeader = null; // { wrapper, table }

  const getScroller = () => container?.querySelector("[data-table-scroll]");

  const destroyFloatingHeader = () => {
    floatingHeader?.wrapper.remove();
    floatingHeader = null;
  };

  const syncFloatingHeaderWidths = () => {
    const scroller = getScroller();
    const table = scroller?.querySelector("table");
    if (!floatingHeader || !table) {
      return;
    }
    const sourceCells = table.querySelectorAll("thead th");
    const cloneCells = floatingHeader.table.querySelectorAll("thead th");
    if (sourceCells.length !== cloneCells.length) {
      return;
    }
    // table-layout: fixed makes the clone honor the copied widths exactly;
    // auto layout would re-distribute them and drift out of register with
    // the real columns (visibly so after 40+ columns).
    let totalWidth = 0;
    sourceCells.forEach((th, i) => {
      const width = th.getBoundingClientRect().width;
      totalWidth += width;
      cloneCells[i].style.width = `${width}px`;
      cloneCells[i].style.minWidth = `${width}px`;
      cloneCells[i].style.maxWidth = `${width}px`;
    });
    floatingHeader.table.style.tableLayout = "fixed";
    floatingHeader.table.style.width = `${totalWidth}px`;
  };

  const updateFloatingHeader = () => {
    if (!floatingHeader) {
      return;
    }
    const scroller = getScroller();
    if (!scroller || !active || scroller.offsetParent === null) {
      floatingHeader.wrapper.classList.add("hidden");
      return;
    }
    const rect = scroller.getBoundingClientRect();
    const headerHeight = floatingHeader.wrapper.offsetHeight || 0;
    // Show once the real header has scrolled past the top, until the table
    // itself is nearly gone.
    const shouldShow = rect.top < 0 && rect.bottom > headerHeight + 40;
    floatingHeader.wrapper.classList.toggle("hidden", !shouldShow);
    if (!shouldShow) {
      return;
    }
    floatingHeader.wrapper.style.left = `${rect.left}px`;
    floatingHeader.wrapper.style.width = `${scroller.clientWidth}px`;
    floatingHeader.wrapper.scrollLeft = scroller.scrollLeft;
  };

  // Catches the scroller disappearing without a scroll event (tab switch,
  // section collapse) so the clone never lingers over other content.
  const visibilityObserver =
    typeof IntersectionObserver === "function"
      ? new IntersectionObserver(() => updateFloatingHeader())
      : null;

  const buildFloatingHeader = () => {
    destroyFloatingHeader();
    const scroller = getScroller();
    const table = scroller?.querySelector("table");
    const thead = table?.querySelector("thead");
    if (!scroller || !table || !thead) {
      return;
    }
    visibilityObserver?.disconnect();
    visibilityObserver?.observe(scroller);
    const wrapper = document.createElement("div");
    wrapper.className =
      "fixed top-0 z-40 hidden overflow-hidden border-b border-slate-300 bg-white shadow-md";
    const cloneTable = document.createElement("table");
    cloneTable.className = table.className;
    cloneTable.appendChild(thead.cloneNode(true));
    wrapper.appendChild(cloneTable);
    document.body.appendChild(wrapper);
    floatingHeader = { wrapper, table: cloneTable };
    syncFloatingHeaderWidths();
    scroller.addEventListener("scroll", updateFloatingHeader, { passive: true });
  };

  window.addEventListener("scroll", updateFloatingHeader, { passive: true });
  window.addEventListener("resize", () => {
    // Container width changed: re-fit the day columns to the new strip so the
    // seams stay on cell boundaries, then re-measure the header clone.
    if (active) {
      fitAndSnapDayColumns(container);
    }
    syncFloatingHeaderWidths();
    updateFloatingHeader();
  });

  const render = async () => {
    if (!container) {
      return;
    }
    const token = ++renderToken;
    if (!Array.isArray(creatives) || creatives.length === 0) {
      container.innerHTML =
        '<div class="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center"><p class="text-sm text-slate-500">No creatives match the current filters.</p></div>';
      return;
    }
    container.innerHTML =
      '<div class="flex animate-pulse items-center justify-center rounded-2xl border border-slate-200 bg-white py-16 text-sm text-slate-400">Loading time cards table&hellip;</div>';

    let dayData = null;
    try {
      dayData = await fetchBulkDailyHours(getPeriodValue?.() ?? "");
    } catch {
      dayData = null; // Render totals-only with a retry notice.
    }
    if (token !== renderToken) {
      return; // A newer render (filter/period change) superseded this one.
    }
    hoverDayData = dayData;
    projectsByDateCache.clear();
    container.innerHTML = buildTableHtml(creatives, dayData, expandedIds);

    container.querySelectorAll("[data-nj-toggle]").forEach((pill) => {
      applyNewJoinerPillState(pill, pill.dataset.included === "true");
      const row = pill.closest("tr[data-creative-row]");
      bindNewJoinerToggle(pill, Number.parseInt(row?.dataset.creativeRow ?? "", 10));
    });

    // Layout must settle before the boundary math and width copies measure.
    requestAnimationFrame(() => {
      fitAndSnapDayColumns(container);
      buildFloatingHeader();
      updateFloatingHeader();
    });
  };

  if (container) {
    container.addEventListener("pointerover", (event) => {
      const cell = event.target.closest?.("td[data-day-cell]");
      if (!cell || !container.contains(cell)) {
        return;
      }
      const id = cell.closest("tr[data-creative-row]")?.dataset.creativeRow;
      const detail = id ? hoverDayData?.[id] : null;
      const date = cell.dataset.dayCell;
      const day = detail?.days?.find?.((d) => d.date === date);
      if (!day) {
        return;
      }
      let projectsByDate = projectsByDateCache.get(id);
      if (!projectsByDate) {
        projectsByDate = buildProjectsByDate(detail);
        projectsByDateCache.set(id, projectsByDate);
      }
      showTooltip(
        cell,
        buildDayTooltipHtml(day, new Date(`${date}T00:00:00`), projectsByDate.get(date))
      );
    });

    container.addEventListener("pointerout", (event) => {
      const cell = event.target.closest?.("td[data-day-cell]");
      if (cell && !(event.relatedTarget && cell.contains(event.relatedTarget))) {
        hideTooltip();
      }
    });

    container.addEventListener("click", (event) => {
      if (event.target.closest("[data-table-retry]")) {
        render();
        return;
      }
      const row = event.target.closest("tr[data-creative-row]");
      if (!row || row.dataset.hasProjects !== "true") {
        return;
      }
      const id = row.dataset.creativeRow;
      const nextExpanded = row.dataset.expanded !== "true";
      row.dataset.expanded = nextExpanded ? "true" : "false";
      if (nextExpanded) {
        expandedIds.add(id);
      } else {
        expandedIds.delete(id);
      }
      row.querySelector("[data-row-chevron]")?.classList.toggle("rotate-180", nextExpanded);
      container
        .querySelectorAll(`tr[data-project-row-for="${id}"]`)
        .forEach((tr) => tr.classList.toggle("hidden", !nextExpanded));
      // Sub-row content can widen columns; keep the floating header clone in
      // register with the new layout.
      requestAnimationFrame(() => {
        syncFloatingHeaderWidths();
        updateFloatingHeader();
      });
    });
  }

  return {
    // Called by the renderCreatives wrapper on every re-render (filters,
    // period changes, NJ flips) so the table always mirrors the grid's list.
    setCreatives(list) {
      creatives = Array.isArray(list) ? list : [];
      if (active) {
        render();
      }
    },
    setActive(next) {
      const wasActive = active;
      active = Boolean(next);
      if (active && !wasActive) {
        render();
      } else if (!active) {
        destroyFloatingHeader();
      }
    },
  };
}
