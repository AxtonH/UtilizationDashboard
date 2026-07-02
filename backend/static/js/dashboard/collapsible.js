// Collapsible dashboard sections. Extracted verbatim from main.js; collapse
// state persists on creativeState.sectionCollapsed, and onSectionToggled lets
// the caller react to a toggle (e.g. resizing a chart).

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

export function createCollapsibleSections({ creativeState, onSectionToggled }) {
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
        onSectionToggled?.(key);
      });
      applySectionCollapsedState(key);
    });
  };

  return { applySectionCollapsedState, initializeCollapsibleSections };
}
