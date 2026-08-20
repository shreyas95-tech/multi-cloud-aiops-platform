/**
 * Admin page with tabbed interface: Groups, Users, Email Ingestion, Knowledge Base.
 */
import React, { useState, useEffect } from 'react';
import { Link, Navigate } from 'react-router-dom';
import {
  getUsers, createUser, getGroups, createGroup, assignUserToGroup,
  type AdminUser, type AdminGroup,
} from '../services/api';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';

type Tab = 'groups' | 'users' | 'rules' | 'email' | 'knowledge';

// Sub-component for rules list (fetches its own data)
function RulesList({ onDelete }: { onDelete: (id: string) => Promise<void> }) {
  const [rules, setRules] = useState<any[]>([]);

  useEffect(() => { loadRules(); }, []);

  const loadRules = async () => {
    try {
      const { data } = await api.get('/admin/rules');
      setRules(data.rules || []);
    } catch { /* ignore */ }
  };

  if (rules.length === 0) return <p style={{ color: '#94a3b8', fontSize: '0.85rem', fontStyle: 'italic' }}>No rules defined yet. Emails will create new reports by default.</p>;

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
      <thead>
        <tr>
          <th style={{ textAlign: 'left', padding: '0.5rem', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '0.75rem', textTransform: 'uppercase' }}>Priority</th>
          <th style={{ textAlign: 'left', padding: '0.5rem', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '0.75rem', textTransform: 'uppercase' }}>Rule Name</th>
          <th style={{ textAlign: 'left', padding: '0.5rem', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '0.75rem', textTransform: 'uppercase' }}>Target Report</th>
          <th style={{ textAlign: 'left', padding: '0.5rem', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '0.75rem', textTransform: 'uppercase' }}>Conditions</th>
          <th style={{ textAlign: 'left', padding: '0.5rem', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '0.75rem', textTransform: 'uppercase' }}>Action</th>
        </tr>
      </thead>
      <tbody>
        {rules.map((r: any) => (
          <tr key={r.id}>
            <td style={{ padding: '0.5rem', borderBottom: '1px solid #f1f5f9' }}>{r.priority}</td>
            <td style={{ padding: '0.5rem', borderBottom: '1px solid #f1f5f9', fontWeight: 500 }}>{r.name}</td>
            <td style={{ padding: '0.5rem', borderBottom: '1px solid #f1f5f9', color: '#6366f1', fontWeight: 500 }}>{r.target_report_name}</td>
            <td style={{ padding: '0.5rem', borderBottom: '1px solid #f1f5f9', fontSize: '0.8rem', color: '#64748b' }}>
              {r.subject_contains && <div>Subject: "{r.subject_contains}"</div>}
              {r.filename_contains && <div>File: "{r.filename_contains}"</div>}
              {r.sender_email && <div>From: {r.sender_email}</div>}
            </td>
            <td style={{ padding: '0.5rem', borderBottom: '1px solid #f1f5f9' }}>
              <button
                onClick={async () => { await onDelete(r.id); loadRules(); }}
                style={{ padding: '0.2rem 0.5rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '4px', color: '#dc2626', cursor: 'pointer', fontSize: '0.75rem' }}
              >
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AdminPage() {
  const { user, isAdmin, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>('groups');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Create user form
  const [newUsername, setNewUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [newGroupId, setNewGroupId] = useState('');
  const [isCreatingUser, setIsCreatingUser] = useState(false);

  // Create group form
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupDesc, setNewGroupDesc] = useState('');
  const [isCreatingGroup, setIsCreatingGroup] = useState(false);

  if (!isAdmin) return <Navigate to="/" replace />;

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [u, g] = await Promise.all([getUsers(), getGroups()]);
      setUsers(u);
      setGroups(g);
    } catch {
      setError('Failed to load data.');
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setSuccess(null); setIsCreatingUser(true);
    try {
      await createUser(newUsername, newEmail, newPassword, newRole, newGroupId || undefined);
      setSuccess(`User "${newUsername}" created. They must reset password on first login.`);
      setNewUsername(''); setNewEmail(''); setNewPassword(''); setNewRole('user'); setNewGroupId('');
      await loadData();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.join(' ') : detail || 'Failed to create user.');
    } finally {
      setIsCreatingUser(false);
    }
  };

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setSuccess(null); setIsCreatingGroup(true);
    try {
      await createGroup(newGroupName, newGroupDesc || undefined);
      setSuccess(`Group "${newGroupName}" created.`);
      setNewGroupName(''); setNewGroupDesc('');
      await loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create group.');
    } finally {
      setIsCreatingGroup(false);
    }
  };

  const handleAssignGroup = async (userId: string, groupId: string) => {
    setError(null);
    try {
      await assignUserToGroup(userId, groupId || null);
      await loadData();
      setSuccess('User group updated.');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to assign group.');
    }
  };

  const handleDeleteUser = async (u: AdminUser) => {
    if (!confirm(`Delete user "${u.username}"? This cannot be undone.`)) return;
    setError(null);
    try {
      await api.delete(`/admin/users/${u.id}`);
      setSuccess(`User "${u.username}" deleted.`);
      await loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete user.');
    }
  };

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'groups', label: 'Groups', icon: '👥' },
    { id: 'users', label: 'Users', icon: '👤' },
    { id: 'rules', label: 'Ingestion Rules', icon: '🔀' },
    { id: 'email', label: 'Email Ingestion', icon: '📧' },
    { id: 'knowledge', label: 'Knowledge Base', icon: '📚' },
  ];

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.headerTitle}>Admin Panel</h1>
        <div style={styles.headerRight}>
          <Link to="/" style={styles.link}>Dashboard</Link>
          <Link to="/settings" style={styles.link}>Settings</Link>
          <span style={styles.username}>{user?.username}</span>
          <button onClick={logout} style={styles.logoutBtn}>Logout</button>
        </div>
      </header>

      <div style={styles.body}>
        {/* Tab Navigation */}
        <nav style={styles.tabNav}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => { setActiveTab(tab.id); setError(null); setSuccess(null); }}
              style={{
                ...styles.tabBtn,
                ...(activeTab === tab.id ? styles.tabBtnActive : {}),
              }}
            >
              <span style={{ marginRight: '0.4rem' }}>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Tab Content */}
        <div style={styles.tabContent}>
          {error && <div style={styles.error}>{error}</div>}
          {success && <div style={styles.success}>{success}</div>}

          {/* Groups Tab */}
          {activeTab === 'groups' && (
            <>
              <div style={styles.section}>
                <h2 style={styles.sectionTitle}>Create Group</h2>
                <form onSubmit={handleCreateGroup} style={styles.form}>
                  <input value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)}
                    placeholder="Group name" required style={styles.input} />
                  <input value={newGroupDesc} onChange={(e) => setNewGroupDesc(e.target.value)}
                    placeholder="Description (optional)" style={styles.input} />
                  <button type="submit" disabled={isCreatingGroup} style={styles.btn}>
                    {isCreatingGroup ? 'Creating...' : 'Create Group'}
                  </button>
                </form>
              </div>

              <div style={styles.section}>
                <h2 style={styles.sectionTitle}>All Groups ({groups.length})</h2>
                {groups.length === 0 ? <p style={styles.emptyText}>No groups created yet.</p> : (
                  <table style={styles.table}>
                    <thead><tr><th>Name</th><th>Description</th><th>Members</th></tr></thead>
                    <tbody>
                      {groups.map((g) => (
                        <tr key={g.id}>
                          <td><strong>{g.name}</strong></td>
                          <td>{g.description || '—'}</td>
                          <td>{g.member_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}

          {/* Users Tab */}
          {activeTab === 'users' && (
            <>
              <div style={styles.section}>
                <h2 style={styles.sectionTitle}>Create User</h2>
                <p style={styles.helpText}>New users must reset their password on first login.</p>
                <form onSubmit={handleCreateUser} style={styles.form}>
                  <input value={newUsername} onChange={(e) => setNewUsername(e.target.value)}
                    placeholder="Username" required minLength={3} style={styles.input} />
                  <input value={newEmail} onChange={(e) => setNewEmail(e.target.value)}
                    placeholder="Email" type="email" required style={styles.input} />
                  <input value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Temp password" type="password" required minLength={8} style={styles.input} />
                  <select value={newRole} onChange={(e) => setNewRole(e.target.value)} style={styles.input}>
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                  </select>
                  <select value={newGroupId} onChange={(e) => setNewGroupId(e.target.value)} style={styles.input}>
                    <option value="">No group</option>
                    {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                  <button type="submit" disabled={isCreatingUser} style={styles.btn}>
                    {isCreatingUser ? 'Creating...' : 'Create User'}
                  </button>
                </form>
              </div>

              <div style={styles.section}>
                <h2 style={styles.sectionTitle}>All Users ({users.length})</h2>
                <table style={styles.table}>
                  <thead><tr><th>Username</th><th>Email</th><th>Role</th><th>Group</th><th>Reset?</th><th>Action</th></tr></thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id}>
                        <td>{u.username}</td>
                        <td style={{ fontSize: '0.8rem', color: '#64748b' }}>{u.email}</td>
                        <td><span style={{ ...styles.roleBadge, backgroundColor: u.role === 'admin' ? '#fef2f2' : '#eff6ff', color: u.role === 'admin' ? '#dc2626' : '#2563eb' }}>{u.role}</span></td>
                        <td>
                          <select
                            value={u.group_id || ''}
                            onChange={(e) => handleAssignGroup(u.id, e.target.value)}
                            style={{ ...styles.input, padding: '0.25rem', fontSize: '0.8rem', width: 'auto' }}
                          >
                            <option value="">None</option>
                            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                          </select>
                        </td>
                        <td>{u.must_reset_password ? <span style={{ color: '#f59e0b' }}>Yes</span> : 'No'}</td>
                        <td>
                          <button onClick={() => handleDeleteUser(u)} style={styles.deleteBtn}>Remove</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Ingestion Rules Tab */}
          {activeTab === 'rules' && (
            <>
              <div style={styles.section}>
                <h2 style={styles.sectionTitle}>Create Ingestion Rule</h2>
                <p style={styles.helpText}>
                  Rules determine how incoming emails are matched to existing reports.
                  Data from matched emails is <strong>appended</strong> to the target report automatically.
                  At least one match condition is required.
                </p>
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    setError(null); setSuccess(null);
                    const form = e.target as HTMLFormElement;
                    const data = new FormData(form);
                    try {
                      await api.post('/admin/rules', {
                        name: data.get('rule_name'),
                        target_report_name: data.get('target_report'),
                        subject_contains: data.get('subject_contains') || null,
                        filename_contains: data.get('filename_contains') || null,
                        sender_email: data.get('sender_email') || null,
                        priority: parseInt(data.get('priority') as string) || 10,
                      });
                      setSuccess('Ingestion rule created.');
                      form.reset();
                    } catch (err: any) {
                      setError(err.response?.data?.detail || 'Failed to create rule.');
                    }
                  }}
                  style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxWidth: '500px' }}
                >
                  <input name="rule_name" placeholder="Rule name (e.g., Daily Tickets)" required style={styles.input} />
                  <input name="target_report" placeholder="Target report name (must match exactly)" required style={styles.input} />
                  <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '0.75rem' }}>
                    <p style={{ margin: '0 0 0.5rem', fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>Match conditions (at least one):</p>
                    <input name="subject_contains" placeholder="Subject contains..." style={{ ...styles.input, marginBottom: '0.5rem' }} />
                    <input name="filename_contains" placeholder="Filename contains..." style={{ ...styles.input, marginBottom: '0.5rem' }} />
                    <input name="sender_email" placeholder="Sender email (exact match)" type="email" style={{ ...styles.input, marginBottom: '0.5rem' }} />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <label style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 500 }}>Priority:</label>
                    <input name="priority" type="number" min="1" max="100" defaultValue="10" style={{ ...styles.input, maxWidth: '80px' }} />
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>(1 = highest, checked first)</span>
                  </div>
                  <button type="submit" style={{ ...styles.btn, alignSelf: 'flex-start' }}>Create Rule</button>
                </form>
              </div>

              <div style={styles.section}>
                <h2 style={styles.sectionTitle}>Active Rules</h2>
                <p style={styles.helpText}>
                  Rules are checked in priority order (lowest number first). Subject line patterns are used as fallback if no rules match.
                  <br />Subject pattern format: <code>"Report: Report Name"</code> or <code>"Daily Report - Report Name"</code>
                </p>
                <RulesList onDelete={async (id: string) => {
                  setError(null);
                  try {
                    await api.delete(`/admin/rules/${id}`);
                    setSuccess('Rule deleted.');
                  } catch (err: any) {
                    setError(err.response?.data?.detail || 'Failed to delete rule.');
                  }
                }} />
              </div>
            </>
          )}

          {/* Email Ingestion Tab */}
          {activeTab === 'email' && (
            <div style={styles.section}>
              <h2 style={styles.sectionTitle}>Email Ingestion</h2>
              <p style={styles.helpText}>
                Fetch report attachments from the configured email inbox. Emails from registered users
                with CSV/Excel/PDF attachments will be auto-processed through the analysis pipeline.
              </p>

              <div style={styles.configCard}>
                <h3 style={{ margin: '0 0 0.75rem', fontSize: '0.9rem' }}>Configuration</h3>
                <div style={styles.configRow}>
                  <span style={styles.configLabel}>Provider:</span>
                  <span style={styles.configValue}>IMAP (Gmail) / Microsoft Graph (Outlook)</span>
                </div>
                <div style={styles.configRow}>
                  <span style={styles.configLabel}>Auto-poll:</span>
                  <span style={styles.configValue}>Set EMAIL_POLL_ENABLED=true in .env</span>
                </div>
                <div style={styles.configRow}>
                  <span style={styles.configLabel}>Interval:</span>
                  <span style={styles.configValue}>Every 5 minutes (configurable)</span>
                </div>
              </div>

              <button
                onClick={async () => {
                  setError(null); setSuccess(null);
                  try {
                    const { data } = await api.post('/upload/check-email');
                    if (data.status === 'error') {
                      setError(data.message);
                    } else if (data.message && data.message.includes('No new emails')) {
                      setSuccess(data.message);
                    } else {
                      const count = data.emails_found || 0;
                      let msg = `Found ${count} email(s).`;
                      if (data.reports_created?.length > 0) {
                        msg += ` Created/updated ${data.reports_created.length} report(s): ${data.reports_created.map((r: any) => r.name).join(', ')}`;
                      } else if (count === 0) {
                        msg = 'No new emails found in inbox.';
                      }
                      setSuccess(msg);
                    }
                  } catch (err: any) {
                    setError(err.response?.data?.detail || 'Failed to check email.');
                  }
                }}
                style={{ ...styles.btn, marginTop: '1rem' }}
              >
                📧 Check Email Now
              </button>
            </div>
          )}

          {/* Knowledge Base Tab */}
          {activeTab === 'knowledge' && (
            <div style={styles.section}>
              <h2 style={styles.sectionTitle}>Knowledge Base (RAG)</h2>
              <p style={styles.helpText}>
                Upload runbooks and SOPs. When deviations are detected, relevant steps will be
                retrieved and included in alerts and QBot responses.
              </p>

              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const form = e.target as HTMLFormElement;
                  const fileInput = form.querySelector('input[type="file"]') as HTMLInputElement;
                  const file = fileInput?.files?.[0];
                  if (!file) return;
                  setError(null); setSuccess(null);
                  try {
                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('doc_type', 'runbook');
                    const { data } = await api.post('/ai/knowledge-base/upload', formData, {
                      headers: { 'Content-Type': 'multipart/form-data' },
                    });
                    setSuccess(`Document "${data.filename}" uploaded (${data.chunks_created} chunks indexed).`);
                    fileInput.value = '';
                  } catch (err: any) {
                    setError(err.response?.data?.detail || 'Failed to upload document.');
                  }
                }}
                style={{ ...styles.form, marginBottom: '1.5rem' }}
              >
                <input type="file" accept=".txt,.md,.pdf,.csv" required style={styles.fileInput} />
                <button type="submit" style={styles.btn}>Upload to KB</button>
              </form>

              <div style={styles.configCard}>
                <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem' }}>Supported Formats</h3>
                <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b' }}>
                  .txt, .md, .pdf — Documents are chunked and embedded for semantic search.
                  When a deviation matches content in your runbooks, the relevant steps appear in QBot and WhatsApp alerts.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', backgroundColor: '#f1f5f9' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 2rem', background: 'linear-gradient(135deg, #6366f1 0%, #06b6d4 100%)', color: '#fff', boxShadow: '0 4px 12px rgba(99,102,241,0.3)' },
  headerTitle: { margin: 0, fontSize: '1.4rem', fontWeight: 700 },
  headerRight: { display: 'flex', alignItems: 'center', gap: '1rem' },
  link: { color: '#fff', textDecoration: 'none', fontSize: '0.875rem', fontWeight: 500 },
  username: { fontSize: '0.875rem', color: '#c7d2fe' },
  logoutBtn: { padding: '0.4rem 0.75rem', backgroundColor: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)', borderRadius: '6px', cursor: 'pointer', fontSize: '0.8rem', color: '#fff' },
  body: { maxWidth: '1000px', margin: '0 auto', padding: '2rem' },
  tabNav: { display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '2px solid #e2e8f0', paddingBottom: '0' },
  tabBtn: { padding: '0.7rem 1.2rem', border: 'none', borderBottom: '3px solid transparent', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 500, color: '#64748b', borderRadius: '8px 8px 0 0', transition: 'all 0.2s' },
  tabBtnActive: { color: '#6366f1', borderBottomColor: '#6366f1', backgroundColor: '#eff6ff', fontWeight: 600 },
  tabContent: { backgroundColor: '#fff', borderRadius: '12px', padding: '2rem', boxShadow: '0 1px 4px rgba(0,0,0,0.06)' },
  error: { backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', padding: '0.75rem 1rem', marginBottom: '1rem', color: '#dc2626', fontSize: '0.875rem' },
  success: { backgroundColor: '#ecfdf5', border: '1px solid #a7f3d0', borderRadius: '8px', padding: '0.75rem 1rem', marginBottom: '1rem', color: '#059669', fontSize: '0.875rem' },
  section: { marginBottom: '2rem' },
  sectionTitle: { margin: '0 0 1rem', fontSize: '1.1rem', fontWeight: 600, color: '#1e293b' },
  helpText: { color: '#64748b', fontSize: '0.85rem', marginBottom: '1rem' },
  emptyText: { color: '#94a3b8', fontSize: '0.85rem', fontStyle: 'italic' },
  form: { display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' as const },
  input: { padding: '0.5rem 0.75rem', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '0.875rem', outline: 'none', width: '100%', maxWidth: '220px' },
  fileInput: { padding: '0.5rem', border: '2px dashed #e2e8f0', borderRadius: '8px', fontSize: '0.85rem', cursor: 'pointer', backgroundColor: '#f8fafc' },
  btn: { padding: '0.55rem 1.2rem', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600, boxShadow: '0 2px 8px rgba(99,102,241,0.2)' },
  deleteBtn: { padding: '0.25rem 0.6rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#dc2626', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 500 },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: '0.85rem' },
  roleBadge: { padding: '0.2rem 0.5rem', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 },
  configCard: { padding: '1rem 1.25rem', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', marginBottom: '1rem' },
  configRow: { display: 'flex', gap: '0.5rem', marginBottom: '0.4rem', fontSize: '0.85rem' },
  configLabel: { fontWeight: 600, color: '#475569', minWidth: '80px' },
  configValue: { color: '#64748b' },
};
