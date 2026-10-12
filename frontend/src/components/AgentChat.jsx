import React, { useState } from 'react';
import { Send, Bot, User, Sparkles } from 'lucide-react';

export default function AgentChat({ onSendMessage }) {
  const [messages, setMessages] = useState([
    {
      sender: 'agent',
      text: 'Xin chào! Tôi là Au2CAD Senior Engineering Agent. Tôi có thể hỗ trợ bạn kiểm tra dung sai, phân tích góc thoát khuôn, giải thích CAD-IR hoặc cập nhật tham số mô hình 3D.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = async (textToSend) => {
    const query = textToSend || input;
    if (!query.trim() || loading) return;

    const userMsg = { sender: 'user', text: query };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: query }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { sender: 'agent', text: data.reply || 'Đã phân tích yêu cầu thành công.' },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { sender: 'agent', text: 'Không thể kết nối đến AI Agent backend. Vui lòng kiểm tra API.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const quickPrompts = [
    'Giải thích kết cấu Base Plate và Boss Ø44',
    'Góc thoát khuôn có đạt chuẩn 2 độ không?',
    'Có undercut nào cần dùng slider không?',
  ];

  return (
    <div className="chat-container">
      {/* Quick suggestions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
        <span style={{ fontSize: '0.7rem', color: '#64748b', fontWeight: 600 }}>GỢI Ý KỸ THUẬT:</span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {quickPrompts.map((p, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(p)}
              style={{
                fontSize: '0.72rem',
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid var(--border-subtle)',
                color: '#94a3b8',
                borderRadius: 'var(--radius-sm)',
                padding: '4px 8px',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              ⚡ {p}
            </button>
          ))}
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.map((m, idx) => (
          <div key={idx} className={`chat-bubble ${m.sender}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, opacity: 0.8 }}>
              {m.sender === 'agent' ? <Bot size={12} color="#22d3ee" /> : <User size={12} />}
              <span style={{ fontSize: '0.68rem', fontWeight: 700 }}>
                {m.sender === 'agent' ? 'Au2CAD Engineering Agent' : 'Engineer'}
              </span>
            </div>
            <div>{m.text}</div>
          </div>
        ))}
        {loading && (
          <div className="chat-bubble agent" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={14} className="pulse-dot" />
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Agent đang suy luận kỹ thuật...</span>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="chat-input-row">
        <input
          type="text"
          className="chat-input"
          placeholder="Hỏi Agent về kích thước, quy tắc khuôn..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
        />
        <button className="btn btn-primary" onClick={() => handleSend()} disabled={loading} style={{ padding: '8px 12px' }}>
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
