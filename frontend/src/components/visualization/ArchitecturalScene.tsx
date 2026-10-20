"use client"
import React, { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Line, Box, Grid } from '@react-three/drei'
import * as THREE from 'three'

function SceneContent() {
  const groupRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.1
    }
  })

  // Conceptual points for a footprint
  const points = [
    new THREE.Vector3(-2, 0, -2),
    new THREE.Vector3(2, 0, -2),
    new THREE.Vector3(2, 0, 1),
    new THREE.Vector3(1, 0, 2),
    new THREE.Vector3(-2, 0, 2),
    new THREE.Vector3(-2, 0, -2),
  ]

  return (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} color="#00f0ff" />
      <directionalLight position={[-10, 10, -5]} intensity={0.5} color="#8a2be2" />
      
      <Grid infiniteGrid fadeDistance={20} sectionColor="#333" cellColor="#111" />
      
      <group ref={groupRef}>
        {/* Footprint Boundary */}
        <Line points={points} color="#00f0ff" lineWidth={2} dashed={false} />
        
        {/* Conceptual Nodes */}
        {points.slice(0, 5).map((pos, i) => (
          <mesh key={i} position={pos}>
            <sphereGeometry args={[0.05, 16, 16]} />
            <meshBasicMaterial color="#00f0ff" />
          </mesh>
        ))}
        
        {/* Central Core Volume */}
        <Box args={[1.5, 1, 1.5]} position={[-0.5, 0.5, 0]}>
          <meshStandardMaterial color="#222" transparent opacity={0.8} wireframe />
        </Box>
        
        {/* Animated Connection Paths (Concept) */}
        <Line 
          points={[new THREE.Vector3(-0.5, 1, 0), new THREE.Vector3(1, 1, 0), new THREE.Vector3(1, 0, -1)]} 
          color="#8a2be2" 
          lineWidth={1.5} 
        />
      </group>

      <OrbitControls 
        enableZoom={false} 
        enablePan={false}
        autoRotate 
        autoRotateSpeed={0.5}
        maxPolarAngle={Math.PI / 2 - 0.1}
      />
    </>
  )
}

import { WebGLErrorBoundary } from './WebGLErrorBoundary'

function VectorFallbackScene() {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center relative overflow-hidden bg-slate-950/60 p-6">
      {/* Decorative Grid Pattern */}
      <div 
        className="absolute inset-0 opacity-20 pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(#00f0ff22 1px, transparent 1px), linear-gradient(90deg, #00f0ff22 1px, transparent 1px)`,
          backgroundSize: '32px 32px',
        }}
      />

      {/* Isometric SVG Vector Graphic */}
      <svg
        viewBox="0 0 400 300"
        className="w-full max-w-[340px] h-auto drop-shadow-[0_0_25px_rgba(0,240,255,0.25)] relative z-10"
      >
        <defs>
          <linearGradient id="cyanPurple" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00f0ff" />
            <stop offset="100%" stopColor="#8a2be2" />
          </linearGradient>
        </defs>

        {/* Isometric Base Grid */}
        <path
          d="M 200,60 L 340,140 L 200,220 L 60,140 Z"
          fill="none"
          stroke="#334155"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />
        <path
          d="M 200,90 L 300,145 L 200,200 L 100,145 Z"
          fill="rgba(0,240,255,0.03)"
          stroke="#00f0ff44"
          strokeWidth="1"
        />

        {/* Isometric Building Footprint & Extrusions */}
        <polygon
          points="150,115 250,90 270,160 210,185 130,150"
          fill="none"
          stroke="#00f0ff"
          strokeWidth="2"
        />
        <polygon
          points="150,65 250,40 270,110 210,135 130,100"
          fill="rgba(138,43,226,0.12)"
          stroke="#8a2be2"
          strokeWidth="2"
        />

        {/* Vertical Wall Pillars */}
        <line x1="150" y1="115" x2="150" y2="65" stroke="#00f0ff" strokeWidth="1.5" />
        <line x1="250" y1="90" x2="250" y2="40" stroke="#00f0ff" strokeWidth="1.5" />
        <line x1="270" y1="160" x2="270" y2="110" stroke="#00f0ff" strokeWidth="1.5" />
        <line x1="210" y1="185" x2="210" y2="135" stroke="#00f0ff" strokeWidth="1.5" />
        <line x1="130" y1="150" x2="130" y2="100" stroke="#00f0ff" strokeWidth="1.5" />

        {/* Vertex Spheres / Nodes */}
        {[[150, 65], [250, 40], [270, 110], [210, 135], [130, 100], [200, 140]].map(([cx, cy], i) => (
          <circle key={i} cx={cx} cy={cy} r="4" fill="#00f0ff" className="animate-pulse" />
        ))}
      </svg>

      <div className="mt-4 text-center z-10">
        <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-widest block mb-1">
          Vector Schematic Mode
        </span>
        <span className="text-[10px] text-muted-foreground/70">
          Hardware acceleration disabled in browser — showing 2D spatial schematic
        </span>
      </div>
    </div>
  )
}

export default function ArchitecturalScene() {
  return (
    <div className="w-full h-full relative min-h-[400px]">
      <div className="absolute inset-0 bg-gradient-to-r from-background via-transparent to-background z-10 pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent z-10 pointer-events-none" />
      
      <WebGLErrorBoundary fallback={<VectorFallbackScene />}>
        <Canvas
          camera={{ position: [5, 4, 5], fov: 45 }}
          gl={{
            powerPreference: 'default',
            failIfMajorPerformanceCaveat: false,
            antialias: true,
          }}
        >
          <SceneContent />
        </Canvas>
      </WebGLErrorBoundary>
      
      <div className="absolute bottom-4 right-4 z-20 text-[10px] text-muted-foreground uppercase tracking-widest font-mono">
        Spatial Intelligence Vector Model v1.0
      </div>
    </div>
  )
}
