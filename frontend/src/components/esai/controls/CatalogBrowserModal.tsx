'use client';

import React, { useState, useEffect } from 'react';
import { esaiApi } from '@/lib/api/esai';

interface CatalogBrowserModalProps {
  isOpen: boolean;
  onClose: () => void;
  roomType?: string;
  onSelectAsset: (asset: {
    asset_id: string;
    asset_name: string;
    category: string;
    dimensions: { width: number; depth: number; height: number };
    material?: string;
    color?: string;
  }) => void;
  mode?: 'add' | 'replace';
  currentAssetCategory?: string;
}

export const CatalogBrowserModal: React.FC<CatalogBrowserModalProps> = ({
  isOpen,
  onClose,
  roomType,
  onSelectAsset,
  mode = 'add',
  currentAssetCategory,
}) => {
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>(currentAssetCategory || '');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [search, setSearch] = useState<string>('');

  useEffect(() => {
    if (!isOpen) return;
    const fetchCats = async () => {
      try {
        const cats = await esaiApi.getCatalogCategories();
        setCategories(cats || []);
        if (currentAssetCategory && cats.includes(currentAssetCategory)) {
          setSelectedCategory(currentAssetCategory);
        } else if (cats.length > 0 && !selectedCategory) {
          setSelectedCategory(cats[0]);
        }
      } catch (err) {
        console.error('Failed to fetch categories:', err);
      }
    };
    fetchCats();
  }, [isOpen, currentAssetCategory]);

  useEffect(() => {
    if (!isOpen || !selectedCategory) return;
    const fetchItems = async () => {
      setLoading(true);
      try {
        const res = await esaiApi.getCatalogItems({
          category: selectedCategory,
          room_type: roomType || undefined,
        });
        setItems(res || []);
      } catch (err) {
        console.error('Failed to fetch catalog items:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchItems();
  }, [isOpen, selectedCategory, roomType]);

  if (!isOpen) return null;

  const filteredItems = items.filter((item) =>
    search ? item.name.toLowerCase().includes(search.toLowerCase()) : true
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden text-xs text-slate-300">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800 bg-slate-950/50">
          <div>
            <span className="text-sm font-bold text-white flex items-center gap-2">
              <span className="text-cyan-400">🗂</span>
              {mode === 'replace' ? 'Replace Furniture Variant' : 'Add Furniture from Catalog'}
            </span>
            <span className="text-[11px] text-slate-400 block mt-0.5">
              Verified Phase 3 Architectural & Ergonomic Asset Catalog
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
          >
            ✕
          </button>
        </div>

        {/* Category & Search Filter */}
        <div className="p-4 border-b border-slate-800 flex flex-wrap items-center gap-3 bg-slate-900/50">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1 rounded-lg capitalize whitespace-nowrap font-medium transition-all ${
                  selectedCategory === cat
                    ? 'bg-cyan-500 text-white shadow-sm'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {cat.replace('_', ' ')}
              </button>
            ))}
          </div>
          <div className="flex-1 min-w-[200px]">
            <input
              type="text"
              placeholder="Search catalog items..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            />
          </div>
        </div>

        {/* Item Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-48 text-slate-400">
              <span className="animate-spin text-xl mr-2">⚙</span> Loading catalog assets...
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-slate-500 text-center">
              <span>No items found matching your filter.</span>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {filteredItems.map((item) => {
                const w = item.dimensions?.width ?? 1.0;
                const d = item.dimensions?.depth ?? 1.0;
                const h = item.dimensions?.height ?? 1.0;

                return (
                  <div
                    key={item.id}
                    className="flex flex-col justify-between bg-slate-950 border border-slate-800/80 hover:border-cyan-500/50 rounded-xl p-3 transition-all group"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] text-cyan-400 uppercase font-semibold">
                          {item.category?.replace('_', ' ')}
                        </span>
                        {item.is_configurable && (
                          <span className="text-[9px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded font-mono">
                            Configurable
                          </span>
                        )}
                      </div>
                      <div className="font-semibold text-white text-xs group-hover:text-cyan-300 transition-colors">
                        {item.name}
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        {w.toFixed(2)} × {d.toFixed(2)} × {h.toFixed(2)} m
                      </div>
                    </div>

                    <div className="mt-3 pt-2 border-t border-slate-900 flex justify-end">
                      <button
                        onClick={() => {
                          onSelectAsset({
                            asset_id: item.id,
                            asset_name: item.name,
                            category: item.category,
                            dimensions: { width: w, depth: d, height: h },
                            material: item.default_material || 'default',
                            color: item.default_color || '#94a3b8',
                          });
                          onClose();
                        }}
                        className="px-3 py-1 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-[11px] transition-all shadow-sm"
                      >
                        {mode === 'replace' ? 'Replace' : 'Add to Room'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
