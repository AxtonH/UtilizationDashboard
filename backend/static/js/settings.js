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
            internalExternalImbalanceToggle.checked = settings.internal_external_imbalance_enabled || false;
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
    function openSettingsModal() {
      if (settingsModal) {
        settingsModal.classList.remove('hidden');
        settingsModal.classList.add('flex');
        // Prevent body scroll when modal is open
        document.body.style.overflow = 'hidden';
        // Load email settings when modal opens
        loadEmailSettings();
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
