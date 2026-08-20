/**
 * Dashboard page: report list, trend visualization, deviation alerts.
 * - "Create Report" uploads baseline historical data
 * - "Add Data" on a selected report appends daily entries and triggers analysis
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import {
  getReports,
  getReportTrends,
  getReportDeviations,
  getGroups,
  type ReportSummary,
  type TrendVisualization,
  type Deviation,
  type AdminGroup,
} from '../services/api';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { useWebSocket, type WebSocketMessage } from '../hooks/useWebSocket';
import { ChatPanel } from '../components/ChatPanel';
import { Link } from 'react-router-dom';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

export function DashboardPage() {
  const { user, logout, isAdmin } = useAuth();
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [selectedReport, setSelectedReport] = useState<ReportSummary | null>(null);
  const [trendData, setTrendData] = useState<TrendVisualization | null>(null);
  const [deviations, setDeviations] = useState<Deviation[]>([]);
  const [days, setDays] = useState(30);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createReportName, setCreateReportName] = useState('');
  const [createFile, setCreateFile] = useState<File | null>(null);
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const addDataRef = useRef<HTMLInputElement>(null);
  const createReportRef = useRef<HTMLInputElement>(null);

  const handleWsMessage = useCallback((msg: WebSocketMessage) => {
    if (msg.type === 'trend_update' || msg.type === 'deviation_update') {
      if (selectedReport) {
        loadReportData(selectedReport.name, days);
      }
    }
  }, [selectedReport, days]);

  useWebSocket({ onMessage: handleWsMessage, enabled: true });

  useEffect(() => { loadReports(); }, []);
  useEffect(() => { if (isAdmin) loadGroups(); }, [isAdmin]);

  useEffect(() => {
    if (selectedReport) {
      loadReportData(selectedReport.name, days);
    }
  }, [selectedReport, days]);

  const loadReports = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getReports();
      setReports(data);
    } catch {
      setError('Failed to load reports.');
    } finally {
      setIsLoading(false);
    }
  };

  const loadGroups = async () => {
    try {
      const g = await getGroups();
      setGroups(g);
    } catch { /* ignore */ }
  };

  const loadReportData = async (reportName: string, rangeDays: number) => {
    try {
      const [trends, devs] = await Promise.all([
        getReportTrends(reportName, rangeDays),
        getReportDeviations(reportName, rangeDays),
      ]);
      setTrendData(trends);
      setDeviations(devs);
      setError(null);
    } catch {
      setError('Failed to load trend data.');
    }
  };

  // Create a new report with baseline data
  const handleSubmitCreateReport = async () => {
    if (!createFile || !createReportName.trim()) return;

    setIsUploading(true);
    setStatusMsg(null);
    setError(null);
    setShowCreateModal(false);
    try {
      const formData = new FormData();
      formData.append('file', createFile);
      formData.append('report_name', createReportName.trim());
      const { data } = await api.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setStatusMsg(`Report "${data.report_name}" created with ${data.data_points_created} data points.`);
      await loadReports();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create report.');
    } finally {
      setIsUploading(false);
      setCreateFile(null);
      setCreateReportName('');
    }
  };

  // Append daily data to the selected report
  const handleAddData = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedReport) return;

    setIsUploading(true);
    setStatusMsg(null);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const { data } = await api.post(`/upload/reports/${selectedReport.id}/append`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      let msg = `Added ${data.new_data_points} data points.`;
      if (data.deviations_found > 0) {
        msg += ` ${data.deviations_found} deviation(s) detected!`;
      }
      if (data.whatsapp_alerts_sent > 0) {
        msg += ` ${data.whatsapp_alerts_sent} WhatsApp alert(s) sent.`;
      }
      setStatusMsg(msg);
      await loadReportData(selectedReport.name, days);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add data.');
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  };

  const chartData = buildChartData(trendData, deviations);

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <a onClick={() => { setSelectedReport(null); setTrendData(null); setDeviations([]); setStatusMsg(null); }} style={{ textDecoration: 'none', color: 'inherit', cursor: 'pointer' }}><h1 style={styles.headerTitle}>ReportPulse</h1></a>
        <div style={styles.headerRight}>
          {isAdmin && <Link to="/admin" style={{ color: '#fbbf24', textDecoration: 'none', fontSize: '0.875rem', fontWeight: 700 }}>Admin</Link>}
          <Link to="/settings" style={styles.settingsLink}>Settings</Link>
          <span style={styles.username}>{user?.username}</span>
          <button onClick={logout} style={styles.logoutBtn}>Logout</button>
        </div>
      </header>

      <div style={styles.content}>
        {/* Sidebar toggle button */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          style={{
            position: 'absolute' as const,
            left: sidebarOpen ? '248px' : '8px',
            top: '76px',
            zIndex: 10,
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            backgroundColor: '#6366f1',
            color: '#fff',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '0.75rem',
            fontWeight: 700,
            boxShadow: '0 2px 8px rgba(99,102,241,0.4)',
            transition: 'left 0.3s ease',
          }}
          title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {sidebarOpen ? '\u2039' : '\u203A'}
        </button>

        {/* Sidebar */}
        <aside style={{ ...styles.sidebar, width: sidebarOpen ? '260px' : '0px', padding: sidebarOpen ? '1.25rem' : '0', overflow: 'hidden', transition: 'width 0.3s ease, padding 0.3s ease' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0, fontSize: '1rem' }}>Reports</h2>
            {isAdmin && (
              <button
                onClick={() => { setShowCreateModal(true); setCreateReportName(''); setCreateFile(null); }}
                style={styles.createBtn}
              >
                + New
              </button>
            )}
          </div>

          {reports.length === 0 && !isLoading ? (
            <p style={styles.emptyMsg}>
              No reports yet. Click "+ New" to upload baseline data.
            </p>
          ) : (
            <ul style={styles.reportList}>
              {reports.map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => setSelectedReport(r)}
                    style={{
                      ...styles.reportItem,
                      backgroundColor: selectedReport?.id === r.id ? 'rgba(99,102,241,0.2)' : 'transparent',
                      fontWeight: selectedReport?.id === r.id ? 600 : 400,
                      borderLeft: selectedReport?.id === r.id ? '3px solid #6366f1' : '3px solid transparent',
                    }}
                  >
                    <div>
                      <span>{r.name}</span>
                      {(r as any).group_name && <div style={{ fontSize: '0.65rem', color: '#94a3b8', marginTop: '2px' }}>{(r as any).group_name}</div>}
                    </div>
                    <small style={{ color: '#64748b' }}>{r.file_type.toUpperCase()}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        {/* Main */}
        <main style={styles.main}>
          {error && (
            <div style={styles.error} role="alert">{error}</div>
          )}
          {statusMsg && (
            <div style={styles.success} role="status">{statusMsg}</div>
          )}

          {selectedReport ? (
            <>
              {/* Report header with Add Data button */}
              <div style={styles.reportHeader}>
                <div>
                  <h2 style={{ margin: 0 }}>{selectedReport.name}</h2>
                  <small style={{ color: '#666' }}>
                    Created {new Date(selectedReport.received_at).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' })}
                  </small>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <select
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                    style={styles.select}
                  >
                    <option value={7}>7 days</option>
                    <option value={30}>30 days</option>
                    <option value={90}>90 days</option>
                    <option value={180}>180 days</option>
                    <option value={365}>365 days</option>
                  </select>
                  {isAdmin && (
                    <label style={styles.addDataBtn}>
                      {isUploading ? 'Uploading...' : 'Add Data'}
                      <input
                        ref={addDataRef}
                        type="file"
                        accept=".pdf,.xlsx,.xls,.csv"
                        onChange={handleAddData}
                        style={{ display: 'none' }}
                        disabled={isUploading}
                      />
                    </label>
                  )}
                  {isAdmin && (
                    <button
                      onClick={async () => {
                        if (!confirm(`Delete report "${selectedReport.name}"? All data, trends, and deviations will be permanently removed.`)) return;
                        try {
                          await api.delete(`/reports/${selectedReport.id}`);
                          setSelectedReport(null);
                          setTrendData(null);
                          setDeviations([]);
                          setStatusMsg(`Report "${selectedReport.name}" deleted.`);
                          await loadReports();
                        } catch (err: any) {
                          setError(err.response?.data?.detail || 'Failed to delete report.');
                        }
                      }}
                      style={styles.deleteReportBtn}
                      title="Delete this report"
                    >
                      🗑
                    </button>
                  )}
                  {isAdmin && groups.length > 0 && (
                    <select
                      value={(selectedReport as any).group_id || ''}
                      onChange={async (e) => {
                        const gid = e.target.value || null;
                        try {
                          await api.put(`/reports/${selectedReport.id}/group`, null, { params: { group_id: gid } });
                          setStatusMsg('Report group updated.');
                          await loadReports();
                        } catch (err: any) {
                          setError(err.response?.data?.detail || 'Failed to update group.');
                        }
                      }}
                      style={{ ...styles.select, fontSize: '0.75rem' }}
                      title="Assign to group"
                    >
                      <option value="">No group</option>
                      {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                    </select>
                  )}
                </div>
              </div>

              {/* Chart */}
              {chartData && (
                <div style={styles.chartContainer}>
                  <Line data={{ ...chartData, _fullDates: chartData._fullDates } as any} options={chartOptions} />
                </div>
              )}

              {/* Trends */}
              {trendData && trendData.trends.length > 0 && (
                <div style={{ marginBottom: '2rem' }}>
                  <h3>Trend Analysis</h3>
                  <div style={styles.trendCards}>
                    {trendData.trends.slice(0, 6).map((t) => (
                      <div key={t.id} style={styles.trendCard}>
                        <strong>{t.metric_name}</strong>
                        <span style={{ color: directionColor(t.direction) }}>
                          {t.direction} ({t.rate_of_change_pct > 0 ? '+' : ''}{t.rate_of_change_pct.toFixed(2)}%)
                        </span>
                        <small>{t.algorithm_used} | {t.data_points_count} pts</small>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Deviations */}
              {deviations.length > 0 && (
                <div>
                  <h3>Deviations Detected</h3>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>Severity</th>
                        <th>Expected</th>
                        <th>Actual</th>
                        <th>Score</th>
                        <th>Detected</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deviations.map((d) => (
                        <tr key={d.id}>
                          <td>{d.metric_name}</td>
                          <td><span style={{ ...styles.badge, backgroundColor: severityColor(d.severity) }}>{d.severity}</span></td>
                          <td>{d.expected_value.toFixed(2)}</td>
                          <td>{d.actual_value.toFixed(2)}</td>
                          <td>{d.deviation_score.toFixed(2)}σ</td>
                          <td>{new Date(d.detected_at).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' })}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <div style={styles.emptyState}>
              <h2 style={{ fontSize: '1.75rem', color: '#1e293b' }}>Welcome to ReportPulse</h2>
              <p>Click "+ New" to create a report with historical data, then use "Add Data" to append daily entries.</p>
              <p>When deviations are detected, you'll get a WhatsApp alert automatically.</p>
            </div>
          )}
        </main>
      </div>

      {/* Create Report Modal */}
      {showCreateModal && (
        <div style={modalStyles.overlay} onClick={() => setShowCreateModal(false)}>
          <div style={modalStyles.modal} onClick={(e) => e.stopPropagation()}>
            <h2 style={modalStyles.title}>Create New Report</h2>

            <div style={modalStyles.field}>
              <label style={modalStyles.label}>Team</label>
              <input
                type="text"
                value={user?.group_name || 'No team assigned'}
                disabled
                style={{ ...modalStyles.input, backgroundColor: '#f1f5f9', color: '#64748b' }}
              />
            </div>

            <div style={modalStyles.field}>
              <label style={modalStyles.label}>Report Name <span style={{ color: '#ef4444' }}>*</span></label>
              <input
                type="text"
                value={createReportName}
                onChange={(e) => setCreateReportName(e.target.value)}
                placeholder="Enter report name"
                required
                style={modalStyles.input}
                autoFocus
              />
            </div>

            <div style={modalStyles.field}>
              <label style={modalStyles.label}>Upload File <span style={{ color: '#ef4444' }}>*</span></label>
              <input
                type="file"
                accept=".pdf,.xlsx,.xls,.csv"
                onChange={(e) => setCreateFile(e.target.files?.[0] || null)}
                style={modalStyles.fileInput}
              />
              {createFile && (
                <div style={modalStyles.fileInfo}>
                  Selected: {createFile.name} ({(createFile.size / 1024).toFixed(1)} KB)
                </div>
              )}
            </div>

            <div style={modalStyles.actions}>
              <button onClick={() => setShowCreateModal(false)} style={modalStyles.cancelBtn}>
                Cancel
              </button>
              <button
                onClick={handleSubmitCreateReport}
                disabled={!createReportName.trim() || !createFile || isUploading}
                style={{
                  ...modalStyles.submitBtn,
                  opacity: (!createReportName.trim() || !createFile) ? 0.5 : 1,
                }}
              >
                {isUploading ? 'Uploading...' : 'Upload & Create Report'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating QBot */}
      <ChatPanel />
    </div>
  );
}

// --- Chart helpers ---
function buildChartData(trend: TrendVisualization | null, deviations: Deviation[]) {
  if (!trend || trend.data_points.length === 0) return null;
  const metrics = new Map<string, { values: number[]; labels: string[]; fullDates: string[] }>();
  for (const dp of trend.data_points) {
    if (!metrics.has(dp.metric_name)) metrics.set(dp.metric_name, { values: [], labels: [], fullDates: [] });
    const m = metrics.get(dp.metric_name)!;
    m.values.push(dp.value);
    m.labels.push(new Date(dp.timestamp).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' }));
    m.fullDates.push(new Date(dp.timestamp).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }));
  }
  const colors = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
  const datasets = Array.from(metrics.entries()).slice(0, 4).map(([name, data], idx) => ({
    label: name, data: data.values, borderColor: colors[idx % colors.length],
    backgroundColor: colors[idx % colors.length] + '20', tension: 0.3, pointRadius: 3,
  }));
  const firstMetric = metrics.values().next().value;
  return { labels: firstMetric?.labels || [], datasets, _fullDates: firstMetric?.fullDates || [] };
}

const chartOptions = {
  responsive: true, maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top' as const },
    title: { display: false },
    tooltip: {
      callbacks: {
        title: (items: any[]) => {
          if (!items.length) return '';
          const chart = items[0].chart;
          const fullDates = (chart.data as any)._fullDates;
          if (fullDates && fullDates[items[0].dataIndex]) {
            return fullDates[items[0].dataIndex];
          }
          return items[0].label;
        },
      },
    },
  },
  scales: { y: { beginAtZero: false } },
};

function directionColor(d: string) { return d === 'increasing' ? '#10b981' : d === 'decreasing' ? '#ef4444' : '#64748b'; }
function severityColor(s: string) { return s === 'high' ? '#ef4444' : s === 'medium' ? '#f59e0b' : '#06b6d4'; }

// --- Styles ---
const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', backgroundColor: '#f1f5f9' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 2rem', background: 'linear-gradient(135deg, #6366f1 0%, #06b6d4 100%)', color: '#fff', boxShadow: '0 4px 12px rgba(99,102,241,0.3)' },
  headerTitle: { margin: 0, fontSize: '1.4rem', fontWeight: 700, letterSpacing: '-0.5px' },
  headerRight: { display: 'flex', alignItems: 'center', gap: '1rem' },
  settingsLink: { color: '#fff', textDecoration: 'none', fontSize: '0.875rem', fontWeight: 500 },
  username: { fontSize: '0.875rem', color: '#fff', fontWeight: 600 },
  logoutBtn: { padding: '0.5rem 1rem', backgroundColor: 'rgba(255,255,255,0.25)', border: '2px solid rgba(255,255,255,0.6)', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem', color: '#fff', fontWeight: 600, backdropFilter: 'blur(4px)' },
  content: { display: 'flex', minHeight: 'calc(100vh - 64px)', position: 'relative' as const },
  sidebar: { width: '260px', backgroundColor: '#1e293b', padding: '1.25rem', overflowY: 'auto' as const, color: '#e2e8f0' },
  createBtn: { padding: '0.35rem 0.7rem', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', color: '#fff', borderRadius: '6px', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600, border: 'none' },
  emptyMsg: { fontSize: '0.875rem', color: '#94a3b8' },
  reportList: { listStyle: 'none', padding: 0, margin: 0 },
  reportItem: { width: '100%', padding: '0.7rem 0.75rem', border: 'none', borderRadius: '8px', cursor: 'pointer', textAlign: 'left' as const, display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.875rem', color: '#e2e8f0', transition: 'background 0.2s' },
  main: { flex: 1, padding: '2rem', overflowY: 'auto' as const },
  error: { backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '10px', padding: '0.75rem 1rem', marginBottom: '1rem', color: '#dc2626', fontSize: '0.875rem' },
  success: { backgroundColor: '#ecfdf5', border: '1px solid #a7f3d0', borderRadius: '10px', padding: '0.75rem 1rem', marginBottom: '1rem', color: '#059669', fontSize: '0.875rem' },
  reportHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem', flexWrap: 'wrap' as const, gap: '1rem' },
  select: { padding: '0.4rem 0.6rem', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '0.8rem', backgroundColor: '#fff' },
  addDataBtn: { padding: '0.5rem 1.2rem', background: 'linear-gradient(135deg, #10b981, #06b6d4)', color: '#fff', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600, border: 'none', boxShadow: '0 2px 8px rgba(16,185,129,0.3)' },
  deleteReportBtn: { width: '36px', height: '36px', borderRadius: '8px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', cursor: 'pointer', fontSize: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  chartContainer: { height: '320px', marginBottom: '2rem', backgroundColor: '#fff', borderRadius: '12px', padding: '1.5rem', boxShadow: '0 1px 4px rgba(0,0,0,0.06)' },
  trendCards: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '1rem' },
  trendCard: { padding: '1.25rem', backgroundColor: '#fff', borderRadius: '12px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', display: 'flex', flexDirection: 'column' as const, gap: '0.4rem', fontSize: '0.875rem', borderLeft: '4px solid #6366f1' },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: '0.85rem', backgroundColor: '#fff', borderRadius: '12px', overflow: 'hidden', boxShadow: '0 1px 4px rgba(0,0,0,0.06)' },
  badge: { padding: '0.2rem 0.6rem', borderRadius: '9999px', color: '#fff', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.5px' },
  emptyState: { textAlign: 'center' as const, marginTop: '6rem', color: '#64748b' },
};

const modalStyles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(4px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  },
  modal: {
    backgroundColor: '#fff', borderRadius: '16px', padding: '2rem',
    width: '100%', maxWidth: '440px', boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
  },
  title: { margin: '0 0 1.5rem', fontSize: '1.25rem', fontWeight: 700, color: '#1e293b' },
  field: { marginBottom: '1.25rem' },
  label: { display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#475569', marginBottom: '0.4rem' },
  input: {
    width: '100%', padding: '0.6rem 0.75rem', border: '1px solid #e2e8f0',
    borderRadius: '8px', fontSize: '0.95rem', outline: 'none',
  },
  fileInfo: {
    padding: '0.5rem 0.75rem', backgroundColor: '#ecfdf5', border: '1px solid #a7f3d0',
    borderRadius: '6px', fontSize: '0.8rem', color: '#059669', marginTop: '0.4rem',
  },
  fileInput: {
    width: '100%', padding: '0.5rem', border: '2px dashed #e2e8f0',
    borderRadius: '8px', fontSize: '0.85rem', cursor: 'pointer', backgroundColor: '#f8fafc',
  },
  actions: { display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.5rem' },
  cancelBtn: {
    padding: '0.6rem 1.2rem', backgroundColor: '#f1f5f9', border: '1px solid #e2e8f0',
    borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 500, color: '#475569',
  },
  submitBtn: {
    padding: '0.6rem 1.5rem', background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
    color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer',
    fontSize: '0.85rem', fontWeight: 600, boxShadow: '0 2px 8px rgba(99,102,241,0.3)',
  },
};
