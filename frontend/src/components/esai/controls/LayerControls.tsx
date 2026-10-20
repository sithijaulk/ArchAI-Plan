'use client';

import React from 'react';
import { LayerVisibilityState } from '@/types/esai';

interface LayerControlsProps {
  layers: LayerVisibilityState;
  onToggleLayer: (key: keyof LayerVisibilityState) => void;
  onResetLayers?: () => void;
}

export const LayerControls: React.FC<LayerControlsProps> = ({
  layers,
  onToggleLayer,
  onResetLayers,
}) => {
  const layerConfigs: { key: keyof LayerVisibilityState; label: string; icon: string }[] = [
    { key: 'walls', label: 'Walls & Openings', icon: '🧱' },
    { key: 'ceiling', label: 'Ceiling Cutaway', icon: '🏠' },
    { key: 'furniture', label: 'Furniture', icon: '🛋️' },
    { key: 'cabinetry', label: 'Cabinetry', icon: '🗄️' },
    { key: 'appliances', label: 'Appliances', icon: '🔌' },
    { key: 'sanitary', label: 'Sanitary', icon: '🚿' },
    { key: 'lighting', label: 'Lighting', icon: '💡' },
    { key: 'servicePoints', label: 'Service Points', icon: '⚡' },
    { key: 'roomLabels', label: 'Labels', icon: '🏷️' },
    { key: 'wireframe', label: 'Wireframe', icon: '📐' },
  ];

  return (
    <div className="bg-slate-900/90 backdrop-blur-md px-3 py-2 rounded-xl border border-slate-800 shadow-xl text-xs">
      <div className="flex items-center justify-between mb-2 pb-1 border-b border-slate-800">
        <span className="font-semibold text-slate-300">Visibility Layers</span>
        {onResetLayers && (
          <button
            onClick={onResetLayers}
            className="text-[10px] text-cyan-400 hover:underline"
          >
            Reset
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {layerConfigs.map(({ key, label, icon }) => {
          const isActive = layers[key];
          return (
            <button
              key={String(key)}
              onClick={() => onToggleLayer(key)}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-all text-left ${
                isActive
                  ? 'bg-slate-800 text-slate-200 border border-slate-700'
                  : 'bg-slate-950/40 text-slate-500 border border-transparent hover:text-slate-400'
              }`}
            >
              <span className="text-xs">{icon}</span>
              <span className="truncate">{label}</span>
              <span
                className={`ml-auto w-1.5 h-1.5 rounded-full ${
                  isActive ? 'bg-cyan-400' : 'bg-slate-700'
                }`}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
};
