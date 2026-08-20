/**
 * Password reset page - reset password using email address.
 */
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';

export function ResetPasswordPage() {
  const [email, setEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await api.post('/auth/reset-password', { email, new_password: newPassword });
      setSuccess(true);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.join(' '));
      } else {
        setError(detail || 'Password reset failed.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (success) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <h1 style={styles.title}>Password Reset</h1>
          <div style={styles.success}>
            Password reset successful! You can now log in with your new password.
          </div>
          <Link to="/login" style={styles.link}>Go to Login</Link>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Reset Password</h1>

        {error && <div style={styles.error} role="alert">{error}</div>}

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label htmlFor="email" style={styles.label}>Email address</label>
            <input
              id="email" type="email" value={email}
              onChange={(e) => setEmail(e.target.value)}
              required style={styles.input} disabled={isSubmitting}
              placeholder="your@email.com"
            />
          </div>

          <div style={styles.field}>
            <label htmlFor="newPassword" style={styles.label}>New Password</label>
            <input
              id="newPassword" type="password" value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required minLength={8} maxLength={128}
              style={styles.input} disabled={isSubmitting}
            />
            <small style={{ color: '#666' }}>
              8-128 chars, uppercase, lowercase, digit, and special character required.
            </small>
          </div>

          <button type="submit" style={styles.button} disabled={isSubmitting}>
            {isSubmitting ? 'Resetting...' : 'Reset Password'}
          </button>
        </form>

        <p style={styles.backLink}>
          <Link to="/login">Back to Login</Link>
        </p>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    minHeight: '100vh', backgroundColor: '#f5f5f5', padding: '1rem',
  },
  card: {
    backgroundColor: '#fff', borderRadius: '8px', padding: '2rem',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)', width: '100%', maxWidth: '400px',
  },
  title: { margin: '0 0 1.5rem', fontSize: '1.5rem', textAlign: 'center' as const },
  error: {
    backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '4px',
    padding: '0.75rem', marginBottom: '1rem', color: '#dc2626', fontSize: '0.875rem',
  },
  success: {
    backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '4px',
    padding: '0.75rem', marginBottom: '1rem', color: '#16a34a', fontSize: '0.875rem',
  },
  form: { display: 'flex', flexDirection: 'column' as const, gap: '1rem' },
  field: { display: 'flex', flexDirection: 'column' as const, gap: '0.25rem' },
  label: { fontSize: '0.875rem', fontWeight: 500 },
  input: {
    padding: '0.5rem 0.75rem', border: '1px solid #d1d5db', borderRadius: '4px',
    fontSize: '1rem', outline: 'none',
  },
  button: {
    padding: '0.75rem', backgroundColor: '#2563eb', color: '#fff', border: 'none',
    borderRadius: '4px', fontSize: '1rem', cursor: 'pointer', fontWeight: 500,
    marginTop: '0.5rem',
  },
  link: { display: 'block', textAlign: 'center' as const, marginTop: '1rem' },
  backLink: { textAlign: 'center' as const, marginTop: '1rem', fontSize: '0.875rem' },
};
