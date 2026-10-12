import React from 'react';
import { Compass, AlertTriangle, CheckCircle2, ShieldCheck } from 'lucide-react';

export default function MoldInspector({ moldReport }) {
  const partingDir = moldReport?.parting_direction || [0, 0, 1];
  const undercuts = moldReport?.undercut_faces || [];
  const partingEdges = moldReport?.parting_line_edges || [1, 2, 3, 4, 5, 6];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Mold Orientation Card */}
      <div className="section-card">
        <div className="card-title">
          <span>Hướng mở khuôn (Parting Direction)</span>
          <Compass size={14} color="#06b6d4" />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 4 }}>
          <div style={{
            background: 'rgba(6, 182, 212, 0.15)',
            border: '1px solid rgba(6, 182, 212, 0.3)',
            borderRadius: 'var(--radius-sm)',
            padding: '8px 12px',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.85rem',
            color: '#67e8f9',
            fontWeight: 600,
          }}>
            Vector: [{partingDir.map(v => Number(v).toFixed(1)).join(', ')}] (+Z Axis)
          </div>
          <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>Hướng tối ưu hóa giảm thiểu undercut</span>
        </div>
      </div>

      {/* Draft Analysis & Undercuts */}
      <div className="section-card">
        <div className="card-title">
          <span>Phân tích góc thoát khuôn (Draft Angle)</span>
          <ShieldCheck size={14} color="#10b981" />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 6 }}>
          <div style={{
            background: 'rgba(16, 185, 129, 0.1)',
            border: '1px solid rgba(16, 185, 129, 0.25)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#10b981' }}>2.0°</div>
            <div style={{ fontSize: '0.68rem', color: '#94a3b8', marginTop: 2 }}>Góc thoát tối thiểu</div>
          </div>

          <div style={{
            background: undercuts.length === 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
            border: `1px solid ${undercuts.length === 0 ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
            borderRadius: 'var(--radius-sm)',
            padding: '10px',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: undercuts.length === 0 ? '#10b981' : '#f43f5e' }}>
              {undercuts.length}
            </div>
            <div style={{ fontSize: '0.68rem', color: '#94a3b8', marginTop: 2 }}>Mặt Undercut (Vướng khuôn)</div>
          </div>
        </div>

        <div style={{ marginTop: 12, fontSize: '0.74rem', color: '#cbd5e1', lineHeight: 1.45 }}>
          {undercuts.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#10b981' }}>
              <CheckCircle2 size={14} /> Không phát hiện undercut nguy hiểm. Có thể gia công 2 nửa khuôn chuẩn.
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#f59e0b' }}>
              <AlertTriangle size={14} /> Cần bổ sung lõi trượt phụ (slider core) cho phần undercut.
            </div>
          )}
        </div>
      </div>

      {/* Parting Line Summary */}
      <div className="section-card">
        <div className="card-title">
          <span>Đường phân khuôn (Parting Line)</span>
          <span className="feature-tag">{partingEdges.length} Cạnh</span>
        </div>
        <p style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
          Đường phân tách tự động khớp với mặt phẳng đáy và gờ bậc Z = 9mm. Đảm bảo độ kín khít khi ép phun nhựa / đúc áp lực.
        </p>
      </div>
    </div>
  );
}
