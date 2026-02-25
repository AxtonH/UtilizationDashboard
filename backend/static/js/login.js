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

    // Hide logout button until we confirm user is authenticated (Sales access)
    if (logoutBtn) logoutBtn.style.display = 'none';

    // Check authentication status on page load (creative dashboard always visible)
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
          } else {
            // Creative dashboard is public - always show it, don't block with login modal
            showDashboard();
            hideLoginModal();
            hideError();
            updateLogoutButtonVisibility(false);
          }
        })
        .catch(error => {
          console.error('Error checking auth status:', error);
          showDashboard();
          hideLoginModal();
          updateLogoutButtonVisibility(false);
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
      
      // Hide logout button immediately; creative dashboard stays visible
      updateLogoutButtonVisibility(false);
      
      // Clear form fields
      if (emailInput) emailInput.value = '';
      if (passwordInput) passwordInput.value = '';
      hideError();
      
      // Clear session on server (fire and forget)
      fetch('/api/logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include'  // Include cookies to revoke refresh token
      })
        .then(response => response.json())
        .then(data => {
          console.log('Logout successful');
        })
        .catch(error => {
          console.error('Logout error:', error);
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

    function updateLogoutButtonVisibility(show) {
      if (logoutBtn) {
        logoutBtn.style.display = show ? '' : 'none';
      }
    }

    // Expose for sales dashboard: show login modal when user tries to access Sales without auth
    window.showLoginModalForSales = function() {
      showLoginModal();
      hideError();
    };
  }
})();



