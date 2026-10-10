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

export default function ArchitecturalScene() {
  return (
    <div className="w-full h-full relative min-h-[400px]">
      <div className="absolute inset-0 bg-gradient-to-r from-background via-transparent to-background z-10 pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent z-10 pointer-events-none" />
      
      <Canvas camera={{ position: [5, 4, 5], fov: 45 }}>
        <SceneContent />
      </Canvas>
      
      <div className="absolute bottom-4 right-4 z-20 text-[10px] text-muted-foreground uppercase tracking-widest font-mono">
        Spatial Intelligence Vector Model v1.0
      </div>
    </div>
  )
}
