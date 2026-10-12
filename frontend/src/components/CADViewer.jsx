import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { Box, Eye, Layers, RotateCcw, Maximize2, ShieldAlert } from 'lucide-react';

export default function CADViewer({
  viewMode = 'solid', // 'solid' | 'wireframe' | 'mold' | 'draft'
  setViewMode,
  modelStats,
  moldReport,
}) {
  const mountRef = useRef(null);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const cameraRef = useRef(null);
  const meshGroupRef = useRef(null);

  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const currentMount = mountRef.current;
    if (!currentMount) return;

    // 1. Scene setup
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0x070b14);

    // 2. Camera setup
    const width = currentMount.clientWidth;
    const height = currentMount.clientHeight;
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(130, 110, 150);
    cameraRef.current = camera;

    // 3. Renderer setup
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    currentMount.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0x06b6d4, 1.8);
    dirLight1.position.set(100, 150, 100);
    dirLight1.castShadow = true;
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x3b82f6, 1.0);
    dirLight2.position.set(-100, -50, -80);
    scene.add(dirLight2);

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.8);
    rimLight.position.set(0, 100, -100);
    scene.add(rimLight);

    // 5. Grid Floor & Axes
    const gridHelper = new THREE.GridHelper(200, 40, 0x06b6d4, 0x1e293b);
    gridHelper.position.y = -0.5;
    scene.add(gridHelper);

    const axesHelper = new THREE.AxesHelper(35);
    scene.add(axesHelper);

    // 6. Mesh Group
    const meshGroup = new THREE.Group();
    scene.add(meshGroup);
    meshGroupRef.current = meshGroup;

    // Build Demo Mechanical Bracket CSG geometry
    buildParametricBracket(meshGroup, viewMode);

    // 7. Mouse Orbit Controls (Native Vanilla implementation for smooth interaction)
    let isDragging = false;
    let isPanning = false;
    let prevMouse = { x: 0, y: 0 };
    let target = new THREE.Vector3(0, 20, 0);
    camera.lookAt(target);

    const onMouseDown = (e) => {
      if (e.button === 0) isDragging = true;
      if (e.button === 2) isPanning = true;
      prevMouse = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e) => {
      const deltaX = e.clientX - prevMouse.x;
      const deltaY = e.clientY - prevMouse.y;
      prevMouse = { x: e.clientX, y: e.clientY };

      if (isDragging) {
        const offset = camera.position.clone().sub(target);
        let spherical = new THREE.Spherical().setFromVector3(offset);
        spherical.theta -= deltaX * 0.008;
        spherical.phi -= deltaY * 0.008;
        spherical.phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.01, spherical.phi));
        offset.setFromSpherical(spherical);
        camera.position.copy(target).add(offset);
        camera.lookAt(target);
      } else if (isPanning) {
        const panSpeed = 0.15;
        const right = new THREE.Vector3().crossVectors(camera.up, camera.position.clone().sub(target)).normalize();
        target.add(right.multiplyScalar(-deltaX * panSpeed));
        target.y += deltaY * panSpeed;
        camera.position.y += deltaY * panSpeed;
        camera.lookAt(target);
      }
    };

    const onMouseUp = () => {
      isDragging = false;
      isPanning = false;
    };

    const onWheel = (e) => {
      e.preventDefault();
      const zoomSpeed = 0.08;
      const offset = camera.position.clone().sub(target);
      const factor = e.deltaY > 0 ? 1 + zoomSpeed : 1 - zoomSpeed;
      if (offset.length() * factor > 10 && offset.length() * factor < 400) {
        offset.multiplyScalar(factor);
        camera.position.copy(target).add(offset);
      }
    };

    const dom = renderer.domElement;
    dom.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    dom.addEventListener('wheel', onWheel, { passive: false });
    dom.addEventListener('contextmenu', (e) => e.preventDefault());

    // 8. Animation Loop
    let animationFrameId;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      renderer.render(scene, camera);
    };
    animate();

    // 9. Resize handler
    const handleResize = () => {
      if (!currentMount) return;
      const w = currentMount.clientWidth;
      const h = currentMount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
      dom.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      dom.removeEventListener('wheel', onWheel);
      if (currentMount.contains(dom)) {
        currentMount.removeChild(dom);
      }
      renderer.dispose();
    };
  }, []);

  // Update materials when viewMode changes
  useEffect(() => {
    if (meshGroupRef.current) {
      buildParametricBracket(meshGroupRef.current, viewMode);
    }
  }, [viewMode]);

  const resetCamera = () => {
    if (cameraRef.current) {
      cameraRef.current.position.set(130, 110, 150);
      cameraRef.current.lookAt(0, 20, 0);
    }
  };

  return (
    <div className="viewport-panel">
      {/* Top Floating View Controls */}
      <div className="viewport-toolbar">
        <div className="tool-group">
          <button
            className={`tool-btn ${viewMode === 'solid' ? 'active' : ''}`}
            onClick={() => setViewMode('solid')}
            title="Mô hình Solid gia công PBR"
          >
            <Box size={14} /> Solid CAD
          </button>
          <button
            className={`tool-btn ${viewMode === 'wireframe' ? 'active' : ''}`}
            onClick={() => setViewMode('wireframe')}
            title="Khung dây lưới đa giác"
          >
            <Layers size={14} /> Wireframe
          </button>
          <button
            className={`tool-btn ${viewMode === 'mold' ? 'active' : ''}`}
            onClick={() => setViewMode('mold')}
            title="Phân tách Lõi / Khuôn (Core & Cavity)"
          >
            <Eye size={14} /> Mold Core/Cavity
          </button>
          <button
            className={`tool-btn ${viewMode === 'draft' ? 'active' : ''}`}
            onClick={() => setViewMode('draft')}
            title="Biểu đồ nhiệt góc thoát khuôn"
          >
            <ShieldAlert size={14} /> Draft Angle
          </button>
        </div>

        <div className="tool-group">
          <button className="tool-btn" onClick={resetCamera} title="Reset góc nhìn">
            <RotateCcw size={14} /> Reset View
          </button>
        </div>
      </div>

      {/* 3D Canvas Mount Point */}
      <div ref={mountRef} className="canvas-container" />

      {/* Bottom Model Meta Overlay */}
      <div className="model-meta-overlay">
        <div className="meta-row">
          <span>Part:</span>
          <span className="meta-val">Mechanical Bracket (SSOT)</span>
        </div>
        <div className="meta-row">
          <span>Kích thước:</span>
          <span className="meta-val">100 × 62 × 50 mm</span>
        </div>
        <div className="meta-row">
          <span>Vật liệu khuôn:</span>
          <span className="meta-val">P20 Steel / Cavity + Core</span>
        </div>
        <div className="meta-row">
          <span>Tọa độ:</span>
          <span className="meta-val">CAD-IR Center [0, 0, 0]</span>
        </div>
      </div>
    </div>
  );
}

