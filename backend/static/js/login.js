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

    // Check authentication status on page load
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
          } else {
            showLoginModal();
            hideDashboard();
          }
        })
        .catch(error => {
          console.error('Error checking auth status:', error);
          // Show modal on error to allow login attempt
          showLoginModal();
          hideDashboard();
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
            // Success - hide modal and show dashboard
            hideLoginModal();
            showDashboard();
            setLoadingState(false);
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
      
      // Immediately show login modal and hide dashboard for instant feedback
      showLoginModal();
      hideDashboard();
      
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
  }
})();
