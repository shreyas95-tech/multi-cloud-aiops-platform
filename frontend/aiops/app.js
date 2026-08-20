(function () {
  'use strict';

  const API_BASE = 'http://localhost:8000/api';
  const TIMEOUT_MS = 30000;

  const queryForm = document.getElementById('query-form');
  const queryInput = document.getElementById('query-input');
  const submitBtn = document.getElementById('submit-btn');
  const validationMessage = document.getElementById('validation-message');
  const loadingIndicator = document.getElementById('loading-indicator');
  const resultDisplay = document.getElementById('result-display');
  const errorDisplay = document.getElementById('error-display');
  const errorText = document.getElementById('error-text');

  const resultIntent = document.getElementById('result-intent');
  const resultProvider = document.getElementById('result-provider');
  const resultAction = document.getElementById('result-action');
  const resultState = document.getElementById('result-state');

  /**
   * Validate that the query is non-empty and not whitespace-only.
   * @param {string} query
   * @returns {boolean}
   */
  function validateQuery(query) {
    if (!query || query.trim().length === 0) {
      showValidation('Please enter a non-empty query');
      return false;
    }
    clearValidation();
    return true;
  }

  function showValidation(message) {
    validationMessage.textContent = message;
    queryInput.setAttribute('aria-invalid', 'true');
  }

  function clearValidation() {
    validationMessage.textContent = '';
    queryInput.removeAttribute('aria-invalid');
  }

  function showLoading() {
    loadingIndicator.classList.remove('loading--hidden');
    submitBtn.disabled = true;
    submitBtn.setAttribute('aria-busy', 'true');
    hideResult();
    hideError();
  }

  function hideLoading() {
    loadingIndicator.classList.add('loading--hidden');
    submitBtn.disabled = false;
    submitBtn.removeAttribute('aria-busy');
  }

  function showResult(data) {
    resultIntent.textContent = data.intent || 'N/A';
    resultProvider.textContent = data.cloud || data.provider || 'N/A';
    resultAction.textContent = data.action || 'N/A';
    resultState.textContent = data.state || data.status || 'Completed';
    resultDisplay.classList.remove('result-card--hidden');
  }

  function hideResult() {
    resultDisplay.classList.add('result-card--hidden');
  }

  function showError(message) {
    errorText.textContent = message;
    errorDisplay.classList.remove('error-message--hidden');
  }

  function hideError() {
    errorDisplay.classList.add('error-message--hidden');
    errorText.textContent = '';
  }

  /**
   * Submit the query to the backend API.
   * @param {string} query
   */
  async function submitQuery(query) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

    showLoading();

    try {
      const response = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const json = await response.json();

      if (!response.ok) {
        const errorMsg =
          (json.error && json.error.message) ||
          json.detail ||
          `Request failed with status ${response.status}`;
        throw new Error(errorMsg);
      }

      // Handle envelope structure: {status, data, error}
      if (json.status === 'error') {
        throw new Error(
          (json.error && json.error.message) || 'An unknown error occurred'
        );
      }

      const resultData = json.data || json;
      hideLoading();
      showResult(resultData);
    } catch (err) {
      clearTimeout(timeoutId);
      hideLoading();

      if (err.name === 'AbortError') {
        showError('Request timed out. Please try again.');
      } else {
        showError(err.message || 'An unexpected error occurred.');
      }
      // Preserve user's query text in the input field on error
      // (do not clear the input)
    }
  }

  // Event: form submission
  queryForm.addEventListener('submit', function (e) {
    e.preventDefault();
    const query = queryInput.value;
    if (!validateQuery(query)) {
      return;
    }
    submitQuery(query.trim());
  });

  // Event: clear validation on input
  queryInput.addEventListener('input', function () {
    if (queryInput.value.trim().length > 0) {
      clearValidation();
    }
  });
})();
