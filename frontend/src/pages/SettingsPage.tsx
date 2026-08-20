/**
 * Settings page: Phone number management UI.
 * Add, verify, and remove WhatsApp notification numbers (Req 8.1-8.7).
 */
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  getPhoneNumbers,
  addPhoneNumber,
  verifyPhoneNumber,
  removePhoneNumber,
  type PhoneNumber,
} from '../services/api';
import { useAuth } from '../hooks/useAuth';

export function SettingsPage() {
  const { user, logout } = useAuth();
  const [phoneNumbers, setPhoneNumbers] = useState<PhoneNumber[]>([]);
  const [newNumber, setNewNumber] = useState('');
  const [verifyNumber, setVerifyNumber] = useState('');
  const [verifyCode, setVerifyCode] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadPhoneNumbers();
  }, []);

  const loadPhoneNumbers = async () => {
    try {
      const numbers = await getPhoneNumbers();
      setPhoneNumbers(numbers);
    } catch {
      setError('Failed to load phone numbers.');
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setIsAdding(true);

    try {
      const result = await addPhoneNumber(newNumber);
      setPhoneNumbers((prev) => [...prev, result]);
      setNewNumber('');
      setSuccess('Phone number added. Check your WhatsApp for the verification code.');
      setVerifyNumber(result.number);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add phone number.');
    } finally {
      setIsAdding(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setIsVerifying(true);

    try {
      const result = await verifyPhoneNumber(verifyNumber, verifyCode);
      setPhoneNumbers((prev) =>
        prev.map((p) => (p.number === result.number ? result : p))
      );
      setVerifyCode('');
      setVerifyNumber('');
      setSuccess('Phone number verified successfully.');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Verification failed.');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleRemove = async (id: string) => {
    if (!confirm('Remove this phone number? You will no longer receive notifications on it.')) return;
    setError(null);
    try {
      await removePhoneNumber(id);
      setPhoneNumbers((prev) => prev.filter((p) => p.id !== id));
      setSuccess('Phone number removed.');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to remove phone number.');
    }
  };

  const pendingNumbers = phoneNumbers.filter((p) => p.status === 'pending_verification');

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.headerTitle}>Settings</h1>
        <div style={styles.headerRight}>
          <Link to="/" style={styles.backLink}>Back to Dashboard</Link>
          <span style={styles.username}>{user?.username}</span>
          <button onClick={logout} style={styles.logoutBtn}>Logout</button>
        </div>
      </header>

      <div style={styles.content}>
        <h2>WhatsApp Notification Numbers</h2>
        <p style={styles.description}>
          Add phone numbers to receive WhatsApp alerts when deviations are detected.
          Numbers must be in E.164 format (e.g., +14155552671). Maximum 10 numbers.
        </p>

        {error && <div style={styles.error} role="alert">{error}</div>}
        {success && <div style={styles.success} role="status">{success}</div>}

        {/* Current numbers */}
        <div style={styles.section}>
          <h3>Your Numbers ({phoneNumbers.length}/10)</h3>
          {phoneNumbers.length === 0 ? (
            <p style={{ color: '#666', fontSize: '0.875rem' }}>No phone numbers configured yet.</p>
          ) : (
            <ul style={styles.numberList}>
              {phoneNumbers.map((pn) => (
                <li key={pn.id} style={styles.numberItem}>
                  <div>
                    <span style={styles.numberText}>{pn.number}</span>
                    <span style={{
                      ...styles.statusBadge,
                      backgroundColor: pn.status === 'verified' ? '#dcfce7' : '#fef9c3',
                      color: pn.status === 'verified' ? '#16a34a' : '#a16207',
                    }}>
                      {pn.status === 'verified' ? 'Verified' : 'Pending'}
                    </span>
                  </div>
                  <button onClick={() => handleRemove(pn.id)} style={styles.removeBtn}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Add new number */}
        <div style={styles.section}>
          <h3>Add New Number</h3>
          <form onSubmit={handleAdd} style={styles.form}>
            <input
              type="tel"
              value={newNumber}
              onChange={(e) => setNewNumber(e.target.value)}
              placeholder="+14155552671"
              required
              style={styles.input}
              disabled={isAdding}
            />
            <button type="submit" style={styles.addBtn} disabled={isAdding || phoneNumbers.length >= 10}>
              {isAdding ? 'Adding...' : 'Add Number'}
            </button>
          </form>
        </div>

        {/* Verify pending numbers */}
        {pendingNumbers.length > 0 && (
          <div style={styles.section}>
            <h3>Verify a Number</h3>
            <form onSubmit={handleVerify} style={styles.form}>
              <select
                value={verifyNumber}
                onChange={(e) => setVerifyNumber(e.target.value)}
                style={styles.input}
                required
              >
                <option value="">Select number to verify</option>
                {pendingNumbers.map((pn) => (
                  <option key={pn.id} value={pn.number}>{pn.number}</option>
                ))}
              </select>
              <input
                type="text"
                value={verifyCode}
                onChange={(e) => setVerifyCode(e.target.value)}
                placeholder="6-digit code"
                maxLength={6}
                required
                style={{ ...styles.input, width: '120px' }}
                disabled={isVerifying}
              />
              <button type="submit" style={styles.addBtn} disabled={isVerifying || !verifyNumber}>
                {isVerifying ? 'Verifying...' : 'Verify'}
              </button>
            </form>
          </div>
        )}
        {/* Test WhatsApp */}
        {phoneNumbers.some((p) => p.status === 'verified') && (
          <div style={styles.section}>
            <h3>Test WhatsApp Notification</h3>
            <p style={{ color: '#666', fontSize: '0.875rem', marginBottom: '0.75rem' }}>
              Send a test deviation alert to your verified numbers.
            </p>
            <button
              onClick={async () => {
                setError(null);
                setSuccess(null);
                try {
                  const { data } = await (await import('../services/api')).default.post('/upload/test-whatsapp');
                  if (data.status === 'sent') {
                    setSuccess('Test WhatsApp message sent! Check your phone.');
                  } else {
                    setError(data.message || 'Failed to send test message.');
                  }
                } catch (err: any) {
                  setError(err.response?.data?.detail || 'Failed to send test message.');
                }
              }}
              style={styles.addBtn}
            >
              Send Test Message
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', backgroundColor: '#f9fafb' },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '1rem 2rem', backgroundColor: '#fff', borderBottom: '1px solid #e5e7eb',
  },
  headerTitle: { margin: 0, fontSize: '1.25rem' },
  headerRight: { display: 'flex', alignItems: 'center', gap: '1rem' },
  backLink: { color: '#2563eb', textDecoration: 'none', fontSize: '0.875rem' },
  username: { fontSize: '0.875rem', color: '#666' },
  logoutBtn: {
    padding: '0.4rem 0.75rem', backgroundColor: '#f3f4f6', border: '1px solid #d1d5db',
    borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem',
  },
  content: { maxWidth: '700px', margin: '0 auto', padding: '2rem' },
  description: { color: '#666', fontSize: '0.875rem', marginBottom: '1.5rem' },
  error: {
    backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '4px',
    padding: '0.75rem', marginBottom: '1rem', color: '#dc2626', fontSize: '0.875rem',
  },
  success: {
    backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '4px',
    padding: '0.75rem', marginBottom: '1rem', color: '#16a34a', fontSize: '0.875rem',
  },
  section: { marginBottom: '2rem' },
  numberList: { listStyle: 'none', padding: 0, margin: 0 },
  numberItem: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '0.75rem', borderBottom: '1px solid #e5e7eb',
  },
  numberText: { fontFamily: 'monospace', marginRight: '0.75rem' },
  statusBadge: {
    padding: '0.15rem 0.5rem', borderRadius: '9999px', fontSize: '0.75rem', fontWeight: 500,
  },
  removeBtn: {
    padding: '0.3rem 0.6rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca',
    borderRadius: '4px', color: '#dc2626', cursor: 'pointer', fontSize: '0.75rem',
  },
  form: { display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' as const },
  input: {
    padding: '0.5rem 0.75rem', border: '1px solid #d1d5db', borderRadius: '4px',
    fontSize: '0.9rem', outline: 'none',
  },
  addBtn: {
    padding: '0.5rem 1rem', backgroundColor: '#2563eb', color: '#fff', border: 'none',
    borderRadius: '4px', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500,
  },
};
