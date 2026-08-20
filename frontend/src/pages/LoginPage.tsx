/**
 * Login page with username/password form.
 * Redirects to Dashboard on success, supports redirect preservation (Req 6.8).
 */
import React, { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export function LoginPage() {
  const { login, error: authError } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirectTo = searchParams.get('redirect') || '/';

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const result = await login(username, password);
      if (result.must_reset_password) {
        navigate('/reset-password', { replace: true });
      } else {
        navigate(redirectTo, { replace: true });
      }
    } catch (err: any) {
      setError(err.message || 'Login failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>ReportPulse</h1>
        <h2 style={styles.subtitle}>Sign In</h2>

        {(error || authError) && (
          <div style={styles.error} role="alert">
            {error || authError}
          </div>
        )}

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label htmlFor="username" style={styles.label}>Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              style={styles.input}
              disabled={isSubmitting}
            />
          </div>

          <div style={styles.field}>
            <label htmlFor="password" style={styles.label}>Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              style={styles.input}
              disabled={isSubmitting}
            />
          </div>

          <button type="submit" style={styles.button} disabled={isSubmitting}>
            {isSubmitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p style={styles.registerLink}>
          Don't have an account? <Link to="/register">Register</Link>
        </p>
        <p style={styles.registerLink}>
          <Link to="/reset-password">Forgot password?</Link>
        </p>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    minHeight: '100vh', background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)', padding: '1rem',
  },
  card: {
    backgroundColor: '#fff', borderRadius: '16px', padding: '2.5rem',
    boxShadow: '0 20px 60px rgba(0,0,0,0.3)', width: '100%', maxWidth: '400px',
  },
  title: { margin: '0 0 0.25rem', fontSize: '1.75rem', textAlign: 'center' as const, background: 'linear-gradient(135deg, #6366f1, #06b6d4)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', fontWeight: 700 },
  subtitle: { margin: '0 0 1.5rem', fontSize: '1rem', textAlign: 'center' as const, color: '#64748b' },
  error: {
    backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px',
    padding: '0.75rem', marginBottom: '1rem', color: '#dc2626', fontSize: '0.875rem',
  },
  form: { display: 'flex', flexDirection: 'column' as const, gap: '1rem' },
  field: { display: 'flex', flexDirection: 'column' as const, gap: '0.25rem' },
  label: { fontSize: '0.875rem', fontWeight: 500, color: '#334155' },
  input: {
    padding: '0.6rem 0.75rem', border: '1px solid #e2e8f0', borderRadius: '8px',
    fontSize: '1rem', outline: 'none', transition: 'border-color 0.2s',
  },
  button: {
    padding: '0.75rem', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', color: '#fff', border: 'none',
    borderRadius: '8px', fontSize: '1rem', cursor: 'pointer', fontWeight: 600,
    marginTop: '0.5rem', boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
  },
  registerLink: { textAlign: 'center' as const, marginTop: '1rem', fontSize: '0.875rem', color: '#64748b' },
};
