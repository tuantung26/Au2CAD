import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Cpu,
  Upload,
  Play,
  Download,
  Settings,
  FileText,
  Boxes,
  Compass,
  MessageSquare,
  ShieldCheck,
  RefreshCw,
  FolderOpen,
  Trash2,
  Camera,
  X,
  ImagePlus,
  CheckCircle2,
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
  const [pipelineProgress, setPipelineProgress] = useState(0);
  const [pipelineStage, setPipelineStage] = useState('Sẵn sàng');
  const [latestLog, setLatestLog] = useState('Chào mừng đến với Au2CAD — nhập thông tin bản vẽ và khởi chạy pipeline.');

  // Form Inputs
  const [blueprintName, setBlueprintName] = useState('');
  const [blueprintFile, setBlueprintFile] = useState(null);  // actual File object
  const [photoFiles, setPhotoFiles] = useState([]);           // File[] of physical photos
  const [photoPreviews, setPhotoPreviews] = useState([]);     // base64 preview URLs
  const [descriptionText, setDescriptionText] = useState('');
  const [mockCADFit, setMockCADFit] = useState(true);
  const [skipMold, setSkipMold] = useState(false);
  const [viewerRefreshKey, setViewerRefreshKey] = useState(0);
  const photoInputRef = useRef(null);

  // Model & Report Data
  const [cadIRData, setCadIRData] = useState(null);
  const [moldData, setMoldData] = useState(null);
  const [validationData, setValidationData] = useState(null);

  const fetchInitialData = useCallback(async () => {
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
  }, []);

  // Add physical photos (multi-select, deduplicated)
  const handleAddPhotos = useCallback((files) => {
    const incoming = Array.from(files);
    setPhotoFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.name));
      return [...prev, ...incoming.filter((f) => !existingNames.has(f.name))];
    });
    incoming.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        setPhotoPreviews((prev) => {
          const existingNames = new Set(prev.map((p) => p.name));
          if (existingNames.has(file.name)) return prev;
          return [...prev, { name: file.name, url: e.target.result }];
        });
      };
      reader.readAsDataURL(file);
    });
  }, []);

  const handleRemovePhoto = useCallback((name) => {
    setPhotoFiles((prev) => prev.filter((f) => f.name !== name));
    setPhotoPreviews((prev) => prev.filter((p) => p.name !== name));
  }, []);

  // Clear all inputs and reset to fresh state
  const handleClearInput = useCallback(() => {
    setBlueprintName('');
    setBlueprintFile(null);
    setPhotoFiles([]);
    setPhotoPreviews([]);
    setDescriptionText('');
    setMockCADFit(true);
    setSkipMold(false);
    setPipelineRunning(false);
    setCurrentTaskId(null);
    setPipelineProgress(0);
    setPipelineStage('Sẵn sàng');
    setLatestLog('Đã xóa input. Nhập thông tin mới để bắt đầu.');
    setCadIRData(null);
    setMoldData(null);
    setValidationData(null);
  }, []);

  // Called by AgentChat when agent rebuilds the model
  const handleModelRefresh = useCallback(() => {
    setViewerRefreshKey((k) => k + 1);
    fetchInitialData();
    setLatestLog('🤖 Agent đã cập nhật mô hình — đang tải lại viewer...');
  }, [fetchInitialData]);

  // Load initial demo metadata & models
  useEffect(() => {
    // Don't auto-load on start — wait for user input
  }, []);

  // Run Pipeline API call & polling
  const handleRunPipeline = async () => {
    // Validate: need at least one input
    const hasDrawing = !!blueprintName || !!blueprintFile;
    const hasPhotos = photoFiles.length > 0;
    const hasDescription = !!descriptionText.trim();
    if (!hasDrawing && !hasPhotos && !hasDescription) {
      alert('Vui lòng cung cấp ít nhất một trong ba: Bản vẽ kỹ thuật, Ảnh chụp vật thể, hoặc Ghi chú mô tả.');
      return;
    }

    setPipelineRunning(true);
    setPipelineProgress(3);
    setPipelineStage('Đang upload...');
    setLatestLog('Đang tải file lên server...');

    // Step 1: Upload all files first
    let uploadedDrawing = blueprintName || null;
    let uploadedPhotos = [];
    try {
      if (blueprintFile || photoFiles.length > 0) {
        const formData = new FormData();
        if (blueprintFile) formData.append('drawing', blueprintFile);
        photoFiles.forEach((f) => formData.append('photos', f));
        if (descriptionText.trim()) formData.append('description', descriptionText.trim());

        const uploadRes = await fetch('/api/upload', { method: 'POST', body: formData });
        if (uploadRes.ok) {
          const uploadData = await uploadRes.json();
          if (uploadData.files?.drawing) uploadedDrawing = uploadData.files.drawing;
          if (uploadData.files?.photos) uploadedPhotos = uploadData.files.photos;
          setLatestLog(`Đã upload ${Object.keys(uploadData.files || {}).length} file thành công.`);
        }
      }
    } catch (uploadErr) {
      console.warn('Upload warning:', uploadErr);
    }

    setPipelineProgress(5);
    setPipelineStage('Đang khởi tạo...');
    setLatestLog('Gửi yêu cầu tới Au2CAD Engine...');

    try {
      const res = await fetch('/api/pipeline/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          drawing_filename: uploadedDrawing,
          photo_filenames: uploadedPhotos,
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
            <div className="brand-title">Au2CAD</div>
            <div className="brand-subtitle">AGENTIC REVERSE ENGINEERING & PRELIMINARY MOLD DESIGN</div>
          </div>
          <div className="cloud-pill">
            <span className="pulse-dot" /> FastAPI + React
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
            <button
              className="btn btn-danger-sm"
              onClick={handleClearInput}
              title="Xóa tất cả input và nhập mới"
              style={{ padding: '5px 10px', fontSize: '0.75rem', gap: 5 }}
            >
              <Trash2 size={13} /> Clear
            </button>
          </div>

          <div className="panel-content">

            {/* ─── Input status badges ─── */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {[{ label: 'Bản vẽ', active: !!blueprintName }, { label: `Ảnh vật (${photoFiles.length})`, active: photoFiles.length > 0 }, { label: 'Mô tả', active: !!descriptionText.trim() }].map((b) => (
                <span key={b.label} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  fontSize: '0.7rem', fontWeight: 600, padding: '3px 8px',
                  borderRadius: 999,
                  background: b.active ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${b.active ? 'rgba(16,185,129,0.4)' : 'rgba(255,255,255,0.08)'}`,
                  color: b.active ? '#10b981' : '#475569',
                }}>
                  {b.active && <CheckCircle2 size={10} />}
                  {b.label}
                </span>
              ))}
            </div>

            {/* ─── 1. Bản vẽ kỹ thuật ─── */}
            <div className="section-card">
              <div className="card-title">
                <span>① Bản vẽ kỹ thuật</span>
                <span className="feature-tag" style={{ background: 'rgba(6,182,212,0.15)', color: '#67e8f9' }}>Tùy chọn</span>
              </div>
              <div
                className="dropzone"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const file = e.dataTransfer.files[0];
                  if (file) { setBlueprintName(file.name); setBlueprintFile(file); }
                }}
                onClick={() => document.getElementById('blueprint-file-input').click()}
                style={blueprintName ? { borderColor: 'rgba(6,182,212,0.5)', background: 'rgba(6,182,212,0.06)' } : {}}
              >
                <Upload size={20} className="dropzone-icon" style={{ color: blueprintName ? '#06b6d4' : undefined }} />
                <div className="dropzone-label" style={{ fontSize: '0.8rem' }}>
                  {blueprintName || 'Kéo thả hoặc nhấn để chọn'}
                </div>
                <div className="dropzone-hint">.png .jpg .pdf — để trống để dùng demo</div>
              </div>
              {blueprintName && (
                <button onClick={() => { setBlueprintName(''); setBlueprintFile(null); }}
                  style={{ marginTop: 6, fontSize: '0.7rem', color: '#64748b', background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <X size={11} /> Xóa bản vẽ
                </button>
              )}
              <input id="blueprint-file-input" type="file" accept=".png,.jpg,.jpeg,.pdf,.webp"
                style={{ display: 'none' }}
                onChange={(e) => { const f = e.target.files[0]; if (f) { setBlueprintName(f.name); setBlueprintFile(f); } }}
              />
            </div>

            {/* ─── 2. Ảnh chụp vật thể ─── */}
            <div className="section-card">
              <div className="card-title">
                <span>② Ảnh chụp vật thể</span>
                <span className="feature-tag" style={{ background: 'rgba(139,92,246,0.15)', color: '#c4b5fd' }}>Tùy chọn</span>
              </div>

              {/* Photo thumbnails */}
              {photoPreviews.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                  {photoPreviews.map((p) => (
                    <div key={p.name} style={{ position: 'relative', width: 56, height: 56 }}>
                      <img src={p.url} alt={p.name} title={p.name}
                        style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 6,
                          border: '1px solid rgba(139,92,246,0.4)' }} />
                      <button onClick={() => handleRemovePhoto(p.name)}
                        style={{ position: 'absolute', top: -5, right: -5, width: 16, height: 16,
                          borderRadius: '50%', background: '#f43f5e', border: 'none',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          cursor: 'pointer', padding: 0 }}>
                        <X size={9} color="#fff" />
                      </button>
                    </div>
                  ))}
                  {/* Add more button */}
                  <div onClick={() => photoInputRef.current?.click()}
                    style={{ width: 56, height: 56, borderRadius: 6, border: '1.5px dashed rgba(139,92,246,0.4)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', color: '#8b5cf6', background: 'rgba(139,92,246,0.05)' }}>
                    <ImagePlus size={18} />
                  </div>
                </div>
              )}

              {photoPreviews.length === 0 && (
                <div className="dropzone"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { e.preventDefault(); handleAddPhotos(e.dataTransfer.files); }}
                  onClick={() => photoInputRef.current?.click()}
                  style={{ borderColor: 'rgba(139,92,246,0.3)', cursor: 'pointer' }}
                >
                  <Camera size={20} className="dropzone-icon" style={{ color: '#8b5cf6' }} />
                  <div className="dropzone-label" style={{ fontSize: '0.8rem' }}>Kéo thả hoặc nhấn để chọn</div>
                  <div className="dropzone-hint">Nhiều ảnh, góc chụp khác nhau càng tốt</div>
                </div>
              )}

              <input ref={photoInputRef} type="file" multiple
                accept=".png,.jpg,.jpeg,.webp,.heic"
                style={{ display: 'none' }}
                onChange={(e) => handleAddPhotos(e.target.files)}
              />

              {photoPreviews.length > 0 && (
                <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: 4 }}>
                  {photoFiles.length} ảnh đã chọn — VLM sẽ phân tích hình dạng 3D từ ảnh thực
                </div>
              )}
            </div>

            {/* ─── 3. Ghi chú mô tả ─── */}
            <div className="section-card">
              <div className="card-title">
                <span>③ Ghi chú mô tả</span>
                <span className="feature-tag" style={{ background: 'rgba(245,158,11,0.15)', color: '#fbbf24' }}>Tùy chọn</span>
              </div>
              <textarea
                style={{
                  width: '100%',
                  height: 72,
                  background: 'var(--bg-input)',
                  border: `1px solid ${descriptionText.trim() ? 'rgba(245,158,11,0.35)' : 'var(--border-subtle)'}`,
                  borderRadius: 'var(--radius-sm)',
                  color: '#e2e8f0',
                  fontSize: '0.74rem',
                  fontFamily: 'var(--font-sans)',
                  padding: 8,
                  resize: 'none',
                  outline: 'none',
                  transition: 'border-color 0.2s',
                }}
                placeholder="Ví dụ: Boss Ø44/ID28 cao 50mm, Base plate 100×62×18mm. Mô tả càng chi tiết, kết quả CAD càng chính xác..."
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
            key={viewerRefreshKey}
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
            {activeTab === 'chat' && <AgentChat onModelRefresh={handleModelRefresh} />}
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
          <span>Au2CAD v1.0 • API: http://127.0.0.1:8000</span>
        </div>
      </footer>
    </div>
  );
}
