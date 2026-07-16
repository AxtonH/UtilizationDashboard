// Shared custom tooltip for the whole dashboard: one floating panel element
// that replaces native title bubbles everywhere. Rich callers (the daily
// hours calendar) pass HTML to showTooltip directly; everything else keeps
// using plain `title` attributes, which initGlobalTooltips intercepts via
// event delegation (the attribute is moved to data-tooltip on first hover so
// the browser's own tooltip never appears).

export const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );

let tooltipEl = null;

const ensureTooltip = () => {
  if (!tooltipEl) {
    tooltipEl = document.createElement("div");
    tooltipEl.className =
      "pointer-events-none fixed z-50 hidden w-max max-w-64 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] shadow-lg";
    document.body.appendChild(tooltipEl);
    // Fixed positioning goes stale the moment anything scrolls or is clicked
    // (clicks can re-render the anchor out from under the panel).
    window.addEventListener("scroll", hideTooltip, { passive: true, capture: true });
    window.addEventListener("pointerdown", hideTooltip, { capture: true });
  }
  return tooltipEl;
};

export const hideTooltip = () => tooltipEl?.classList.add("hidden");

export const showTooltip = (anchor, html) => {
  const tip = ensureTooltip();
  tip.innerHTML = html;
  tip.classList.remove("hidden");
  const anchorRect = anchor.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  let left = anchorRect.left + anchorRect.width / 2 - tipRect.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
  let top = anchorRect.top - tipRect.height - 6;
  if (top < 8) {
    top = anchorRect.bottom + 6;
  }
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
};

// ---------------------------------------------------------------------------
// Global takeover of `title` attributes. Delegated, so elements rendered at
// any point (server HTML, cards, table view, modals) are covered without
// per-element wiring. Rich tooltips that call showTooltip themselves simply
// don't carry a title attribute, so the two paths never fight.
//
// Rich markup tooltips can also be authored declaratively: put
// data-tooltip-rich on the anchor and a hidden child with
// data-tooltip-content holding the HTML to display.
// ---------------------------------------------------------------------------

let activeAnchor = null;

export const initGlobalTooltips = () => {
  document.addEventListener("pointerover", (event) => {
    const el = event.target.closest?.("[title], [data-tooltip], [data-tooltip-rich]");
    if (!el) {
      return;
    }
    // Native title is consumed into data-tooltip; re-set titles (e.g. the NJ
    // pill after a toggle) take precedence again on the next hover.
    if (el.hasAttribute("title")) {
      const text = el.getAttribute("title");
      el.removeAttribute("title");
      if (text && text.trim()) {
        el.dataset.tooltip = text;
      }
    }
    if (el === activeAnchor) {
      return;
    }
    const richContent = el.hasAttribute("data-tooltip-rich")
      ? el.querySelector("[data-tooltip-content]")
      : null;
    if (richContent) {
      activeAnchor = el;
      showTooltip(el, richContent.innerHTML);
      return;
    }
    const text = el.dataset.tooltip;
    if (!text) {
      return;
    }
    activeAnchor = el;
    showTooltip(el, `<div class="text-slate-600">${escapeHtml(text)}</div>`);
  });

  document.addEventListener("pointerout", (event) => {
    if (!activeAnchor) {
      return;
    }
    const leavingAnchor = event.target === activeAnchor || activeAnchor.contains(event.target);
    const stillInside = event.relatedTarget && activeAnchor.contains(event.relatedTarget);
    if (leavingAnchor && !stillInside) {
      activeAnchor = null;
      hideTooltip();
    }
  });
};
