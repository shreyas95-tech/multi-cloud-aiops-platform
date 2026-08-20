/**
 * Registration page for new user accounts.
 */
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { register } from '../services/api';

export function RegisterPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors([]);
    setIsSubmitting(true);

    try {
      await register(username, email, password);
      navigate('/login', { replace: true });
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setErrors(detail);
      } else if (typeof detail === 'string') {
        setErrors([detail]);
      } else {
        setErrors(['Registration failed. Please try again.']);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>ReportPulse</h1>

        {errors.length > 0 && (
          <div style={styles.error} role="alert">
            {errors.map((err, i) => <p key={i} style={{ margin: '0.25rem 0' }}>{err}</p>)}
          </div>
        )}

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label htmlFor="username" style={styles.label}>Username</label>
            <input
              id="username" type="text" value={username}
              onChange={(e) => setUsername(e.target.value)}
              required minLength={3} maxLength={150}
              style={styles.input} disabled={isSubmitting}
            />
          </div>

          <div style={styles.field}>
            <label htmlFor="email" style={styles.label}>Email</label>
            <input
              id="email" type="email" value={email}
              onChange={(e) => setEmail(e.target.value)}
              required style={styles.input} disabled={isSubmitting}
            />
          </div>

          <div style={styles.field}>
            <label htmlFor="password" style={styles.label}>Password</label>
            <input
              id="password" type="password" value={password}
              onChange={(e) => setPassword(e.target.value)}
              required minLength={8} maxLength={128}
              style={styles.input} disabled={isSubmitting}
            />
            <small style={{ color: '#666' }}>
              8-128 chars, uppercase, lowercase, digit, and special character required.
            </small>
          </div>

          <button type="submit" style={styles.button} disabled={isSubmitting}>
            {isSubmitting ? 'Creating account...' : 'Register'}
          </button>
        </form>

        <p style={styles.loginLink}>
          Already have an account? <Link to="/login">Sign In</Link>
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
  title: { margin: '0 0 1.5rem', fontSize: '1.75rem', textAlign: 'center' as const, background: 'linear-gradient(135deg, #6366f1, #06b6d4)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', fontWeight: 700 },
  error: {
    backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px',
    padding: '0.75rem', marginBottom: '1rem', color: '#dc2626', fontSize: '0.875rem',
  },
  form: { display: 'flex', flexDirection: 'column' as const, gap: '1rem' },
  field: { display: 'flex', flexDirection: 'column' as const, gap: '0.25rem' },
  label: { fontSize: '0.875rem', fontWeight: 500, color: '#334155' },
  input: {
    padding: '0.6rem 0.75rem', border: '1px solid #e2e8f0', borderRadius: '8px',
    fontSize: '1rem', outline: 'none',
  },
  button: {
    padding: '0.75rem', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', color: '#fff', border: 'none',
    borderRadius: '8px', fontSize: '1rem', cursor: 'pointer', fontWeight: 600,
    marginTop: '0.5rem', boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
  },
  loginLink: { textAlign: 'center' as const, marginTop: '1rem', fontSize: '0.875rem', color: '#64748b' },
};
