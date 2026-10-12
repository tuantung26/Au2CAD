import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, Code2, RefreshCw, CheckCircle, AlertCircle } from 'lucide-react';

/**
 * AgentChat — Real CAD Modification Agent
 *
 * The agent operates in two modes based on user intent:
 *  1. Q&A: General questions about the model -> calls /api/agent/chat
 *  2. MODIFY: Requests to change dimensions/features -> calls /api/agent/modify
 *     which: reads parametric_model.py -> LLM edits it -> CadQuery rebuild -> new STL/STEP
 *     -> onModelRefresh() is called to reload Three.js viewer
 */
export default function AgentChat({ onModelRefresh }) {
  const [messages, setMessages] = useState([
    {
      sender: 'agent',
      type: 'text',
      text:
        'Xin chao! Toi la Au2CAD Engineering Agent.\n\n' +
        'Toi co the:\n' +
        '• Tra loi cau hoi ve mo hinh, kich thuoc, khuon mau\n' +
        '• Sua doi mo hinh 3D theo yeu cau (thay doi kich thuoc, them/bot feature)\n\n' +
        'Vi du: "Tang chieu cao Boss len 70mm" hoac "Doi do day Base Plate thanh 25mm"',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [rebuildStatus, setRebuildStatus] = useState(null); // null | 'rebuilding' | 'done' | 'error'
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Heuristic: detect if user wants to modify the model
  const isModifyRequest = (text) => {
    const keywords = [
      'tang', 'giam', 'thay doi', 'doi', 'sua', 'chinh', 'update', 'modify',
      'them', 'bo', 'xoa', 'remove', 'add', 'change', 'set', 'resize',
      'chieu cao', 'chieu rong', 'do day', 'ban kinh', 'duong kinh', 'mm',
      'boss', 'base plate', 'bore', 'cutout', 'rib', 'web', 'slot',
    ];
    const lower = text.toLowerCase();
    return keywords.some((k) => lower.includes(k));
  };

  const appendMessage = (msg) => setMessages((prev) => [...prev, msg]);

  const handleSend = async (textToSend) => {
    const query = textToSend !== undefined ? textToSend : input;
    if (!query.trim() || loading) return;

    appendMessage({ sender: 'user', type: 'text', text: query });
    setInput('');
    setLoading(true);
    setRebuildStatus(null);

    const willModify = isModifyRequest(query);

    try {
      if (willModify) {
        // -- MODIFY PATH -- Agent rewrites CAD script and rebuilds model --
        appendMessage({
          sender: 'agent',
          type: 'status',
          text: 'Dang phan tich yeu cau va chinh sua code CadQuery...',
        });

        const res = await fetch('/api/agent/modify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ instruction: query }),
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({ detail: 'Unknown error' }));
          throw new Error(errData.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();

        // Show what the agent changed
        appendMessage({
          sender: 'agent',
          type: 'code',
          title: 'Code CadQuery da duoc cap nhat:',
          text: data.diff_summary || data.modified_lines || '(Khong co thay doi duoc ghi lai)',
          explanation: data.explanation || '',
        });

        // Trigger rebuild
        setRebuildStatus('rebuilding');
        appendMessage({
          sender: 'agent',
          type: 'status',
          text: 'Dang build lai mo hinh 3D tu code moi...',
        });

        const buildRes = await fetch('/api/agent/rebuild', { method: 'POST' });
        if (!buildRes.ok) {
          throw new Error('Build that bai. Kiem tra log CadQuery.');
        }
        const buildData = await buildRes.json();

        setRebuildStatus('done');
        appendMessage({
          sender: 'agent',
          type: 'success',
          text: `Mo hinh 3D da duoc cap nhat thanh cong!\n${buildData.message || ''}`,
        });

        // Reload Three.js viewer with new STL
        if (onModelRefresh) onModelRefresh();
      } else {
        // -- Q&A PATH -- Simple chat with engineering context --
        const res = await fetch('/api/agent/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: query }),
        });
        const data = await res.json();
        appendMessage({
          sender: 'agent',
          type: 'text',
          text: data.reply || 'Da phan tich yeu cau thanh cong.',
        });
      }
    } catch (err) {
      setRebuildStatus('error');
      appendMessage({
        sender: 'agent',
        type: 'error',
        text: `Loi: ${err.message}`,
      });
    } finally {
      setLoading(false);
    }
  };

  const quickPrompts = [
    { label: 'Tang chieu cao Boss len 70mm', modify: true },
    { label: 'Doi do day Base Plate thanh 25mm', modify: true },
    { label: 'Goc thoat khuon co dat 2 do khong?', modify: false },
    { label: 'Giai thich ket cau CAD-IR hien tai', modify: false },
  ];

  const renderMessage = (m, idx) => {
    if (m.type === 'code') {
      return (
        <div key={idx} className="chat-bubble agent" style={{ maxWidth: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6, opacity: 0.8 }}>
            <Code2 size={12} color="#22d3ee" />
            <span style={{ fontSize: '0.68rem', fontWeight: 700 }}>Au2CAD Agent - Code Edit</span>
          </div>
          {m.explanation && (
            <p style={{ fontSize: '0.8rem', marginBottom: 8, color: '#cbd5e1', lineHeight: 1.5 }}>
              {m.explanation}
            </p>
          )}
          <div style={{ fontSize: '0.7rem', color: '#64748b', marginBottom: 4, fontWeight: 600 }}>
            {m.title}
          </div>
          <pre
            style={{
              background: '#020408',
              border: '1px solid rgba(6,182,212,0.2)',
              borderRadius: 6,
              padding: '10px 12px',
              fontSize: '0.72rem',
              fontFamily: 'JetBrains Mono, monospace',
              color: '#67e8f9',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              maxHeight: 200,
              overflowY: 'auto',
            }}
          >
            {m.text}
          </pre>
        </div>
      );
    }

    if (m.type === 'status') {
      return (
        <div key={idx} className="chat-bubble agent" style={{ opacity: 0.75 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <RefreshCw size={12} style={{ color: '#06b6d4' }} className="spin-icon" />
            <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontStyle: 'italic' }}>{m.text}</span>
          </div>
        </div>
      );
    }

    if (m.type === 'success') {
      return (
        <div
          key={idx}
          className="chat-bubble agent"
          style={{ borderColor: 'rgba(16,185,129,0.4)', background: 'rgba(16,185,129,0.08)' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <CheckCircle size={12} color="#10b981" />
            <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#10b981' }}>Build Thanh Cong</span>
          </div>
          <div style={{ fontSize: '0.82rem', whiteSpace: 'pre-line' }}>{m.text}</div>
        </div>
      );
    }

    if (m.type === 'error') {
      return (
        <div
          key={idx}
          className="chat-bubble agent"
          style={{ borderColor: 'rgba(244,63,94,0.4)', background: 'rgba(244,63,94,0.08)' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <AlertCircle size={12} color="#f43f5e" />
            <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#f43f5e' }}>Loi</span>
          </div>
          <div style={{ fontSize: '0.82rem' }}>{m.text}</div>
        </div>
      );
    }

    // Default: text message
    return (
      <div key={idx} className={`chat-bubble ${m.sender}`}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, opacity: 0.8 }}>
          {m.sender === 'agent' ? <Bot size={12} color="#22d3ee" /> : <User size={12} />}
          <span style={{ fontSize: '0.68rem', fontWeight: 700 }}>
            {m.sender === 'agent' ? 'Au2CAD Engineering Agent' : 'Engineer'}
          </span>
        </div>
        <div style={{ fontSize: '0.82rem', whiteSpace: 'pre-line', lineHeight: 1.5 }}>{m.text}</div>
      </div>
    );
  };

  return (
    <div className="chat-container">
      {/* Quick suggestion chips */}
      <div style={{ marginBottom: 10 }}>
        <span style={{ fontSize: '0.68rem', color: '#64748b', fontWeight: 600, display: 'block', marginBottom: 6 }}>
          GOI Y NHANH:
        </span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
          {quickPrompts.map((p, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(p.label)}
              disabled={loading}
              style={{
                fontSize: '0.71rem',
                background: p.modify ? 'rgba(6,182,212,0.08)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${p.modify ? 'rgba(6,182,212,0.3)' : 'rgba(255,255,255,0.08)'}`,
                color: p.modify ? '#67e8f9' : '#94a3b8',
                borderRadius: 'var(--radius-sm)',
                padding: '4px 8px',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.5 : 1,
                textAlign: 'left',
                transition: 'all 0.15s',
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.map((m, idx) => renderMessage(m, idx))}
        {loading && (
          <div className="chat-bubble agent" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={14} style={{ color: '#06b6d4' }} className="pulse-dot" />
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              {rebuildStatus === 'rebuilding'
                ? 'Dang build lai mo hinh 3D...'
                : 'Agent dang suy luan va xu ly...'}
            </span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="chat-input-row">
        <input
          type="text"
          className="chat-input"
          placeholder="Hoi ve mo hinh hoac yeu cau sua doi kich thuoc..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !loading && handleSend()}
          disabled={loading}
        />
        <button
          className="btn btn-primary"
          onClick={() => handleSend()}
          disabled={loading || !input.trim()}
          style={{ padding: '8px 12px', flexShrink: 0 }}
        >
          {loading
            ? <RefreshCw size={14} className="spin-icon" />
            : <Send size={14} />}
        </button>
      </div>

      <div style={{ marginTop: 8, fontSize: '0.68rem', color: '#475569', textAlign: 'center' }}>
        Yeu cau sua doi kich thuoc se tu dong rebuild mo hinh 3D
      </div>

      <style>{`
        .spin-icon { animation: agentSpin 1s linear infinite; }
        @keyframes agentSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
