import React, { useState, useEffect } from 'react';
import {
  Cpu,
  Layers,
  Upload,
  Play,
  Download,
  Settings,
  CheckCircle,
  FileText,
  Boxes,
  Compass,
  MessageSquare,
  ShieldCheck,
  RefreshCw,
  FolderOpen,
} from 'lucide-react';

import CADViewer from './components/CADViewer';
import CADIRViewer from './components/CADIRViewer';
import MoldInspector from './components/MoldInspector';
import AgentChat from './components/AgentChat';
import ValidationInspector from './components/ValidationInspector';

export default function App() {
  // Navigation & Tabs
  const [activeTab, setActiveTab] = useState('cadir'); // 'cadir' | 'mold' | 'validation' | 'chat'
  const [viewMode, setViewMode] = useState('solid'); // 'solid' | 'wireframe' | 'mold' | 'draft'

  // Pipeline state
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [pipelineProgress, setPipelineProgress] = useState(100);
  const [pipelineStage, setPipelineStage] = useState('Completed');
  const [latestLog, setLatestLog] = useState('Sẵn sàng. Dữ liệu chuẩn Mechanical Bracket đã nạp.');

  // Form Inputs
  const [blueprintName, setBlueprintName] = useState('mechanical_bracket_drawing.png');
  const [descriptionText, setDescriptionText] = useState('Mechanical Bracket: Base plate 100x62x18 mm, Boss OD44/ID28, Height 50mm, Front cutout R22.');
  const [mockCADFit, setMockCADFit] = useState(true);
  const [skipMold, setSkipMold] = useState(false);

  // Model & Report Data
  const [cadIRData, setCadIRData] = useState(null);
  const [moldData, setMoldData] = useState(null);
  const [validationData, setValidationData] = useState(null);

  // Load initial demo metadata & models
  useEffect(() => {
    fetchInitialData();
  }, []);

  const fetchInitialData = async () => {
    try {
      const cadRes = await fetch('/api/model/cad-ir');
      if (cadRes.ok) {
        const data = await cadRes.json();
        setCadIRData(data);
      }
      const moldRes = await fetch('/api/mold/report');
      if (moldRes.ok) {
        const data = await moldRes.json();
        setMoldData(data);
      }
      const valRes = await fetch('/api/verification/report');
      if (valRes.ok) {
        const data = await valRes.json();
        setValidationData(data);
      }
    } catch (e) {
      console.log('Using local fallback demo state');
    }
  };

  // Run Pipeline API call & polling
  const handleRunPipeline = async () => {
    setPipelineRunning(true);
    setPipelineProgress(5);
    setPipelineStage('Đang khởi tạo...');
    setLatestLog('Gửi yêu cầu tới Au2CAD Cloud Engine...');

    try {
      const res = await fetch('/api/pipeline/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          drawing_filename: blueprintName,
          context_text: descriptionText,
          mock_cadfit: mockCADFit,
          skip_mold: skipMold,
        }),
      });
      const data = await res.json();
      const taskId = data.task_id;
      setCurrentTaskId(taskId);

      // Poll task progress
      const interval = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/pipeline/status/${taskId}`);
          if (pollRes.ok) {
            const pollData = await pollRes.json();
            setPipelineProgress(pollData.progress || 0);
            setPipelineStage(pollData.stage || 'Đang xử lý');
            if (pollData.logs && pollData.logs.length > 0) {
              setLatestLog(pollData.logs[pollData.logs.length - 1]);
            }

            if (pollData.status === 'success') {
              clearInterval(interval);
              setPipelineRunning(false);
              fetchInitialData();
            } else if (pollData.status === 'failed') {
              clearInterval(interval);
              setPipelineRunning(false);
              alert('Pipeline lỗi: ' + (pollData.error || 'Chi tiết trong log'));
            }
          }
        } catch (err) {
          console.error(err);
        }
      }, 1500);
    } catch (err) {
      setPipelineRunning(false);
      alert('Không thể kết nối đến máy chủ API: ' + err.message);
    }
  };

  const handleDownloadSTEP = () => {
    window.open('/api/model/step', '_blank');
  };

  const handleDownloadSTL = () => {
    window.open('/api/model/stl', '_blank');
  };

  return (
    <div className="app-container">
      {/* ── TOP HEADER ── */}
      <header className="header-bar">
        <div className="brand-section">
          <div className="logo-badge">
            <Cpu size={22} />
          </div>
          <div>
            <div className="brand-title">Au2CAD Cloud</div>
            <div className="brand-subtitle">AGENTIC REVERSE ENGINEERING & PRELIMINARY MOLD DESIGN</div>
          </div>
          <div className="cloud-pill">
            <span className="pulse-dot" /> Cloud Ready (FastAPI + React)
          </div>
        </div>

        <div className="header-actions">
          <button className="btn btn-secondary" onClick={handleDownloadSTL}>
            <Download size={14} /> Xuất STL
          </button>
          <button className="btn btn-accent" onClick={handleDownloadSTEP}>
            <Download size={14} /> Tải file STEP (CAD Solid)
          </button>
        </div>
      </header>

      {/* ── MAIN WORKSPACE GRID ── */}
      <main className="main-layout">
        {/* LEFT PANEL: Inputs & Pipeline Controls */}
        <aside className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <FolderOpen size={16} color="#06b6d4" />
              <span>Input & Pipeline Config</span>
            </div>
          </div>

          <div className="panel-content">
            {/* Input Selection Card */}
            <div className="section-card">
              <div className="card-title">
                <span>Bản vẽ kỹ thuật (SSOT)</span>
                <span className="feature-tag">Bắt buộc</span>
              </div>
              <div className="dropzone">
                <Upload size={22} className="dropzone-icon" />
                <div className="dropzone-label">blueprint_drawing.png</div>
                <div className="dropzone-hint">Kéo thả bản vẽ kỹ thuật (.png, .jpg, .pdf)</div>
              </div>
            </div>

            {/* Engineer Context / Notes */}
            <div className="section-card">
              <div className="card-title">
                <span>Ghi chú kỹ sư (Context)</span>
                <FileText size={14} color="#94a3b8" />
              </div>
              <textarea
                style={{
                  width: '100%',
                  height: 64,
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  color: '#e2e8f0',
                  fontSize: '0.74rem',
                  fontFamily: 'var(--font-sans)',
                  padding: 8,
                  resize: 'none',
                  outline: 'none',
                }}
                value={descriptionText}
                onChange={(e) => setDescriptionText(e.target.value)}
              />
            </div>

            {/* Pipeline Configuration Switches */}
            <div className="section-card">
              <div className="card-title">
                <span>Cấu hình Pipeline</span>
                <Settings size={14} color="#94a3b8" />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: '0.78rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}>
                  <span>CADFit Mock Mode</span>
                  <input
                    type="checkbox"
                    checked={mockCADFit}
                    onChange={(e) => setMockCADFit(e.target.checked)}
                  />
                </label>
                <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}>
                  <span>Phân tích khuôn sơ bộ (Mold)</span>
                  <input
                    type="checkbox"
                    checked={!skipMold}
                    onChange={(e) => setSkipMold(!e.target.checked)}
                  />
                </label>
              </div>
            </div>

            {/* Action Button & Progress */}
            <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
                onClick={handleRunPipeline}
                disabled={pipelineRunning}
              >
                {pipelineRunning ? <RefreshCw size={16} className="pulse-dot" /> : <Play size={16} />}
                {pipelineRunning ? `Đang xử lý (${pipelineProgress}%)` : 'Khởi chạy Pipeline'}
              </button>

              {pipelineRunning && (
                <div style={{
                  background: 'rgba(0,0,0,0.3)',
                  borderRadius: 4,
                  overflow: 'hidden',
                  height: 6,
                  border: '1px solid var(--border-subtle)'
                }}>
                  <div style={{
                    width: `${pipelineProgress}%`,
                    height: '100%',
                    background: 'linear-gradient(90deg, #06b6d4, #10b981)',
                    transition: 'width 0.4s ease'
                  }} />
                </div>
              )}
            </div>

            {/* Pipeline Stage Tracker */}
            <div className="stepper-container">
              <div className={`step-item ${pipelineProgress >= 20 ? 'completed' : pipelineRunning ? 'active' : ''}`}>
                <div className="step-number">1</div>
                <div className="step-info">
                  <div className="step-title">Perception & SSOT</div>
                  <div className="step-desc">Trích xuất kích thước chuẩn</div>
                </div>
              </div>
              <div className={`step-item ${pipelineProgress >= 40 ? 'completed' : ''}`}>
                <div className="step-number">2</div>
                <div className="step-info">
                  <div className="step-title">Geometry Graph & CAD-IR</div>
                  <div className="step-desc">Đồ thị giải quyết xung đột</div>
                </div>
              </div>
              <div className={`step-item ${pipelineProgress >= 65 ? 'completed' : ''}`}>
                <div className="step-number">3</div>
                <div className="step-info">
                  <div className="step-title">Parametric Solid Builder</div>
                  <div className="step-desc">Sinh STEP / STL CadQuery</div>
                </div>
              </div>
              <div className={`step-item ${pipelineProgress >= 80 ? 'completed' : ''}`}>
                <div className="step-number">4</div>
                <div className="step-info">
                  <div className="step-title">Symbolic CAD Verifier</div>
                  <div className="step-desc">Kiểm chứng quy tắc kỹ thuật</div>
                </div>
              </div>
              <div className={`step-item ${pipelineProgress >= 100 ? 'completed' : ''}`}>
                <div className="step-number">5</div>
                <div className="step-info">
                  <div className="step-title">Mold Design Analyst</div>
                  <div className="step-desc">Góc thoát & hướng mở khuôn</div>
                </div>
              </div>
            </div>
          </div>
        </aside>

        {/* CENTER VIEWPORT: Three.js Interactive 3D CAD Stage */}
        <section className="viewport-panel">
          <CADViewer
            viewMode={viewMode}
            setViewMode={setViewMode}
            moldReport={moldData}
          />
        </section>

        {/* RIGHT PANEL: Tabbed Engineering Inspector */}
        <aside className="panel panel-right">
          <div className="tabs-header">
            <button
              className={`tab-btn ${activeTab === 'cadir' ? 'active' : ''}`}
              onClick={() => setActiveTab('cadir')}
            >
              <Boxes size={14} /> CAD-IR
            </button>
            <button
              className={`tab-btn ${activeTab === 'mold' ? 'active' : ''}`}
              onClick={() => setActiveTab('mold')}
            >
              <Compass size={14} /> Khuôn mẫu
            </button>
            <button
              className={`tab-btn ${activeTab === 'validation' ? 'active' : ''}`}
              onClick={() => setActiveTab('validation')}
            >
              <ShieldCheck size={14} /> Kiểm định
            </button>
            <button
              className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              <MessageSquare size={14} /> Agent AI
            </button>
          </div>

          <div className="panel-content">
            {activeTab === 'cadir' && <CADIRViewer cadIR={cadIRData} />}
            {activeTab === 'mold' && <MoldInspector moldReport={moldData} />}
            {activeTab === 'validation' && <ValidationInspector report={validationData} />}
            {activeTab === 'chat' && <AgentChat />}
          </div>
        </aside>
      </main>

      {/* ── BOTTOM STATUS BAR ── */}
      <footer className="footer-bar">
        <div className="footer-left">
          <span style={{ color: '#06b6d4' }}>● ENGINE: {pipelineStage}</span>
          <span className="log-ticker">{latestLog}</span>
        </div>
        <div>
          <span>Au2CAD v1.0 • Cloud API: http://127.0.0.1:8000</span>
        </div>
      </footer>
    </div>
  );
}
