/**
 * Floating QBot chat panel for natural language queries about data.
 */
import React, { useState, useRef, useEffect } from 'react';
import api from '../services/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export function ChatPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [isFullPage, setIsFullPage] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const question = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setIsLoading(true);

    try {
      const { data } = await api.post('/ai/chat', { question });
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer }]);
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Sorry, failed to get a response.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {/* Floating QBot Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          width: '64px',
          height: '64px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
          color: '#fff',
          border: 'none',
          cursor: 'pointer',
          boxShadow: '0 4px 20px rgba(99,102,241,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          transition: 'transform 0.2s, box-shadow 0.2s',
          transform: isOpen ? 'scale(0.9)' : 'scale(1)',
          padding: 0,
        }}
        title="Ask QBot about your data"
      >
        {isOpen ? (
          <span style={{ fontSize: '1.5rem' }}>✕</span>
        ) : (
          <svg width="36" height="36" viewBox="0 0 64 64" fill="none">
            {/* Bot head */}
            <rect x="14" y="20" width="36" height="28" rx="8" fill="#fff"/>
            {/* Antenna */}
            <line x1="32" y1="12" x2="32" y2="20" stroke="#fff" strokeWidth="3" strokeLinecap="round"/>
            <circle cx="32" cy="10" r="4" fill="#06b6d4"/>
            {/* Eyes */}
            <circle cx="24" cy="32" r="4" fill="#6366f1"/>
            <circle cx="40" cy="32" r="4" fill="#6366f1"/>
            {/* Smile */}
            <path d="M24 40 Q32 46 40 40" stroke="#6366f1" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
            {/* Ears */}
            <rect x="8" y="28" width="6" height="12" rx="3" fill="#fff" opacity="0.8"/>
            <rect x="50" y="28" width="6" height="12" rx="3" fill="#fff" opacity="0.8"/>
          </svg>
        )}
      </button>

      {/* Chat Window */}
      {isOpen && (
        <div style={{
          position: 'fixed',
          bottom: isFullPage ? '0' : '96px',
          right: isFullPage ? '0' : '24px',
          width: isFullPage ? '100vw' : '380px',
          height: isFullPage ? '100vh' : '500px',
          backgroundColor: '#fff',
          borderRadius: isFullPage ? '0' : '16px',
          boxShadow: isFullPage ? 'none' : '0 8px 40px rgba(0,0,0,0.2)',
          display: 'flex',
          flexDirection: 'column',
          zIndex: 999,
          overflow: 'hidden',
          transition: 'all 0.3s ease',
        }}>
          <div style={styles.header}>
            <div>
              <span style={styles.headerTitle}>QBot</span>
              <span style={styles.headerSub}>Ask about your data</span>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {/* Minimize */}
              <button
                onClick={() => setIsOpen(false)}
                style={styles.headerBtn}
                title="Minimize"
              >
                ─
              </button>
              {/* Fullscreen toggle */}
              <button
                onClick={() => setIsFullPage(!isFullPage)}
                style={styles.headerBtn}
                title={isFullPage ? 'Exit fullscreen' : 'Fullscreen'}
              >
                {isFullPage ? '⊡' : '⊞'}
              </button>
              {/* Close */}
              <button
                onClick={() => { setIsOpen(false); setIsFullPage(false); }}
                style={styles.headerBtn}
                title="Close"
              >
                ✕
              </button>
            </div>
          </div>

          <div style={styles.messages}>
            {messages.length === 0 && (
              <div style={styles.welcome}>
                <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem' }}>
                  <svg width="28" height="28" viewBox="0 0 64 64" fill="none">
                    <rect x="14" y="20" width="36" height="28" rx="8" fill="#fff"/>
                    <line x1="32" y1="12" x2="32" y2="20" stroke="#fff" strokeWidth="3" strokeLinecap="round"/>
                    <circle cx="32" cy="10" r="4" fill="#06b6d4"/>
                    <circle cx="24" cy="32" r="4" fill="#6366f1"/>
                    <circle cx="40" cy="32" r="4" fill="#6366f1"/>
                    <path d="M24 40 Q32 46 40 40" stroke="#6366f1" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
                  </svg>
                </div>
                <p style={{ margin: '0 0 0.25rem', fontWeight: 700, fontSize: '1.1rem', color: '#1e293b' }}>Hi! I'm QBot</p>
                <p style={{ margin: '0 0 1.25rem', fontSize: '0.85rem', color: '#64748b' }}>Your AI assistant for report analysis</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <button onClick={() => { setInput('What spiked today?'); }} style={styles.suggestionBtn}>📈 What spiked today?</button>
                  <button onClick={() => { setInput('Compare this week to last month'); }} style={styles.suggestionBtn}>📊 Compare this week to last month</button>
                  <button onClick={() => { setInput('Which metrics have deviations?'); }} style={styles.suggestionBtn}>⚠️ Which metrics have deviations?</button>
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} style={msg.role === 'user' ? styles.userBubble : styles.botBubble}>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: '0.85rem' }}>{msg.content}</div>
              </div>
            ))}
            {isLoading && (
              <div style={styles.botBubble}>
                <em style={{ color: '#94a3b8' }}>Thinking...</em>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSend} style={styles.inputRow}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a question..."
              style={styles.input}
              disabled={isLoading}
              autoFocus
            />
            <button type="submit" style={styles.sendBtn} disabled={isLoading || !input.trim()}>
              ➤
            </button>
          </form>
        </div>
      )}
    </>
  );
}

const styles: Record<string, React.CSSProperties> = {
  header: {
    background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
    padding: '0.75rem 1.25rem',
    color: '#fff',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: { fontSize: '1.1rem', fontWeight: 700 },
  headerSub: { fontSize: '0.75rem', opacity: 0.8, marginLeft: '0.5rem' },
  headerBtn: {
    width: '28px',
    height: '28px',
    borderRadius: '6px',
    backgroundColor: 'rgba(255,255,255,0.2)',
    border: 'none',
    color: '#fff',
    cursor: 'pointer',
    fontSize: '0.85rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 700,
  },
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: '1rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  welcome: {
    textAlign: 'center',
    padding: '2rem 1rem',
    color: '#475569',
  },
  suggestionBtn: {
    padding: '0.6rem 1rem',
    backgroundColor: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    cursor: 'pointer',
    fontSize: '0.8rem',
    color: '#334155',
    textAlign: 'left' as const,
    transition: 'background-color 0.2s, border-color 0.2s',
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: '#6366f1',
    color: '#fff',
    padding: '0.6rem 1rem',
    borderRadius: '12px 12px 2px 12px',
    maxWidth: '80%',
  },
  botBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#f1f5f9',
    color: '#334155',
    padding: '0.6rem 1rem',
    borderRadius: '12px 12px 12px 2px',
    maxWidth: '85%',
  },
  inputRow: {
    display: 'flex',
    gap: '0.5rem',
    padding: '0.75rem',
    borderTop: '1px solid #e2e8f0',
    backgroundColor: '#f8fafc',
  },
  input: {
    flex: 1,
    padding: '0.6rem 0.75rem',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    fontSize: '0.9rem',
    outline: 'none',
  },
  sendBtn: {
    width: '38px',
    height: '38px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
    color: '#fff',
    border: 'none',
    cursor: 'pointer',
    fontSize: '1rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
};
