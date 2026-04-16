/**
 * Settings modal functionality for dashboard.
 * Handles opening/closing the settings modal and email configuration.
 */
(function() {
  'use strict';

  document.addEventListener('DOMContentLoaded', function() {
    const settingsBtn = document.querySelector('[data-settings-btn]');
    const settingsModal = document.querySelector('[data-settings-modal]');
    const settingsModalClose = document.querySelector('[data-settings-modal-close]');
    const emailForm = document.querySelector('[data-email-settings-form]');
    const emailRecipients = document.querySelector('[data-email-recipients]');
    const emailCc = document.querySelector('[data-email-cc]');
    const emailSendDate = document.querySelector('[data-email-send-date]');
    const emailSendTime = document.querySelector('[data-email-send-time]');
    const emailSaveBtn = document.querySelector('[data-email-save-btn]');
    const emailTestBtn = document.querySelector('[data-email-test-btn]');
    const emailError = document.querySelector('[data-email-error]');
    const emailErrorMessage = document.querySelector('[data-email-error-message]');
    const emailSuccess = document.querySelector('[data-email-success]');
    const emailSuccessMessage = document.querySelector('[data-email-success-message]');
    const internalExternalImbalanceToggle = document.querySelector('[data-internal-external-imbalance-toggle]');
    const overbookingToggle = document.querySelector('[data-overbooking-toggle]');
    const underbookingToggle = document.querySelector('[data-underbooking-toggle]');
    const subscriptionHoursAlertToggle = document.querySelector('[data-subscription-hours-alert-toggle]');
    const testReportMonth = document.querySelector('[data-test-report-month]');

    if (!settingsBtn || !settingsModal) {
      return;
    }

    /**
     * Show error message
     */
    function showError(message) {
      if (emailError && emailErrorMessage) {
        emailErrorMessage.textContent = message;
        emailError.classList.remove('hidden');
        emailSuccess?.classList.add('hidden');
      }
    }

    /**
     * Show success message
     */
    function showSuccess(message) {
      if (emailSuccess && emailSuccessMessage) {
        emailSuccessMessage.textContent = message;
        emailSuccess.classList.remove('hidden');
        emailError?.classList.add('hidden');
      }
    }

    /**
     * Hide all messages
     */
    function hideMessages() {
      emailError?.classList.add('hidden');
      emailSuccess?.classList.add('hidden');
    }

    /**
     * Parse comma-separated email addresses
     */
    function parseEmails(emailString) {
      if (!emailString || !emailString.trim()) {
        return [];
      }
      return emailString
        .split(',')
        .map(email => email.trim())
        .filter(email => email.length > 0);
    }

    /**
     * Load email settings from server
     */
    async function loadEmailSettings() {
      try {
        const response = await fetch('/api/email-settings', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
        });

        const data = await response.json();

        if (data.success && data.settings) {
          const settings = data.settings;
          
          // Populate form fields
          if (emailRecipients) {
            emailRecipients.value = settings.recipients?.join(', ') || '';
          }
          if (emailCc) {
            emailCc.value = settings.cc_recipients?.join(', ') || '';
          }
          if (emailSendDate && settings.send_date) {
            emailSendDate.value = settings.send_date;
          }
          if (emailSendTime && settings.send_time) {
            // Convert HH:MM:SS to HH:MM if needed
            const time = settings.send_time.split(':').slice(0, 2).join(':');
            emailSendTime.value = time;
          }
          if (internalExternalImbalanceToggle !== null) {
            // Explicitly convert to boolean to handle string "true"/"false" or null/undefined
            const toggleValue = settings.internal_external_imbalance_enabled;
            internalExternalImbalanceToggle.checked = toggleValue === true || toggleValue === "true" || toggleValue === "t" || toggleValue === 1;
          }
          if (overbookingToggle !== null) {
            // Explicitly convert to boolean to handle string "true"/"false" or null/undefined
            const toggleValue = settings.overbooking_enabled;
            overbookingToggle.checked = toggleValue === true || toggleValue === "true" || toggleValue === "t" || toggleValue === 1;
          }
          if (underbookingToggle !== null) {
            // Explicitly convert to boolean to handle string "true"/"false" or null/undefined
            const toggleValue = settings.underbooking_enabled;
            underbookingToggle.checked = toggleValue === true || toggleValue === "true" || toggleValue === "t" || toggleValue === 1;
          }
          if (subscriptionHoursAlertToggle !== null) {
            // Explicitly convert to boolean to handle string "true"/"false" or null/undefined
            const toggleValue = settings.subscription_hours_alert_enabled;
            subscriptionHoursAlertToggle.checked = toggleValue === true || toggleValue === "true" || toggleValue === "t" || toggleValue === 1;
          }
        }
      } catch (error) {
        console.error('Error loading email settings:', error);
        // Don't show error on load failure, just use defaults
      }
    }

    /**
     * Save email settings
     */
    async function saveEmailSettings() {
      if (!emailForm || !emailRecipients) {
        return;
      }

      hideMessages();

      const recipients = parseEmails(emailRecipients.value);
      
      if (recipients.length === 0) {
        showError('At least one recipient is required');
        emailRecipients.focus();
        return;
      }

      const ccRecipients = parseEmails(emailCc?.value || '');
      const sendDate = emailSendDate?.value || null;
      const sendTime = emailSendTime?.value || null;
      const internalExternalImbalanceEnabled = internalExternalImbalanceToggle?.checked || false;
      const overbookingEnabled = overbookingToggle?.checked || false;
      const underbookingEnabled = underbookingToggle?.checked || false;
      const subscriptionHoursAlertEnabled = subscriptionHoursAlertToggle?.checked || false;

      if (emailSaveBtn) {
        emailSaveBtn.disabled = true;
        emailSaveBtn.textContent = 'Saving...';
      }

      try {
        const response = await fetch('/api/email-settings', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
          body: JSON.stringify({
            recipients,
            cc_recipients: ccRecipients,
            send_date: sendDate,
            send_time: sendTime,
            enabled: true,
            internal_external_imbalance_enabled: internalExternalImbalanceEnabled,
            overbooking_enabled: overbookingEnabled,
            underbooking_enabled: underbookingEnabled,
            subscription_hours_alert_enabled: subscriptionHoursAlertEnabled,
          }),
        });

        const data = await response.json();

        if (data.success) {
          showSuccess(data.message || 'Email settings saved successfully');
        } else {
          showError(data.error || 'Failed to save email settings');
        }
      } catch (error) {
        console.error('Error saving email settings:', error);
        showError('Failed to save email settings. Please try again.');
      } finally {
        if (emailSaveBtn) {
          emailSaveBtn.disabled = false;
          emailSaveBtn.textContent = 'Save Settings';
        }
      }
    }

    /**
     * Send alert report
     */
    async function sendAlertReport() {
      if (!emailRecipients) {
        return;
      }

      hideMessages();

      const recipients = parseEmails(emailRecipients.value);
      
      if (recipients.length === 0) {
        showError('At least one recipient is required');
        emailRecipients.focus();
        return;
      }

      const ccRecipients = parseEmails(emailCc?.value || '');
      const internalExternalImbalanceEnabled = internalExternalImbalanceToggle?.checked || false;
      const overbookingEnabled = overbookingToggle?.checked || false;
      const underbookingEnabled = underbookingToggle?.checked || false;
      const subscriptionHoursAlertEnabled = subscriptionHoursAlertToggle?.checked || false;
      const testMonth = testReportMonth?.value || null; // Format: YYYY-MM

      if (emailTestBtn) {
        emailTestBtn.disabled = true;
        emailTestBtn.textContent = 'Sending...';
      }

      try {
        const response = await fetch('/api/email-settings/test', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
            body: JSON.stringify({
              recipients,
              cc_recipients: ccRecipients,
              internal_external_imbalance_enabled: internalExternalImbalanceEnabled,
              overbooking_enabled: overbookingEnabled,
              underbooking_enabled: underbookingEnabled,
              subscription_hours_alert_enabled: subscriptionHoursAlertEnabled,
              test_month: testMonth,
            }),
        });

        const data = await response.json();

        if (data.success) {
          showSuccess(data.message || 'Alert report sent successfully');
        } else {
          showError(data.error || 'Failed to send alert report');
        }
      } catch (error) {
        console.error('Error sending alert report:', error);
        showError('Failed to send alert report. Please check your configuration.');
      } finally {
        if (emailTestBtn) {
          emailTestBtn.disabled = false;
          emailTestBtn.textContent = 'Send Report';
        }
      }
    }

    /**
     * Open the settings modal
     */
    const hourAdjustmentsRows = document.querySelector('[data-hour-adjustments-rows]');
    const hourAdjustmentsAdd = document.querySelector('[data-hour-adjustments-add]');
    const hourAdjustmentsSave = document.querySelector('[data-hour-adjustments-save]');
    const hourAdjustmentsFeedback = document.querySelector('[data-hour-adjustments-feedback]');
    const creativesGrid = document.querySelector('[data-creatives-grid]');

    function getCreativesForHourPicker() {
      if (!creativesGrid || !creativesGrid.dataset.creativesInitial) {
        return [];
      }
      try {
        const raw = creativesGrid.dataset.creativesInitial;
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch (e) {
        console.warn('Could not parse creatives list for hour adjustments', e);
        return [];
      }
    }

    function buildCreativeSelectOptions(selectedId) {
      const creatives = getCreativesForHourPicker();
      const opts = ['<option value="">Select creative…</option>'];
      creatives.forEach((c) => {
        const id = c && c.id;
        if (typeof id !== 'number') {
          return;
        }
        const name = (c.name && String(c.name).trim()) || `ID ${id}`;
        const sel = id === selectedId ? ' selected' : '';
        opts.push(`<option value="${id}"${sel}>${escapeHtml(String(name))}</option>`);
      });
      return opts.join('');
    }

    function escapeHtml(s) {
      return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function addHourAdjustmentRow(employeeId, monthlyHours) {
      if (!hourAdjustmentsRows) {
        return;
      }
      const eid = typeof employeeId === 'number' ? employeeId : null;
      const hrs = typeof monthlyHours === 'number' && !Number.isNaN(monthlyHours) ? monthlyHours : '';
      const wrap = document.createElement('div');
      wrap.setAttribute('data-hour-adjustment-row', '');
      wrap.className =
        'flex flex-wrap items-end gap-2 rounded-lg border border-slate-100 bg-slate-50/80 p-3';
      wrap.innerHTML = `
        <label class="flex min-w-[12rem] flex-1 flex-col gap-1">
          <span class="text-xs font-medium text-slate-600">Creative</span>
          <select data-hour-adjustment-employee class="rounded-lg border border-slate-200 bg-white px-2 py-2 text-sm text-slate-800 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-200">
            ${buildCreativeSelectOptions(eid)}
          </select>
        </label>
        <label class="flex w-32 flex-col gap-1">
          <span class="text-xs font-medium text-slate-600">Hours / month</span>
          <input type="number" min="0" max="400" step="0.5" value="${hrs}" data-hour-adjustment-value
            class="rounded-lg border border-slate-200 bg-white px-2 py-2 text-sm text-slate-800 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-200" />
        </label>
        <button type="button" data-hour-adjustment-remove class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:bg-slate-100" aria-label="Remove row">
          <span class="material-symbols-rounded text-base">close</span>
        </button>
      `;
      hourAdjustmentsRows.appendChild(wrap);
    }

    function clearHourAdjustmentRows() {
      if (hourAdjustmentsRows) {
        hourAdjustmentsRows.innerHTML = '';
      }
    }

    function showHourFeedback(message, isError) {
      if (!hourAdjustmentsFeedback) {
        return;
      }
      hourAdjustmentsFeedback.textContent = message || '';
      hourAdjustmentsFeedback.classList.remove('hidden', 'text-rose-600', 'text-emerald-700');
      if (!message) {
        hourAdjustmentsFeedback.classList.add('hidden');
        return;
      }
      hourAdjustmentsFeedback.classList.add(isError ? 'text-rose-600' : 'text-emerald-700');
    }

    async function loadHourAdjustments() {
      clearHourAdjustmentRows();
      showHourFeedback('', false);
      try {
        const response = await fetch('/api/creative-hour-adjustments', {
          method: 'GET',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        });
        const data = await response.json();
        const rows = data.adjustments && Array.isArray(data.adjustments) ? data.adjustments : [];
        if (rows.length === 0) {
          addHourAdjustmentRow(null, null);
        } else {
          rows.forEach((r) => {
            const id = typeof r.employee_id === 'number' ? r.employee_id : parseInt(r.employee_id, 10);
            const hrs = parseFloat(r.monthly_hours);
            if (!Number.isNaN(id)) {
              addHourAdjustmentRow(id, Number.isNaN(hrs) ? 0 : hrs);
            }
          });
        }
      } catch (e) {
        console.error(e);
        addHourAdjustmentRow(null, null);
        showHourFeedback('Could not load saved adjustments (check Supabase). You can still edit and save.', true);
      }
    }

    async function saveHourAdjustments() {
      if (!hourAdjustmentsRows) {
        return;
      }
      showHourFeedback('', false);
      const rowEls = hourAdjustmentsRows.querySelectorAll('[data-hour-adjustment-row]');
      const adjustments = [];
      for (let i = 0; i < rowEls.length; i += 1) {
        const row = rowEls[i];
        const sel = row.querySelector('[data-hour-adjustment-employee]');
        const inp = row.querySelector('[data-hour-adjustment-value]');
        if (!sel || !inp) {
          continue;
        }
        const v = sel.value;
        if (!v) {
          continue;
        }
        const employeeId = parseInt(v, 10);
        if (Number.isNaN(employeeId)) {
          continue;
        }
        const hrs = parseFloat(inp.value);
        if (Number.isNaN(hrs) || hrs < 0 || hrs > 400) {
          showHourFeedback('Each hours value must be between 0 and 400.', true);
          return;
        }
        adjustments.push({ employee_id: employeeId, monthly_hours: hrs });
      }

      if (hourAdjustmentsSave) {
        hourAdjustmentsSave.disabled = true;
        hourAdjustmentsSave.textContent = 'Saving…';
      }
      let reloadAfterSave = false;
      try {
        const response = await fetch('/api/creative-hour-adjustments', {
          method: 'PUT',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ adjustments }),
        });
        const data = await response.json();
        if (data.success) {
          reloadAfterSave = true;
          showHourFeedback('Saved. Refreshing dashboard…', false);
          if (hourAdjustmentsSave) {
            hourAdjustmentsSave.textContent = 'Refreshing…';
          }
          window.setTimeout(() => {
            window.location.reload();
          }, 500);
        } else {
          showHourFeedback(data.error || 'Save failed', true);
        }
      } catch (e) {
        console.error(e);
        showHourFeedback('Failed to save adjustments.', true);
      } finally {
        if (!reloadAfterSave && hourAdjustmentsSave) {
          hourAdjustmentsSave.disabled = false;
          hourAdjustmentsSave.textContent = 'Save hour adjustments';
        }
      }
    }

    document.querySelectorAll('[data-settings-section-toggle]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.getAttribute('data-settings-section-toggle');
        const panel = document.querySelector(`[data-settings-section-panel="${key}"]`);
        const icon = document.querySelector(`[data-settings-section-icon="${key}"]`);
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        if (panel) {
          panel.classList.toggle('hidden', expanded);
        }
        if (icon) {
          icon.textContent = expanded ? 'expand_more' : 'expand_less';
        }
      });
    });

    if (hourAdjustmentsRows) {
      hourAdjustmentsRows.addEventListener('click', (e) => {
        const t = e.target;
        const btn = t && t.closest && t.closest('[data-hour-adjustment-remove]');
        if (!btn) {
          return;
        }
        const row = btn.closest('[data-hour-adjustment-row]');
        if (row && row.parentNode) {
          row.parentNode.removeChild(row);
        }
        if (hourAdjustmentsRows.querySelectorAll('[data-hour-adjustment-row]').length === 0) {
          addHourAdjustmentRow(null, null);
        }
      });
    }

    if (hourAdjustmentsAdd) {
      hourAdjustmentsAdd.addEventListener('click', () => addHourAdjustmentRow(null, null));
    }

    if (hourAdjustmentsSave) {
      hourAdjustmentsSave.addEventListener('click', () => {
        saveHourAdjustments().catch(() => {});
      });
    }

    function openSettingsModal() {
      if (settingsModal) {
        settingsModal.classList.remove('hidden');
        settingsModal.classList.add('flex');
        // Prevent body scroll when modal is open
        document.body.style.overflow = 'hidden';
        // Load email settings when modal opens
        loadEmailSettings();
        loadHourAdjustments();
      }
    }

    /**
     * Close the settings modal
     */
    function closeSettingsModal() {
      if (settingsModal) {
        settingsModal.classList.add('hidden');
        settingsModal.classList.remove('flex');
        // Restore body scroll
        document.body.style.overflow = '';
        // Clear messages when closing
        hideMessages();
      }
    }

    /**
     * Handle click outside modal to close
     */
    function handleModalBackdropClick(e) {
      if (e.target === settingsModal) {
        closeSettingsModal();
      }
    }

    /**
     * Handle Escape key to close modal
     */
    function handleEscapeKey(e) {
      if (e.key === 'Escape' && settingsModal && !settingsModal.classList.contains('hidden')) {
        closeSettingsModal();
      }
    }

    // Event listeners
    if (settingsBtn) {
      settingsBtn.addEventListener('click', openSettingsModal);
    }

    // Handle all close buttons (header and footer)
    const allCloseButtons = document.querySelectorAll('[data-settings-modal-close]');
    allCloseButtons.forEach(btn => {
      btn.addEventListener('click', closeSettingsModal);
    });

    if (settingsModal) {
      settingsModal.addEventListener('click', handleModalBackdropClick);
    }

    if (emailForm) {
      emailForm.addEventListener('submit', function(e) {
        e.preventDefault();
        saveEmailSettings();
      });
    }

    if (emailTestBtn) {
      emailTestBtn.addEventListener('click', function(e) {
        e.preventDefault();
        sendAlertReport();
      });
    }

    document.addEventListener('keydown', handleEscapeKey);

    // Expose functions for potential external use
    window.settingsModal = {
      open: openSettingsModal,
      close: closeSettingsModal
    };
  });
})();
