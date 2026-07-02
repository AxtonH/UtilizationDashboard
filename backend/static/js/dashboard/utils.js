// Leaf utilities for the creatives dashboard: pure formatters, calendar-date
// helpers, and the pool label registry. Extracted verbatim from main.js; no
// DOM access here.

export function formatHours(value) {
  const totalMinutes = Math.round((Number(value) || 0) * 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (minutes === 0) {
    return `${hours}h`;
  }
  return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
}

/** Whole hours only (no minutes); used for BU External Hours Used where values are hour units. */
export function formatHoursWhole(value) {
  const h = Math.round(Number(value) || 0);
  return `${h}h`;
}

export function formatAed(value) {
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

export const parseDateValue = (value) => {
  if (value instanceof Date) {
    return value;
  }
  if (typeof value === "string") {
    // Calendar date only (matches Odoo/backend date logic). Avoid parsing full ISO datetimes
    // with timezones first — that can shift the instant into the wrong month in UTC.
    const datePart = value.trim().split("T")[0].split(" ")[0];
    const [yearStr, monthStr, dayStr] = datePart.split("-");
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
      const y = fallback.getUTCFullYear();
      const m = fallback.getUTCMonth() + 1;
      const d = fallback.getUTCDate();
      return new Date(Date.UTC(y, m - 1, d));
    }
  }
  return null;
};

export const parseMonthBounds = (monthValue) => {
  if (typeof monthValue !== "string") {
    return null;
  }
  if (monthValue.includes("-Q")) {
    const [ys, qPart] = monthValue.split("-Q");
    const year = Number(ys);
    const q = Number(qPart);
    if (!Number.isInteger(year) || !Number.isInteger(q) || q < 1 || q > 4) {
      return null;
    }
    const startMonth = [0, 3, 6, 9][q - 1];
    const endMonthExclusive = [3, 6, 9, 12][q - 1];
    const start = new Date(Date.UTC(year, startMonth, 1));
    const endYear = endMonthExclusive === 12 ? year + 1 : year;
    const endMonth = endMonthExclusive === 12 ? 0 : endMonthExclusive;
    const end = new Date(Date.UTC(endYear, endMonth, 1));
    return { start, end };
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

export const isWithinMonth = (dateValue, start, end) => {
  if (!(dateValue instanceof Date) || Number.isNaN(dateValue.getTime()) || !start || !end) {
    return false;
  }
  return dateValue >= start && dateValue < end;
};

// ---------------------------------------------------------------------------
// Pool label registry (module-level state; shared by all importers)
// ---------------------------------------------------------------------------

const poolLabelMap = new Map();

export const registerPoolLabel = (slug, label) => {
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

export const registerPoolLabelsFromData = (pools) => {
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

export const getPoolLabel = (slug) => {
  if (!slug) {
    return "";
  }
  const key = String(slug).toLowerCase();
  if (!poolLabelMap.has(key)) {
    registerPoolLabel(slug, "");
  }
  return poolLabelMap.get(key) ?? String(slug);
};

// ---------------------------------------------------------------------------
// Pool definitions and client-pool normalization
// ---------------------------------------------------------------------------

export const POOL_DEFINITIONS = [
  { slug: "ksa", tag: "ksa" },
  { slug: "uae", tag: "uae" },
];
export const CLIENT_POOL_DEFINITIONS = [
  { slug: "ksa", label: "KSA", tag: "ksa" },
  { slug: "uae", label: "UAE", tag: "uae", aliases: ["adeo"] },
];
export const CLIENT_POOL_MATCHERS = CLIENT_POOL_DEFINITIONS.map((definition) => {
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
export const CLIENT_POOL_ALIAS_LOOKUP = (() => {
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
export const normalizeClientPoolSlug = (value) => {
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
