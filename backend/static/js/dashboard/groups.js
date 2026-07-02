// Creative search + group management (search box, individual/group filter
// menu, group CRUD modal). Extracted verbatim from main.js; the four deps are
// the pieces of the dashboard it renders through.
export function initCreativeGroups({
  creativeState,
  computeFilteredAggregates,
  computeFilteredPoolStats,
  renderCreatives,
}) {
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
    const filteredAggregates = computeFilteredAggregates(filteredCreatives, null);
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
}