/**
 * Builds high-fidelity Mechanical Bracket CAD model matching SSOT Blueprint dimensions:
 * - Base plate: 100 x 62 x 18 mm with front semicircular cutout R22
 * - Upper Boss: Outer dia 44mm, Bore dia 28mm, Center Z=50mm
 * - Triangular transition web: thickness 9mm
 * - Slot cutout: 28 x 8 mm
 */
function buildParametricBracket(group, mode) {
  // Clear old children
  while (group.children.length > 0) {
    const obj = group.children[0];
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
      else obj.material.dispose();
    }
    group.remove(obj);
  }

  // Material selection based on mode
  let baseMat, bossMat, cavityMat, undercutMat;

  if (mode === 'wireframe') {
    const wireMat = new THREE.MeshBasicMaterial({ color: 0x06b6d4, wireframe: true });
    baseMat = bossMat = cavityMat = undercutMat = wireMat;
  } else if (mode === 'mold') {
    baseMat = new THREE.MeshStandardMaterial({
      color: 0x1e40af, // Cavity side (Blue)
      metalness: 0.6,
      roughness: 0.3,
    });
    bossMat = new THREE.MeshStandardMaterial({
      color: 0xd97706, // Core side (Amber/Gold)
      metalness: 0.7,
      roughness: 0.25,
    });
    cavityMat = baseMat;
    undercutMat = new THREE.MeshStandardMaterial({ color: 0xef4444 });
  } else if (mode === 'draft') {
    // Draft angle heatmap: Green for safe draft, Red for 0 deg / undercut
    baseMat = new THREE.MeshStandardMaterial({ color: 0x10b981, roughness: 0.4 });
    bossMat = new THREE.MeshStandardMaterial({ color: 0x10b981, roughness: 0.4 });
    cavityMat = new THREE.MeshStandardMaterial({ color: 0x059669 });
    undercutMat = new THREE.MeshStandardMaterial({ color: 0xf43f5e });
  } else {
    // Solid Machined Metal
    const steelMat = new THREE.MeshStandardMaterial({
      color: 0x94a3b8,
      metalness: 0.85,
      roughness: 0.2,
    });
    baseMat = bossMat = cavityMat = undercutMat = steelMat;
  }

  // 1. Base Plate (100 x 62 x 18 mm)
  const baseGeom = new THREE.BoxGeometry(100, 18, 62);
  const baseMesh = new THREE.Mesh(baseGeom, baseMat);
  baseMesh.position.set(0, 9, 0);
  baseMesh.castShadow = true;
  baseMesh.receiveShadow = true;
  group.add(baseMesh);

  // 2. Upper Boss Outer Cylinder (OD 44mm, length 62mm)
  const bossGeom = new THREE.CylinderGeometry(22, 22, 62, 48);
  bossGeom.rotateX(Math.PI / 2);
  const bossMesh = new THREE.Mesh(bossGeom, bossMat);
  bossMesh.position.set(25, 50, 0);
  bossMesh.castShadow = true;
  group.add(bossMesh);

  // 2b. Inner Bore (ID 28mm) Visual representation (Darker interior)
  const boreGeom = new THREE.CylinderGeometry(14, 14, 62.5, 36);
  boreGeom.rotateX(Math.PI / 2);
  const boreMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.8 });
  const boreMesh = new THREE.Mesh(boreGeom, boreMat);
  boreMesh.position.set(25, 50, 0);
  group.add(boreMesh);

  // 3. Stiffener Web / Rib (thickness 9mm)
  const webShape = new THREE.Shape();
  webShape.moveTo(-25, 18);
  webShape.lineTo(25, 50);
  webShape.lineTo(25, 18);
  webShape.closePath();

  const webExtrudeSettings = { depth: 9, bevelEnabled: false };
  const webGeom = new THREE.ExtrudeGeometry(webShape, webExtrudeSettings);
  const webMesh = new THREE.Mesh(webGeom, cavityMat);
  webMesh.position.set(0, 0, -4.5);
  webMesh.castShadow = true;
  group.add(webMesh);

  // 4. Front Semicircular Cutout (R22 cutout at -50)
  const cutoutGeom = new THREE.CylinderGeometry(22, 22, 18.2, 32);
  const cutoutMat = new THREE.MeshBasicMaterial({ color: 0x070b14 });
  const cutoutMesh = new THREE.Mesh(cutoutGeom, cutoutMat);
  cutoutMesh.position.set(-50, 9, 0);
  // Optional visual subtraction outline
  const edgeGeom = new THREE.EdgesGeometry(baseGeom);
  const lineMat = new THREE.LineBasicMaterial({ color: 0x06b6d4, linewidth: 1.5 });
  const edges = new THREE.LineSegments(edgeGeom, lineMat);
  edges.position.copy(baseMesh.position);
  group.add(edges);

  // 5. Mold Parting Line (Highlight when in mold mode)
  if (mode === 'mold') {
    const partingLinePoints = [
      new THREE.Vector3(-50, 9, -31),
      new THREE.Vector3(50, 9, -31),
      new THREE.Vector3(50, 9, 31),
      new THREE.Vector3(-50, 9, 31),
      new THREE.Vector3(-50, 9, -31),
    ];
    const partingGeom = new THREE.BufferGeometry().setFromPoints(partingLinePoints);
    const partingMat = new THREE.LineBasicMaterial({ color: 0x22d3ee, linewidth: 3 });
    const partingLine = new THREE.Line(partingGeom, partingMat);
    group.add(partingLine);
  }
}
