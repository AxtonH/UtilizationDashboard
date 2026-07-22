/**
 * Login functionality for dashboard access control.
 * Handles Odoo authentication and login/logout flow.
 */
(function() {
  'use strict';

  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {
    const loginModal = document.querySelector('[data-login-modal]');
    const loginForm = document.querySelector('[data-login-form]');
    const loginSubmitBtn = document.querySelector('[data-login-submit]');
    const emailInput = document.querySelector('[data-login-email-input]');
    const passwordInput = document.querySelector('[data-login-password-input]');
    const rememberMeCheckbox = document.querySelector('[data-remember-me-checkbox]');
    const errorElement = document.querySelector('[data-login-error]');
    const submitText = document.querySelector('[data-login-submit-text]');
    const submitSpinner = document.querySelector('[data-login-submit-spinner]');
    const logoutBtn = document.querySelector('[data-logout-btn]');
    const dashboardContent = document.querySelector('[data-dashboard-content]');
    const totpSection = document.querySelector('[data-totp-section]');
    const totpCodeInput = document.querySelector('[data-totp-code-input]');
    const totpBackBtn = document.querySelector('[data-totp-back]');

    // True while the modal is showing the 2FA code step (the footer button
    // then verifies the code instead of submitting email/password).
    let inTotpStep = false;

    if (!loginModal || !loginForm || !loginSubmitBtn) {
      console.warn('Login elements not found');
      return;
    }

    // The logout button's initial visibility is server-rendered from the
    // session, so don't blind-hide it here (that made it pop in seconds
    // later when the auth check resolved). checkAuthStatus() below corrects
    // the state if the session and server disagree.

    // Require Odoo login for everyone; dashboard stays visible behind the modal
    checkAuthStatus();

    // Handle form submission
    loginForm.addEventListener('submit', handleSubmit);
    loginSubmitBtn.addEventListener('click', handleSubmit);

    // Handle logout button
    if (logoutBtn) {
      logoutBtn.addEventListener('click', handleLogout);
    }

    // Handle Enter key in password field
    if (passwordInput) {
      passwordInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleSubmit(e);
        }
      });
    }

    // Two-factor step controls
    if (totpCodeInput) {
      totpCodeInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleTotpVerify();
        }
      });
    }
    if (totpBackBtn) {
      totpBackBtn.addEventListener('click', function(e) {
        e.preventDefault();
        exitTotpStep();
        hideError();
      });
    }

    function checkAuthStatus() {
      fetch('/api/check-dashboard-auth')
        .then(response => response.json())
        .then(data => {
          if (data.authenticated) {
            hideLoginModal();
            showDashboard();
            hideError();
            updateLogoutButtonVisibility(true);
            window.dispatchEvent(new CustomEvent('dashboardAuthResolved', { detail: data }));
          } else {
            showDashboardBehindLoginOverlay();
            showLoginModal();
            hideError();
            updateLogoutButtonVisibility(false);
            window.dispatchEvent(new CustomEvent('dashboardAuthResolved', { detail: data }));
          }
        })
        .catch(error => {
          console.error('Error checking auth status:', error);
          showDashboardBehindLoginOverlay();
          showLoginModal();
          updateLogoutButtonVisibility(false);
          window.dispatchEvent(new CustomEvent('dashboardAuthResolved', {
            detail: { authenticated: false, sales_access: false, market_filter_visible: false },
          }));
        });
    }

    function handleSubmit(e) {
      e.preventDefault();
      e.stopPropagation();

      if (inTotpStep) {
        handleTotpVerify();
        return;
      }

      // Get form values
      const email = emailInput ? emailInput.value.trim() : '';
      const password = passwordInput ? passwordInput.value.trim() : '';
      const rememberMe = rememberMeCheckbox ? rememberMeCheckbox.checked : false;
      
      // Basic validation
      if (!email) {
        showError('Please enter your email');
        if (emailInput) emailInput.focus();
        return;
      }
      
      if (!password) {
        showError('Please enter your password');
        if (passwordInput) passwordInput.focus();
        return;
      }

      // Show loading state
      setLoadingState(true);
      hideError();

      // Submit to backend
      fetch('/api/verify-dashboard-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          email: email, 
          password: password,
          remember_me: rememberMe 
        }),
        credentials: 'include'  // Include cookies in request
      })
        .then(async response => {
          let data;
          try {
            data = await response.json();
          } catch (e) {
            data = { success: false, message: 'Invalid response from server' };
          }
          return {
            ok: response.ok,
            status: response.status,
            data: data
          };
        })
        .then(result => {
          if (result.ok && result.data.success) {
            handleAuthSuccess(result.data);
          } else if (result.data.requires_totp) {
            // Password accepted; Odoo wants the authenticator code.
            setLoadingState(false);
            enterTotpStep();
          } else {
            // Show error message
            const errorMsg = result.data.message || 'Login failed. Please try again.';
            showError(errorMsg);
            setLoadingState(false);
          }
        })
        .catch(error => {
          console.error('Login error:', error);
          showError('An error occurred. Please check your connection and try again.');
          setLoadingState(false);
        });
    }

    function handleAuthSuccess(data) {
      exitTotpStep();
      hideLoginModal();
      showDashboard();
      setLoadingState(false);
      updateLogoutButtonVisibility(true);
      window.dispatchEvent(new CustomEvent('dashboardAuthResolved', {
        detail: {
          authenticated: true,
          sales_access: !!data.sales_access,
          market_filter_visible: !!data.market_filter_visible,
        },
      }));
      // Notify sales dashboard that user logged in (so it can load data if Sales tab is active)
      window.dispatchEvent(new CustomEvent('salesLoginSuccess'));
    }

    function handleTotpVerify() {
      const code = totpCodeInput ? totpCodeInput.value.trim() : '';
      if (!code) {
        showError('Please enter the verification code');
        if (totpCodeInput) totpCodeInput.focus();
        return;
      }

      setLoadingState(true);
      hideError();

      fetch('/api/verify-dashboard-totp', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ code: code }),
        credentials: 'include'
      })
        .then(async response => {
          let data;
          try {
            data = await response.json();
          } catch (e) {
            data = { success: false, message: 'Invalid response from server' };
          }
          return { ok: response.ok, data: data };
        })
        .then(result => {
          if (result.ok && result.data.success) {
            handleAuthSuccess(result.data);
          } else {
            setLoadingState(false);
            showError(result.data.message || 'Verification failed. Please try again.');
            if (result.data.restart) {
              // Pre-auth session expired: back to the password step.
              exitTotpStep();
            } else if (totpCodeInput) {
              totpCodeInput.value = '';
              totpCodeInput.focus();
            }
          }
        })
        .catch(error => {
          console.error('TOTP verify error:', error);
          showError('An error occurred. Please check your connection and try again.');
          setLoadingState(false);
        });
    }

    function enterTotpStep() {
      inTotpStep = true;
      if (loginForm) loginForm.classList.add('hidden');
      if (totpSection) totpSection.classList.remove('hidden');
      if (submitText) submitText.textContent = 'Verify';
      if (totpCodeInput) {
        totpCodeInput.value = '';
        setTimeout(() => totpCodeInput.focus(), 100);
      }
    }

    function exitTotpStep() {
      inTotpStep = false;
      if (loginForm) loginForm.classList.remove('hidden');
      if (totpSection) totpSection.classList.add('hidden');
      if (submitText) submitText.textContent = 'Login';
      if (totpCodeInput) totpCodeInput.value = '';
    }

    function handleLogout(e) {
      e.preventDefault();
      e.stopPropagation();
      
      updateLogoutButtonVisibility(false);
      hideDashboard();

      // Clear form fields and reset to the password step
      if (emailInput) emailInput.value = '';
      if (passwordInput) passwordInput.value = '';
      exitTotpStep();
      hideError();
      
      fetch('/api/logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include'  // Include cookies to revoke refresh token
      })
        .then(async (response) => {
          let data = {};
          try {
            data = await response.json();
          } catch (e) {
            /* ignore */
          }
          if (!response.ok) {
            throw new Error(data.message || data.error || 'Logout failed');
          }
          return data;
        })
        .then(data => {
          console.log('Logout successful');
          hideDashboard();
          showLoginModal();
          window.dispatchEvent(new CustomEvent('dashboardLoggedOut'));
          window.dispatchEvent(new CustomEvent('dashboardAuthResolved', {
            detail: { authenticated: false, sales_access: false, market_filter_visible: false },
          }));
        })
        .catch(error => {
          console.error('Logout error:', error);
          showDashboardBehindLoginOverlay();
          showLoginModal();
          showError('Could not log out. Please try again.');
          window.dispatchEvent(new CustomEvent('dashboardAuthResolved', {
            detail: { authenticated: false, sales_access: false, market_filter_visible: false },
          }));
        });
    }

    function setLoadingState(loading) {
      if (loginSubmitBtn) {
        loginSubmitBtn.disabled = loading;
      }
      if (submitText) {
        submitText.style.display = loading ? 'none' : 'inline';
      }
      if (submitSpinner) {
        submitSpinner.classList.toggle('hidden', !loading);
        submitSpinner.style.display = loading ? 'inline-block' : 'none';
      }
    }

    function showError(message) {
      if (errorElement) {
        errorElement.textContent = message;
        errorElement.classList.remove('hidden');
      }
    }

    function hideError() {
      if (errorElement) {
        errorElement.textContent = '';
        errorElement.classList.add('hidden');
      }
    }

    function showLoginModal() {
      if (loginModal) {
        loginModal.style.display = 'flex';
        loginModal.classList.remove('hidden');
        loginModal.classList.add('flex');
        // Focus on email input first
        if (emailInput) {
          setTimeout(() => emailInput.focus(), 100);
        }
      }
    }

    function hideLoginModal() {
      if (loginModal) {
        loginModal.style.display = 'none';
        loginModal.classList.add('hidden');
        loginModal.classList.remove('flex');
      }
    }

    function showDashboard() {
      if (dashboardContent) {
        dashboardContent.style.display = '';
        dashboardContent.style.pointerEvents = '';
        dashboardContent.style.opacity = '';
      }
    }

    function hideDashboard() {
      if (dashboardContent) {
        dashboardContent.style.pointerEvents = 'none';
        dashboardContent.style.opacity = '0.3';
      }
    }

    /** Dashboard visible behind the login modal but non-interactive (one step; avoids show+hide confusion). */
    function showDashboardBehindLoginOverlay() {
      if (dashboardContent) {
        dashboardContent.style.display = '';
        dashboardContent.style.pointerEvents = 'none';
        dashboardContent.style.opacity = '0.3';
      }
    }

    function updateLogoutButtonVisibility(show) {
      if (logoutBtn) {
        logoutBtn.style.display = show ? '' : 'none';
      }
    }

    // Expose for sales dashboard: prompt for Odoo login when Sales is opened without a session
    window.showLoginModalForSales = function() {
      showDashboardBehindLoginOverlay();
      showLoginModal();
      hideError();
    };
  }
})();



