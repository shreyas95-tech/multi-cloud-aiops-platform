(function () {
  'use strict';

  const API_BASE = 'http://localhost:8000/api';

  // ─── Token Management ───────────────────────────────────────────────────────

  /**
   * Store the access token in localStorage.
   * @param {string} token
   */
  function setToken(token) {
    localStorage.setItem('access_token', token);
  }

  /**
   * Retrieve the access token from localStorage.
   * @returns {string|null}
   */
  function getToken() {
    return localStorage.getItem('access_token');
  }

  /**
   * Clear all auth-related data from localStorage.
   */
  function clearToken() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_role');
  }

  /**
   * Store the user role in localStorage.
   * @param {string} role
   */
  function setUserRole(role) {
    localStorage.setItem('user_role', role);
  }

  /**
   * Retrieve the user role from localStorage.
   * @returns {string|null}
   */
  function getUserRole() {
    return localStorage.getItem('user_role');
  }

  // ─── Auth State ─────────────────────────────────────────────────────────────

  /**
   * Check if the user is authenticated (token exists and not expired).
   * @returns {boolean}
   */
  function isAuthenticated() {
    const token = getToken();
    if (!token) return false;

    // Attempt to decode JWT and check expiry client-side
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      if (payload.exp && payload.exp * 1000 < Date.now()) {
        clearToken();
        return false;
      }
      return true;
    } catch (e) {
      // If token cannot be decoded, treat as invalid
      clearToken();
      return false;
    }
  }

  // ─── API Functions ──────────────────────────────────────────────────────────

  /**
   * Login with username and password.
   * @param {string} username
   * @param {string} password
   * @returns {Promise<{access_token: string, role: string, requires_password_change: boolean}>}
   */
  async function login(username, password) {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || (data.error && data.error.message) || 'Login failed');
    }

    const result = data.data || data;
    setToken(result.access_token);
    setUserRole(result.role);
    return result; // { access_token, role, requires_password_change }
  }

  /**
   * Logout the current user. Calls the logout endpoint and clears local state.
   */
  async function logout() {
    const token = getToken();
    if (token) {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token },
      }).catch(function () {}); // Ignore errors on logout
    }
    clearToken();
    window.location.href = 'login.html';
  }

  /**
   * Change password (for first-time users or voluntary change).
   * @param {string} currentPassword
   * @param {string} newPassword
   * @returns {Promise<{access_token: string, role: string}>}
   */
  async function changePassword(currentPassword, newPassword) {
    const token = getToken();
    const response = await fetch(`${API_BASE}/auth/change-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
      },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || (data.error && data.error.message) || 'Password change failed');
    }

    const result = data.data || data;
    setToken(result.access_token);
    setUserRole(result.role);
    return result;
  }

  // ─── Auth Guards ────────────────────────────────────────────────────────────

  /**
   * Redirect to login page if the user is not authenticated.
   * Call this at the top of protected pages.
   * @returns {boolean} true if authenticated, false if redirecting
   */
  function requireAuth() {
    if (!isAuthenticated()) {
      window.location.href = 'login.html';
      return false;
    }
    return true;
  }

  /**
   * Get the Authorization header object for authenticated API calls.
   * @returns {{Authorization: string}}
   */
  function getAuthHeaders() {
    return { 'Authorization': 'Bearer ' + getToken() };
  }

  // ─── Login Page Form Handling ───────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    var loginForm = document.getElementById('login-form');
    var passwordChangeForm = document.getElementById('password-change-form');

    // Only wire up login form if we're on the login page
    if (!loginForm) return;

    var loginError = document.getElementById('login-error');
    var loginBtn = document.getElementById('login-btn');

    loginForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      var username = document.getElementById('login-username').value.trim();
      var password = document.getElementById('login-password').value;

      if (!username || !password) {
        if (loginError) {
          loginError.textContent = 'Please enter both username and password.';
          loginError.classList.remove('hidden');
        }
        return;
      }

      if (loginBtn) loginBtn.disabled = true;
      if (loginError) loginError.classList.add('hidden');

      try {
        var result = await login(username, password);

        if (result.requires_password_change) {
          // Show the password change card, hide login card
          var loginCard = document.getElementById('login-card');
          var passwordChangeCard = document.getElementById('password-change-card');
          if (loginCard) loginCard.classList.add('hidden');
          if (passwordChangeCard) passwordChangeCard.classList.remove('hidden');
        } else {
          // Redirect to dashboard
          window.location.href = 'dashboard.html';
        }
      } catch (err) {
        if (loginError) {
          loginError.textContent = err.message;
          loginError.classList.remove('hidden');
        }
      } finally {
        if (loginBtn) loginBtn.disabled = false;
      }
    });

    // Password change form handling
    if (passwordChangeForm) {
      passwordChangeForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        var currentPassword = document.getElementById('current-password').value;
        var newPassword = document.getElementById('new-password').value;
        var confirmPassword = document.getElementById('confirm-password').value;
        var changeError = document.getElementById('change-error');
        var changeBtn = document.getElementById('change-btn');

        if (changeError) changeError.classList.add('hidden');

        if (newPassword !== confirmPassword) {
          if (changeError) {
            changeError.textContent = 'New passwords do not match.';
            changeError.classList.remove('hidden');
          }
          return;
        }

        if (changeBtn) changeBtn.disabled = true;

        try {
          await changePassword(currentPassword, newPassword);
          // Password changed successfully, redirect to dashboard
          window.location.href = 'dashboard.html';
        } catch (err) {
          if (changeError) {
            changeError.textContent = err.message;
            changeError.classList.remove('hidden');
          }
        } finally {
          if (changeBtn) changeBtn.disabled = false;
        }
      });
    }

    // Forgot password link — show reset card
    var forgotLink = document.getElementById('forgot-password-link');
    if (forgotLink) {
      forgotLink.addEventListener('click', function (e) {
        e.preventDefault();
        var loginCard = document.getElementById('login-card');
        var resetCard = document.getElementById('reset-card');
        if (loginCard) loginCard.classList.add('hidden');
        if (resetCard) resetCard.classList.remove('hidden');
      });
    }

    // Back to login link
    var backToLoginLink = document.getElementById('back-to-login-link');
    if (backToLoginLink) {
      backToLoginLink.addEventListener('click', function (e) {
        e.preventDefault();
        var loginCard = document.getElementById('login-card');
        var resetCard = document.getElementById('reset-card');
        if (resetCard) resetCard.classList.add('hidden');
        if (loginCard) loginCard.classList.remove('hidden');
      });
    }
  });

  // ─── Expose Public API ──────────────────────────────────────────────────────

  window.Auth = {
    login: login,
    logout: logout,
    changePassword: changePassword,
    getToken: getToken,
    setToken: setToken,
    clearToken: clearToken,
    getUserRole: getUserRole,
    setUserRole: setUserRole,
    isAuthenticated: isAuthenticated,
    requireAuth: requireAuth,
    getAuthHeaders: getAuthHeaders,
  };
})();
