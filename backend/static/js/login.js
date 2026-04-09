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

    if (!loginModal || !loginForm || !loginSubmitBtn) {
      console.warn('Login elements not found');
      return;
    }

    // Hide logout button until we confirm user is authenticated
    if (logoutBtn) logoutBtn.style.display = 'none';

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
            detail: { authenticated: false, sales_access: false },
          }));
        });
    }

    function handleSubmit(e) {
      e.preventDefault();
      e.stopPropagation();

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
            hideLoginModal();
            showDashboard();
            setLoadingState(false);
            updateLogoutButtonVisibility(true);
            window.dispatchEvent(new CustomEvent('dashboardAuthResolved', {
              detail: {
                authenticated: true,
                sales_access: !!result.data.sales_access,
              },
            }));
            // Notify sales dashboard that user logged in (so it can load data if Sales tab is active)
            window.dispatchEvent(new CustomEvent('salesLoginSuccess'));
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

    function handleLogout(e) {
      e.preventDefault();
      e.stopPropagation();
      
      updateLogoutButtonVisibility(false);
      hideDashboard();
      
      // Clear form fields
      if (emailInput) emailInput.value = '';
      if (passwordInput) passwordInput.value = '';
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
            detail: { authenticated: false, sales_access: false },
          }));
        })
        .catch(error => {
          console.error('Logout error:', error);
          showDashboardBehindLoginOverlay();
          showLoginModal();
          showError('Could not log out. Please try again.');
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



