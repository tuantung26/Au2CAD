import React from 'react';
import { Box, Hash, Lock, CheckCircle2 } from 'lucide-react';

export default function CADIRViewer({ cadIR, structuredDims }) {
  const features = cadIR?.features || [
    {
      id: "feat_base_plate_extrude",
      type: "EXTRUDE",
      profile: "rectangle",
      depth: 18.0,
      parameters: [
        { name: "length", value: 100.0, unit: "mm" },
        { name: "width", value: 62.0, unit: "mm" },
        { name: "thickness", value: 18.0, unit: "mm" },
      ]
    },
    {
      id: "feat_boss_cylinder",
      type: "EXTRUDE",
      profile: "cylinder",
      parameters: [
        { name: "outer_diameter", value: 44.0, unit: "mm" },
        { name: "inner_bore_diameter", value: 28.0, unit: "mm" },
        { name: "center_height_Z", value: 50.0, unit: "mm" },
      ]
    },
    {
      id: "feat_front_cutout",
      type: "CUT",
      profile: "semicircle",
      parameters: [
        { name: "radius", value: 22.0, unit: "mm" },
        { name: "depth", value: 18.0, unit: "mm" },
      ]
    },
    {
      id: "feat_transition_web",
      type: "EXTRUDE",
      profile: "triangle_rib",
      parameters: [
        { name: "thickness", value: 9.0, unit: "mm" },
        { name: "angle", value: 45.0, unit: "deg" },
      ]
    }
  ];

  return (
    <div className="feature-list">
      <div className="section-card" style={{ marginBottom: 12 }}>
        <div className="card-title">
          <span>SSOT Dimension Lock</span>
          <Lock size={14} color="#06b6d4" />
        </div>
        <p style={{ fontSize: '0.74rem', color: '#94a3b8', lineHeight: 1.4 }}>
          Tất cả kích thước hình học được khóa nghiêm ngặt theo Bản vẽ kỹ thuật (Single Source of Truth).
        </p>
        <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span className="feature-tag">100 × 62 × 18 mm</span>
          <span className="feature-tag">Boss Ø44 / Ø28</span>
          <span className="feature-tag">Cutout R22</span>
          <span className="feature-tag">Web 9mm</span>
        </div>
      </div>

      <div className="card-title">
        <span>Cây tính năng (CAD-IR Tree)</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>{features.length} Features</span>
      </div>

      {features.map((feat, idx) => (
        <div key={feat.id || idx} className="feature-node">
          <div className="feature-node-header">
            <span style={{ fontWeight: 600, color: '#f8fafc' }}>{feat.id}</span>
            <span className="feature-tag">{feat.type}</span>
          </div>

          <div className="feature-params">
            {feat.parameters?.map((p, pIdx) => (
              <div key={pIdx}>
                {p.name}: <span style={{ color: '#67e8f9', fontWeight: 600 }}>{p.value} {p.unit}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
