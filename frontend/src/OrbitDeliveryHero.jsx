import React, { useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

function OrbitWorld({ auto, dragRotation }) {
  const globe = useRef(null);
  const courier = useRef(null);
  const cloud = useRef(null);
  const lastDragRotation = useRef([0, 0]);

  const stars = useMemo(() => Array.from({ length: 48 }, (_, index) => {
    const angle = index * 2.399;
    const radius = 3.1 + (index % 7) * 0.17;
    return [Math.cos(angle) * radius, ((index % 9) - 4) * 0.36, Math.sin(angle) * radius];
  }), []);

  useFrame((state, delta) => {
    if (!globe.current) return;
    if (auto) globe.current.rotation.y += delta * 0.16;
    globe.current.rotation.y += dragRotation[0] - lastDragRotation.current[0];
    globe.current.rotation.x = Math.max(-0.55, Math.min(0.55, globe.current.rotation.x + dragRotation[1] - lastDragRotation.current[1]));
    lastDragRotation.current = dragRotation;
    if (courier.current) courier.current.position.y = 2.37 + Math.sin(state.clock.elapsedTime * 2.2) * 0.06;
    if (cloud.current) cloud.current.rotation.y -= delta * 0.045;
  });

  return (
    <>
      <ambientLight intensity={1.6} />
      <directionalLight color="#e4f4ff" intensity={2.6} position={[-4, 5, 5]} />
      <pointLight color="#6ea9ff" intensity={30} position={[3, -1, 5]} distance={10} />
      <group ref={globe} rotation={[0.1, 0.45, 0]}>
        <mesh>
          <sphereGeometry args={[2.08, 64, 64]} />
          <meshStandardMaterial color="#2d76cf" roughness={0.78} metalness={0.04} />
        </mesh>
        <mesh scale={[1.008, 1.008, 1.008]}>
          <sphereGeometry args={[2.08, 48, 48]} />
          <meshStandardMaterial color="#7ec4ff" transparent opacity={0.19} roughness={0.25} />
        </mesh>
        <Land position={[-0.65, 0.68, 1.8]} rotation={[0.3, -0.48, 0.2]} scale={[0.9, 0.48, 0.14]} />
        <Land position={[0.83, 0.23, 1.78]} rotation={[-0.2, 0.42, -0.24]} scale={[0.56, 0.88, 0.13]} />
        <Land position={[-0.38, -1.18, 1.57]} rotation={[0.18, -0.32, 0.42]} scale={[0.75, 0.3, 0.12]} />
        <mesh rotation={[0.98, 0.18, -0.38]}>
          <torusGeometry args={[2.18, 0.025, 8, 100]} />
          <meshBasicMaterial color="#e8f7ff" transparent opacity={0.78} />
        </mesh>
        <mesh rotation={[0.32, -0.55, 0.68]}>
          <torusGeometry args={[2.16, 0.017, 8, 100]} />
          <meshBasicMaterial color="#b6dbff" transparent opacity={0.65} />
        </mesh>
      </group>
      <group ref={courier} position={[0.92, 2.37, 0.6]} rotation={[0.08, -0.24, -0.12]}>
        <mesh castShadow><boxGeometry args={[0.43, 0.35, 0.28]} /><meshStandardMaterial color="#ffd15c" roughness={0.65} /></mesh>
        <mesh position={[0.18, 0.06, 0.15]}><boxGeometry args={[0.02, 0.38, 0.3]} /><meshStandardMaterial color="#f0ae3d" /></mesh>
        <mesh position={[0, 0.34, 0]}><sphereGeometry args={[0.17, 20, 20]} /><meshStandardMaterial color="#f8d0ad" roughness={0.9} /></mesh>
        <mesh position={[0, 0.47, 0.02]}><sphereGeometry args={[0.18, 20, 20]} /><meshStandardMaterial color="#264f9a" roughness={0.72} /></mesh>
      </group>
      <group ref={cloud}>
        {stars.map((position, index) => <mesh key={index} position={position}><sphereGeometry args={[index % 4 === 0 ? 0.034 : 0.02, 8, 8]} /><meshBasicMaterial color="#dff0ff" transparent opacity={0.75} /></mesh>)}
      </group>
    </>
  );
}

function Land({ position, rotation, scale }) {
  return (
    <mesh position={position} rotation={rotation} scale={scale}>
      <sphereGeometry args={[1, 24, 24]} />
      <meshStandardMaterial color="#78d492" roughness={0.92} />
    </mesh>
  );
}

export default function OrbitDeliveryHero({ copy, onOpenChat }) {
  const drag = useRef(null);
  const [auto, setAuto] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [rotation, setRotation] = useState([0, 0]);
  const canRender3d = typeof window !== "undefined" && typeof window.WebGLRenderingContext !== "undefined" && import.meta.env.MODE !== "test";

  const release = (pointerId) => {
    if (drag.current?.id !== pointerId) return;
    drag.current = null;
    setDragging(false);
  };

  return (
    <section className="delivery-hero" id="top" aria-labelledby="hero-title">
      <div className="delivery-hero-copy">
        <p className="delivery-eyebrow">{copy.eyebrow}</p>
        <h1 id="hero-title">{copy.hero}</h1>
        <p className="delivery-description">{copy.description}</p>
        <div className="delivery-actions">
          <a className="delivery-primary" href="#catalog">{copy.openCatalog}<span aria-hidden="true">→</span></a>
          <button className="delivery-secondary" onClick={onOpenChat} type="button">{copy.ask}</button>
        </div>
      </div>
      <div className="delivery-visual">
        <div
          aria-describedby="planet-instructions"
          aria-label={copy.stats}
          className={`delivery-planet${dragging ? " is-dragging" : ""}`}
          onLostPointerCapture={(event) => release(event.pointerId)}
          onPointerCancel={(event) => release(event.pointerId)}
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
            setDragging(true);
          }}
          onPointerMove={(event) => {
            if (drag.current?.id !== event.pointerId) return;
            const dx = event.clientX - drag.current.x;
            const dy = event.clientY - drag.current.y;
            drag.current = { ...drag.current, x: event.clientX, y: event.clientY };
            setRotation(([yaw, pitch]) => [yaw + dx * 0.012, Math.max(-0.55, Math.min(0.55, pitch + dy * 0.008))]);
          }}
          onPointerUp={(event) => release(event.pointerId)}
          role="group"
          tabIndex={0}
        >
          {canRender3d ? (
            <Canvas camera={{ fov: 38, position: [0, 0.1, 8.1] }} dpr={[1, 1.7]} gl={{ antialias: true, alpha: true }}>
              <OrbitWorld auto={auto} dragRotation={rotation} />
            </Canvas>
          ) : <div className="delivery-fallback-globe" aria-hidden="true"><i /><b /><span /></div>}
        </div>
        <div className="delivery-caption" aria-hidden="true"><span>{dragging ? copy.catalogNearby : copy.delivery}</span><svg viewBox="0 0 130 100" fill="none"><path d="M8 13c46 6 72 28 104 78m0 0-17-8m17 8 2-18" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" /></svg></div>
        <div className="delivery-stat"><span><i /> {copy.stats}</span><strong>14k</strong><small>{copy.pages}</small></div>
        <button aria-label={copy.stats} aria-pressed={!auto} className="delivery-motion" onClick={() => setAuto((value) => !value)} type="button"><span>{auto ? "Ⅱ" : "▶"}</span></button>
      </div>
      <p className="sr-only" id="planet-instructions">Перетаскивайте планету, чтобы повернуть её. Кнопка паузы останавливает анимацию.</p>
      <div className="delivery-clouds" aria-hidden="true"><i /><i /><i /><i /></div>
    </section>
  );
}
