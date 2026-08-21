(function () {
  'use strict';

  // ─── Auth Check ───────────────────────────────────────────────────────────
  if (!Auth.requireAuth()) return;

  const role = Auth.getUserRole();
  const API_BASE = '/api';

  // ─── DOM References ───────────────────────────────────────────────────────
  const sidebar = document.getElementById('sidebar');
  const hamburgerBtn = document.getElementById('hamburger-btn');
  const sidebarOverlay = document.getElementById('sidebar-overlay');
  const navItems = document.querySelectorAll('.nav-item');
  const contentSections = document.querySelectorAll('.content-section');
  const userDisplayName = document.getElementById('sidebar-username');
  const userDisplayRole = document.getElementById('sidebar-role');
  const logoutBtn = document.getElementById('logout-btn');

  // ─── User Info Display ────────────────────────────────────────────────────
  function displayUserInfo() {
    var token = Auth.getToken();
    if (!token) return;
    try {
      var payload = JSON.parse(atob(token.split('.')[1]));
      if (userDisplayName) userDisplayName.textContent = payload.sub || 'User';
      if (userDisplayRole) userDisplayRole.textContent = role || payload.role || 'Unknown';
    } catch (e) {
      if (userDisplayName) userDisplayName.textContent = 'User';
      if (userDisplayRole) userDisplayRole.textContent = role || 'Unknown';
    }
  }

  // ─── Role-Based Navigation ────────────────────────────────────────────────
  function setupNavigation() {
    navItems.forEach(function (item) {
      var requiredRole = item.getAttribute('data-role');
      if (requiredRole === 'all') return;
      if (requiredRole && requiredRole !== role) {
        item.style.display = 'none';
      }
    });
  }

  // ─── Section Switching ────────────────────────────────────────────────────
  function showSection(sectionId) {
    contentSections.forEach(function (section) {
      section.classList.add('hidden');
    });
    var target = document.getElementById(sectionId);
    if (target) {
      target.classList.remove('hidden');
    }
    // Compare against data-section value (without 'section-' prefix)
    var dataSectionValue = sectionId.replace(/^section-/, '');
    navItems.forEach(function (item) {
      item.classList.remove('active');
      if (item.getAttribute('data-section') === dataSectionValue) {
        item.classList.add('active');
      }
    });
    // Load section data when switching
    if (sectionId === 'section-kb-articles') {
      loadKBArticles();
    } else if (sectionId === 'section-users') {
      loadUserList();
    } else if (sectionId === 'section-monitors') {
      loadMonitors();
    }
  }

  function setupSectionSwitching() {
    navItems.forEach(function (item) {
      item.addEventListener('click', function (e) {
        e.preventDefault();
        var sectionId = item.getAttribute('data-section');
        if (sectionId) {
          showSection('section-' + sectionId);
          closeSidebarMobile();
        }
      });
    });
  }

  // ─── Hamburger Menu Toggle ────────────────────────────────────────────────
  function setupHamburgerMenu() {
    if (hamburgerBtn) {
      hamburgerBtn.addEventListener('click', function () {
        if (sidebar) sidebar.classList.toggle('open');
        if (sidebarOverlay) sidebarOverlay.classList.toggle('open');
      });
    }
    if (sidebarOverlay) {
      sidebarOverlay.addEventListener('click', function () {
        closeSidebarMobile();
      });
    }
  }

  function closeSidebarMobile() {
    if (sidebar) sidebar.classList.remove('open');
    if (sidebarOverlay) sidebarOverlay.classList.remove('open');
  }

  // ─── Logout ───────────────────────────────────────────────────────────────
  function setupLogout() {
    if (logoutBtn) {
      logoutBtn.addEventListener('click', function (e) {
        e.preventDefault();
        Auth.logout();
      });
    }
  }

  // ─── KB Articles Section ──────────────────────────────────────────────────
  function loadKBArticles() {
    var container = document.getElementById('kb-articles-list');
    if (!container) return;

    container.innerHTML = '<p class="loading-text">Loading documents...</p>';

    fetch(API_BASE + '/kb/documents', {
      method: 'GET',
      headers: Auth.getAuthHeaders(),
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Failed to load documents (status ' + response.status + ')');
        }
        return response.json();
      })
      .then(function (data) {
        var documents = data.data || data.documents || data;
        if (!Array.isArray(documents)) {
          documents = [];
        }
        renderKBArticles(documents, container);
      })
      .catch(function (err) {
        container.innerHTML = '<p class="error-text">' + escapeHtml(err.message) + '</p>';
      });
  }

  function renderKBArticles(documents, container) {
    if (documents.length === 0) {
      container.innerHTML = '<p class="empty-text">No documents uploaded yet.</p>';
      return;
    }

    var html = '<table class="data-table" role="grid" aria-label="Knowledge base documents">';
    html += '<thead><tr><th>Title</th><th>Uploaded By</th><th>Upload Date</th><th>Action</th></tr></thead>';
    html += '<tbody>';

    documents.forEach(function (doc) {
      var uploadDate = doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : 'N/A';
      html += '<tr>';
      html += '<td>' + escapeHtml(doc.title || doc.filename || 'Untitled') + '</td>';
      html += '<td>' + escapeHtml(doc.uploaded_by || 'Unknown') + '</td>';
      html += '<td>' + escapeHtml(uploadDate) + '</td>';
      html += '<td><a href="#" class="btn-link" data-doc-id="' + doc.id + '" aria-label="Download ' + escapeHtml(doc.title || 'document') + '">Download</a></td>';
      html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    // Attach download handlers
    container.querySelectorAll('[data-doc-id]').forEach(function (link) {
      link.addEventListener('click', function (e) {
        e.preventDefault();
        downloadDocument(link.getAttribute('data-doc-id'));
      });
    });
  }

  function downloadDocument(docId) {
    var token = Auth.getToken();
    // Open download in a new window with auth
    fetch(API_BASE + '/kb/documents/' + docId, {
      method: 'GET',
      headers: Auth.getAuthHeaders(),
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Download failed (status ' + response.status + ')');
        }
        return response.blob();
      })
      .then(function (blob) {
        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'document_' + docId;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      })
      .catch(function (err) {
        alert('Download error: ' + err.message);
      });
  }

  // ─── KB Upload Section (Admin Only) ───────────────────────────────────────
  function setupKBUpload() {
    var form = document.getElementById('kb-upload-form');
    if (!form) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var titleInput = document.getElementById('kb-title');
      var fileInput = document.getElementById('kb-file');
      var messageEl = document.getElementById('upload-status');

      var title = titleInput ? titleInput.value.trim() : '';
      var file = fileInput && fileInput.files.length > 0 ? fileInput.files[0] : null;

      if (messageEl) {
        messageEl.textContent = '';
        messageEl.className = 'form-message';
      }

      if (!title) {
        showFormMessage(messageEl, 'Please enter a document title.', 'error');
        return;
      }
      if (!file) {
        showFormMessage(messageEl, 'Please select a file to upload.', 'error');
        return;
      }

      var formData = new FormData();
      formData.append('title', title);
      formData.append('file', file);

      var submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;

      fetch(API_BASE + '/kb/documents', {
        method: 'POST',
        headers: Auth.getAuthHeaders(),
        body: formData,
      })
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (data) {
              var msg = (data.error && data.error.message) || data.detail || 'Upload failed';
              throw new Error(msg);
            });
          }
          return response.json();
        })
        .then(function (data) {
          showFormMessage(messageEl, 'Document uploaded successfully!', 'success');
          if (titleInput) titleInput.value = '';
          if (fileInput) fileInput.value = '';
        })
        .catch(function (err) {
          showFormMessage(messageEl, err.message, 'error');
        })
        .finally(function () {
          if (submitBtn) submitBtn.disabled = false;
        });
    });
  }

  // ─── User Management Section (Admin Only) ─────────────────────────────────
  function setupUserManagement() {
    var form = document.getElementById('create-user-form');
    if (!form) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var usernameInput = document.getElementById('new-user-username');
      var passwordInput = document.getElementById('new-user-password');
      var roleSelect = document.getElementById('new-user-role');
      var messageEl = document.getElementById('create-user-status');

      var username = usernameInput ? usernameInput.value.trim() : '';
      var password = passwordInput ? passwordInput.value : '';
      var userRole = roleSelect ? roleSelect.value : 'L1_User';

      if (messageEl) {
        messageEl.textContent = '';
        messageEl.className = 'form-message';
      }

      if (!username) {
        showFormMessage(messageEl, 'Please enter a username.', 'error');
        return;
      }
      if (!password) {
        showFormMessage(messageEl, 'Please enter a password.', 'error');
        return;
      }

      var submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;

      fetch(API_BASE + '/users', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, Auth.getAuthHeaders()),
        body: JSON.stringify({ username: username, password: password, role: userRole }),
      })
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (data) {
              var msg = (data.error && data.error.message) || data.detail || 'Failed to create user';
              throw new Error(msg);
            });
          }
          return response.json();
        })
        .then(function (data) {
          showFormMessage(messageEl, 'User "' + escapeHtml(username) + '" created successfully!', 'success');
          if (usernameInput) usernameInput.value = '';
          if (passwordInput) passwordInput.value = '';
          if (roleSelect) roleSelect.value = 'L1_User';
          loadUserList();
        })
        .catch(function (err) {
          showFormMessage(messageEl, err.message, 'error');
        })
        .finally(function () {
          if (submitBtn) submitBtn.disabled = false;
        });
    });
  }

  function loadUserList() {
    var container = document.getElementById('users-table-body');
    if (!container) return;

    container.innerHTML = '<tr><td colspan="3" class="loading-text">Loading users...</td></tr>';

    fetch(API_BASE + '/users', {
      method: 'GET',
      headers: Auth.getAuthHeaders(),
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Failed to load users (status ' + response.status + ')');
        }
        return response.json();
      })
      .then(function (data) {
        var users = data.data || data.users || data;
        if (!Array.isArray(users)) {
          users = [];
        }
        renderUserList(users, container);
      })
      .catch(function (err) {
        container.innerHTML = '<tr><td colspan="3" class="error-text">' + escapeHtml(err.message) + '</td></tr>';
      });
  }

  function renderUserList(users, container) {
    if (users.length === 0) {
      container.innerHTML = '<tr><td colspan="3" class="empty-text">No users found.</td></tr>';
      return;
    }

    var html = '';
    users.forEach(function (user) {
      var createdDate = user.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A';
      html += '<tr>';
      html += '<td>' + escapeHtml(user.username || '') + '</td>';
      html += '<td>' + escapeHtml(user.role || '') + '</td>';
      html += '<td>' + escapeHtml(createdDate) + '</td>';
      html += '</tr>';
    });

    container.innerHTML = html;
  }

  // ─── Monitors Section ─────────────────────────────────────────────────────
  function loadMonitors() {
    loadMonitorStatus();
    loadMonitorCosts();
  }

  function loadMonitorStatus() {
    var container = document.getElementById('monitors-status-list');
    if (!container) return;

    container.innerHTML = '<p class="loading-text">Loading resource statuses...</p>';

    fetch(API_BASE + '/status', {
      method: 'GET',
      headers: Auth.getAuthHeaders(),
    })
      .then(function(response) {
        if (!response.ok) throw new Error('Failed to load status (HTTP ' + response.status + ')');
        return response.json();
      })
      .then(function(data) {
        var statuses = data.data || data;
        if (!Array.isArray(statuses) || statuses.length === 0) {
          container.innerHTML = '<p class="empty-text">No resource data available. Configure cloud provider credentials to see live data.</p>';
          return;
        }
        var html = '<table class="data-table"><thead><tr><th>Resource ID</th><th>Provider</th><th>State</th><th>CPU %</th></tr></thead><tbody>';
        statuses.forEach(function(s) {
          var cpuDisplay = s.cpu_available ? (s.cpu_utilization !== null ? s.cpu_utilization + '%' : 'N/A') : 'Unavailable';
          var stateClass = s.state === 'running' ? 'color: #10b981' : (s.state === 'stopped' ? 'color: #f59e0b' : 'color: #ef4444');
          html += '<tr>';
          html += '<td>' + escapeHtml(s.resource_id) + '</td>';
          html += '<td><strong>' + escapeHtml(s.provider) + '</strong></td>';
          html += '<td style="' + stateClass + '; font-weight: 600;">' + escapeHtml(s.state) + '</td>';
          html += '<td>' + escapeHtml(cpuDisplay) + '</td>';
          html += '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
      })
      .catch(function(err) {
        container.innerHTML = '<p class="empty-text">No resource data available. Configure cloud provider credentials to see live data.</p>';
      });
  }

  function loadMonitorCosts() {
    var container = document.getElementById('monitors-cost-list');
    if (!container) return;

    container.innerHTML = '<p class="loading-text">Loading cost data...</p>';

    fetch(API_BASE + '/costs', {
      method: 'GET',
      headers: Auth.getAuthHeaders(),
    })
      .then(function(response) {
        if (!response.ok) throw new Error('Failed to load costs (HTTP ' + response.status + ')');
        return response.json();
      })
      .then(function(data) {
        var costs = data.data || data;
        if (!Array.isArray(costs) || costs.length === 0) {
          container.innerHTML = '<p class="empty-text">No cost data available. Configure cloud provider credentials to see live data.</p>';
          return;
        }
        var html = '<table class="data-table"><thead><tr><th>Provider</th><th>Resource Type</th><th>Cost (USD)</th><th>Period</th></tr></thead><tbody>';
        costs.forEach(function(c) {
          html += '<tr>';
          html += '<td><strong>' + escapeHtml(c.provider) + '</strong></td>';
          html += '<td>' + escapeHtml(c.resource_type) + '</td>';
          html += '<td>$' + escapeHtml(String(c.cost_amount.toFixed(2))) + '</td>';
          html += '<td>' + escapeHtml(c.period_start) + ' → ' + escapeHtml(c.period_end) + '</td>';
          html += '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
      })
      .catch(function(err) {
        container.innerHTML = '<p class="empty-text">No cost data available. Configure cloud provider credentials to see live data.</p>';
      });
  }

  // ─── Bot Widget ─────────────────────────────────────────────────────────
  function setupBotWidget() {
    var toggleBtn = document.getElementById('bot-toggle-btn');
    var closeBtn = document.getElementById('bot-close-btn');
    var panel = document.getElementById('bot-panel');
    var form = document.getElementById('bot-query-form');
    var input = document.getElementById('bot-query-input');
    var messages = document.getElementById('bot-messages');

    if (!toggleBtn || !panel) return;

    // Only show bot for Admin users
    if (role !== 'Admin') {
      document.getElementById('query-bot-widget').style.display = 'none';
      return;
    }

    toggleBtn.addEventListener('click', function() {
      panel.classList.toggle('bot-panel--closed');
      if (!panel.classList.contains('bot-panel--closed')) {
        input.focus();
      }
    });

    closeBtn.addEventListener('click', function() {
      panel.classList.add('bot-panel--closed');
    });

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var query = input.value.trim();
      if (!query) return;

      // Add user message
      addMessage(query, 'user');
      input.value = '';

      // Add loading indicator
      var loadingEl = addMessage('Processing your query...', 'loading');

      // Call API
      fetch(API_BASE + '/query', {
        method: 'POST',
        headers: Object.assign({'Content-Type': 'application/json'}, Auth.getAuthHeaders()),
        body: JSON.stringify({ query: query }),
      })
      .then(function(response) {
        if (!response.ok) {
          return response.json().then(function(data) {
            throw new Error((data.error && data.error.message) || data.detail || 'Query failed');
          });
        }
        return response.json();
      })
      .then(function(data) {
        loadingEl.remove();
        var result = data.data || data;
        var responseText = '';
        
        if (result.success === false) {
          responseText = '❌ ' + (result.error_message || 'Action failed');
        } else {
          responseText = '✅ ' + (result.intent || 'Action processed');
          
          // Show instance details if available in metadata
          if (result.metadata && result.metadata.instances && result.metadata.instances.length > 0) {
            responseText += '\n\n📊 Instances:';
            result.metadata.instances.forEach(function(inst) {
              var stateEmoji = inst.state === 'running' ? '🟢' : (inst.state === 'stopped' ? '🟡' : '🔴');
              var cpuStr = inst.cpu !== null && inst.cpu !== undefined ? inst.cpu + '%' : 'N/A';
              var typeStr = inst.instance_type ? ' [' + inst.instance_type + (inst.free_tier ? ' ✓ Free Tier' : '') + ']' : '';
              responseText += '\n  ' + stateEmoji + ' ' + inst.resource_id + typeStr + ' (' + inst.state + ') CPU: ' + cpuStr;
            });
          } else if (result.metadata && result.metadata.total_cost !== undefined) {
            responseText += '\n\n💰 Total: $' + result.metadata.total_cost.toFixed(2);
            responseText += '\n  Entries: ' + (result.metadata.entries || 0);
          } else {
            responseText += '\n\nProvider: ' + (result.provider || 'N/A');
            responseText += '\nState: ' + (result.state || 'Completed');
          }
          
          if (result.error_message) {
            responseText += '\n⚠️ ' + result.error_message;
          }
        }
        
        addMessage(responseText, 'response');
      })
      .catch(function(err) {
        loadingEl.remove();
        addMessage(err.message, 'error');
      });
    });

    function addMessage(text, type) {
      var div = document.createElement('div');
      div.className = 'bot-message bot-message--' + type;
      div.textContent = text;
      messages.appendChild(div);
      messages.scrollTop = messages.scrollHeight;
      return div;
    }
  }

  // ─── Utility Functions ────────────────────────────────────────────────────
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
  }

  function showFormMessage(el, message, type) {
    if (!el) return;
    el.textContent = message;
    el.className = 'form-message form-message--' + type;
  }

  // ─── Initialize ───────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    displayUserInfo();
    setupNavigation();
    setupSectionSwitching();
    setupHamburgerMenu();
    setupLogout();
    setupKBUpload();
    setupUserManagement();
    setupBotWidget();

    // Show default section based on role
    if (role === 'Admin') {
      showSection('section-kb-articles');
    } else {
      showSection('section-kb-articles');
    }
  });
})();
