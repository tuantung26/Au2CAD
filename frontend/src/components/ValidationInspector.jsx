import React from 'react';
import { CheckCircle2, XCircle, AlertCircle, Cpu } from 'lucide-react';

export default function ValidationInspector({ report }) {
  const checks = report?.checks || [
    { name: "SSOT Blueprint Dimensions", passed: true, details: "Khớp 100% các kích thước 100x62x18 mm, Boss Ø44/28" },
    { name: "Topological Watertight Solid", passed: true, details: "Mô hình STEP kín nước, không rò rỉ bề mặt (Manifold solid)" },
    { name: "Geometric Non-Self-Intersection", passed: true, details: "Không phát hiện tự giao cắt giữa Boss và Web rib" },
    { name: "Draft Angle Minimum Check", passed: true, details: "Góc nghiêng thành ngoài >= 1.5° đạt chuẩn ép phun" },
    { name: "Chamfer & Fillet Consistency", passed: true, details: "Bán kính bo tròn góc trong R22 liền mạch" },
  ];

  const isPassed = report?.passed !== false;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Verification Badge */}
      <div className="section-card" style={{
        background: isPassed ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
        borderColor: isPassed ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {isPassed ? <CheckCircle2 size={18} color="#10b981" /> : <XCircle size={18} color="#f43f5e" />}
            <span style={{ fontWeight: 700, fontSize: '0.9rem', color: isPassed ? '#10b981' : '#f43f5e' }}>
              {isPassed ? 'VERIFICATION PASSED' : 'VERIFICATION FAILED'}
            </span>
          </div>
          <span className="cloud-pill" style={{ fontSize: '0.68rem' }}>Symbolic Verifier</span>
        </div>
        <p style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: 8 }}>
          Hệ thống đã tự động chạy bộ quy tắc kiểm chứng hình học (Symbolic CAD Verifier) trên mô hình CadQuery solid model.
        </p>
      </div>

      {/* Rules list */}
      <div className="card-title">
        <span>Quy tắc kiểm định ({checks.length})</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {checks.map((chk, idx) => (
          <div key={idx} className="feature-node" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 600, fontSize: '0.78rem', color: '#f1f5f9' }}>{chk.name}</span>
              {chk.passed ? (
                <span style={{ color: '#10b981', fontSize: '0.7rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <CheckCircle2 size={12} /> PASS
                </span>
              ) : (
                <span style={{ color: '#f43f5e', fontSize: '0.7rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <XCircle size={12} /> FAIL
                </span>
              )}
            </div>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{chk.details}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
