import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '../../api/client';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Fetch background image via authenticated axios client and return a data URL. */
async function fetchBackgroundAsDataUrl(competitionId: string): Promise<string | null> {
  try {
    const response = await api.get(
      `admin/competitions/${competitionId}/badge-template/background`,
      { responseType: 'blob' }
    );
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(response.data as Blob);
    });
  } catch {
    return null;
  }
}

// ─── Types ───────────────────────────────────────────────────────────────────

type ElementType = 'auto_text' | 'custom_text' | 'image' | 'shape';
type AlignType = 'left' | 'center' | 'right';
type ShapeType = 'rect' | 'ellipse' | 'line';

const AUTO_FIELD_KEYS = ['LAST_NAME', 'FIRST_NAME', 'MIDDLE_NAME', 'ROLE'] as const;
const IMAGE_FIELD_KEYS = ['QR_IMAGE', 'PHOTO'] as const;
const SHAPE_TYPES: { value: ShapeType; label: string }[] = [
  { value: 'rect',    label: 'Прямоугольник' },
  { value: 'ellipse', label: 'Эллипс' },
  { value: 'line',    label: 'Линия' },
];

const FIELD_LABELS: Record<string, string> = {
  LAST_NAME: '{{ФАМИЛИЯ}}',
  FIRST_NAME: '{{ИМЯ}}',
  MIDDLE_NAME: '{{ОТЧЕСТВО}}',
  ROLE: '{{РОЛЬ}}',
  QR_IMAGE: '{{QR-КОД}}',
  PHOTO: '{{ФОТО}}',
};

const FIELD_COLORS: Record<string, string> = {
  QR_IMAGE: '#e0f0ff',
  PHOTO: '#fff0e0',
};

/** Border frame embedded directly in a non-shape element. Moves/resizes with it. */
interface ElementBorder {
  stroke_color: string;
  stroke_width_pt: number;
  border_radius_mm: number;
  fill_color: string;   // hex or 'none'
  opacity: number;
}

interface BadgeElement {
  id: string;
  type: ElementType;
  // text / auto_text fields
  field_key?: string;
  text?: string;
  font_family: string;
  font_size_pt: number;
  font_color: string;
  bold: boolean;
  italic: boolean;
  underline: boolean;
  align: AlignType;
  // geometry (all element types)
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  // shape-only fields
  shape_type?: ShapeType;
  fill_color?: string;      // hex or 'none'
  stroke_color?: string;    // hex
  stroke_width_pt?: number;
  border_radius_mm?: number;
  opacity?: number;         // 0–1
  // embedded border frame (for auto_text, custom_text, image elements)
  border?: ElementBorder;
}

interface BadgeConfig {
  width_mm: number;
  height_mm: number;
  background_w_mm: number;
  background_h_mm: number;
  elements: BadgeElement[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const MM_TO_PX = 3.7795275591; // 1 mm = 3.78 px at 96dpi

/** System fonts that exist in most Linux/Docker environments — no loading needed. */
const SYSTEM_FONT_CSS: Record<string, string> = {
  DejaVuSans: "'DejaVu Sans', Arial, Helvetica, sans-serif",
  'DejaVuSans-Bold': "'DejaVu Sans', Arial, Helvetica, sans-serif",
  'DejaVuSans-Oblique': "'DejaVu Sans', Arial, Helvetica, sans-serif",
  LiberationSans: "'Liberation Sans', Arial, Helvetica, sans-serif",
  'LiberationSans-Bold': "'Liberation Sans', Arial, Helvetica, sans-serif",
  'LiberationSans-Italic': "'Liberation Sans', Arial, Helvetica, sans-serif",
  Helvetica: 'Helvetica, Arial, sans-serif',
};

/** Resolve a ReportLab font name to a CSS font-family string for the editor preview. */
function cssFontFamily(name: string): string {
  return SYSTEM_FONT_CSS[name] ?? `'${name}', Arial, sans-serif`;
}

/** Track which custom fonts have already been loaded via FontFace API. */
const _loadedFonts = new Set<string>();

/** Load a custom font (Magistral etc.) from the backend and register it with the browser. */
async function loadCustomFont(name: string): Promise<void> {
  if (_loadedFonts.has(name) || name in SYSTEM_FONT_CSS) return;
  const extensions = ['.ttf', '.otf'];
  for (const ext of extensions) {
    try {
      const response = await api.get(`admin/badge-fonts/${encodeURIComponent(name + ext)}`, {
        responseType: 'arraybuffer',
      });
      const font = new FontFace(name, response.data as ArrayBuffer);
      await font.load();
      document.fonts.add(font);
      _loadedFonts.add(name);
      return;
    } catch {
      // try next extension
    }
  }
}

const FONT_FAMILIES = [
  'DejaVuSans',
  'LiberationSans',
  'Magistral-Bold',
  'Magistral-Medium',
  'Magistral-Book',
  'Helvetica',
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function px(mm: number) {
  return mm * MM_TO_PX;
}

function mm(pxVal: number) {
  return pxVal / MM_TO_PX;
}

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

function defaultElement(type: ElementType, fieldKey?: string, shapeType?: ShapeType): BadgeElement {
  const isShape = type === 'shape';
  const isImage = type === 'image';
  return {
    id: newId(),
    type,
    field_key: fieldKey,
    text: type === 'custom_text' ? 'Текст' : undefined,
    x_mm: 5,
    y_mm: 5,
    width_mm: isImage ? 30 : isShape ? 60 : 80,
    height_mm: isImage ? 30 : isShape && shapeType === 'line' ? 5 : isShape ? 30 : 10,
    font_family: 'DejaVuSans',
    font_size_pt: 12,
    font_color: '#000000',
    bold: false,
    italic: false,
    underline: false,
    align: 'left',
    // shape defaults
    shape_type: shapeType,
    fill_color: isShape && shapeType !== 'line' ? '#ffffff' : 'none',
    stroke_color: '#000000',
    stroke_width_pt: 1,
    border_radius_mm: 0,
    opacity: 1,
  };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

interface ElementBoxProps {
  elem: BadgeElement;
  selected: boolean;
  onSelect: () => void;
  onChange: (partial: Partial<BadgeElement>) => void;
}

/** Attach a mousemove+mouseup listener pair and return a cleanup. */
function startDrag(
  e: React.MouseEvent,
  onMove: (dx: number, dy: number) => void,
) {
  e.stopPropagation();
  const startX = e.clientX;
  const startY = e.clientY;
  const moveHandler = (ev: MouseEvent) =>
    onMove(mm(ev.clientX - startX), mm(ev.clientY - startY));
  const upHandler = () => {
    window.removeEventListener('mousemove', moveHandler);
    window.removeEventListener('mouseup', upHandler);
  };
  window.addEventListener('mousemove', moveHandler);
  window.addEventListener('mouseup', upHandler);
}

const ElementBox: React.FC<ElementBoxProps> = ({ elem, selected, onSelect, onChange }) => {
  const handleMouseDown = (e: React.MouseEvent) => {
    onSelect();
    startDrag(e, (dx, dy) => {
      onChange({
        x_mm: Math.max(0, elem.x_mm + dx),
        y_mm: Math.max(0, elem.y_mm + dy),
      });
    });
  };

  // SE corner: resize width + height
  const handleResizeSE = (e: React.MouseEvent) => {
    const { width_mm: w0, height_mm: h0 } = elem;
    startDrag(e, (dx, dy) => onChange({
      width_mm: Math.max(5, w0 + dx),
      height_mm: Math.max(5, h0 + dy),
    }));
  };

  // Bottom edge: resize height (bottom fixed at top)
  const handleResizeS = (e: React.MouseEvent) => {
    const h0 = elem.height_mm;
    startDrag(e, (_dx, dy) => onChange({ height_mm: Math.max(5, h0 + dy) }));
  };

  // Top edge: resize height from top (bottom edge stays fixed)
  const handleResizeN = (e: React.MouseEvent) => {
    const { y_mm: y0, height_mm: h0 } = elem;
    startDrag(e, (_dx, dy) => {
      const newH = Math.max(5, h0 - dy);
      onChange({ y_mm: Math.max(0, y0 + (h0 - newH)), height_mm: newH });
    });
  };

  // Right edge: resize width
  const handleResizeE = (e: React.MouseEvent) => {
    const w0 = elem.width_mm;
    startDrag(e, (dx) => onChange({ width_mm: Math.max(5, w0 + dx) }));
  };

  // Left edge: resize width from left (right edge stays fixed)
  const handleResizeW = (e: React.MouseEvent) => {
    const { x_mm: x0, width_mm: w0 } = elem;
    startDrag(e, (dx) => {
      const newW = Math.max(5, w0 - dx);
      onChange({ x_mm: Math.max(0, x0 + (w0 - newW)), width_mm: newW });
    });
  };

  const isImage = elem.type === 'image';
  const isShape = elem.type === 'shape';
  const label = elem.field_key ? FIELD_LABELS[elem.field_key] ?? elem.field_key : '';
  const bgColor = elem.field_key ? (FIELD_COLORS[elem.field_key] ?? 'rgba(200,220,255,0.3)') : 'rgba(200,220,255,0.3)';

  // shape rendering values
  const shapeType  = elem.shape_type ?? 'rect';
  const fillColor  = elem.fill_color ?? 'none';
  const strkColor  = elem.stroke_color ?? '#000000';
  const strkPt     = elem.stroke_width_pt ?? 1;
  const strkPx     = strkPt * 1.333;          // pt → px (72pt = 96px)
  const opacity    = elem.opacity ?? 1;
  // border-radius in SVG viewBox units (viewBox=0 0 1000 1000)
  const rrX = elem.width_mm  > 0 ? ((elem.border_radius_mm ?? 0) / elem.width_mm)  * 1000 : 0;
  const rrY = elem.height_mm > 0 ? ((elem.border_radius_mm ?? 0) / elem.height_mm) * 1000 : 0;

  // Border radius in px for CSS clipping of non-shape content
  const contentRadiusPx = !isShape && elem.border ? px(elem.border.border_radius_mm) : 0;

  return (
    <div
      onMouseDown={handleMouseDown}
      onClick={(e) => e.stopPropagation()}
      style={{
        position: 'absolute',
        left: px(elem.x_mm),
        top: px(elem.y_mm),
        width: px(elem.width_mm),
        height: px(elem.height_mm),
        boxSizing: 'border-box',
        outline: selected ? '2px solid #2563eb' : isShape ? 'none' : '1px dashed #aaa',
        border: 'none',
        cursor: 'move',
        userSelect: 'none',
        overflow: 'visible',
        // Apply borderRadius to outer div so outline also follows the rounded shape
        borderRadius: contentRadiusPx > 0 ? contentRadiusPx : undefined,
      }}
    >
      {isShape ? (
        /* ── SVG shape rendering ── */
        <svg
          width={px(elem.width_mm)}
          height={px(elem.height_mm)}
          viewBox={`0 0 1000 1000`}
          preserveAspectRatio="none"
          style={{ display: 'block', opacity }}
        >
          {shapeType === 'rect' && (
            <rect
              x={strkPx / 2}
              y={strkPx / 2}
              width={1000 - strkPx}
              height={1000 - strkPx}
              rx={rrX}
              ry={rrY}
              fill={fillColor === 'none' ? 'none' : fillColor}
              stroke={strkPt > 0 ? strkColor : 'none'}
              strokeWidth={strkPx}
              vectorEffect="non-scaling-stroke"
            />
          )}
          {shapeType === 'ellipse' && (
            <ellipse
              cx={500}
              cy={500}
              rx={500 - strkPx / 2}
              ry={500 - strkPx / 2}
              fill={fillColor === 'none' ? 'none' : fillColor}
              stroke={strkPt > 0 ? strkColor : 'none'}
              strokeWidth={strkPx}
              vectorEffect="non-scaling-stroke"
            />
          )}
          {shapeType === 'line' && (
            <line
              x1={0}
              y1={500}
              x2={1000}
              y2={500}
              stroke={strkColor}
              strokeWidth={strkPx}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      ) : (
        /* ── Non-shape: content clipped to border radius ── */
        <div
          style={{
            position: 'absolute',
            inset: 0,
            overflow: 'hidden',
            borderRadius: contentRadiusPx > 0 ? contentRadiusPx : undefined,
            backgroundColor: isImage ? bgColor : 'transparent',
          }}
        >
          {isImage ? (
            <div
              style={{
                width: '100%',
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                color: '#555',
                fontWeight: 'bold',
              }}
            >
              {label}
            </div>
          ) : (
            <div
              style={{
                fontFamily: cssFontFamily(elem.font_family),
                fontSize: elem.font_size_pt * 0.8,
                color: elem.font_color,
                fontWeight: elem.bold ? 'bold' : 'normal',
                fontStyle: elem.italic ? 'italic' : 'normal',
                textDecoration: elem.underline ? 'underline' : 'none',
                textAlign: elem.align,
                padding: '2px 4px',
                whiteSpace: 'pre-wrap',
                overflow: 'hidden',
                height: '100%',
              }}
            >
              {elem.type === 'auto_text' ? label : (elem.text || '')}
            </div>
          )}
        </div>
      )}

      {/* Embedded border overlay (for non-shape elements) */}
      {!isShape && elem.border && (() => {
        const b = elem.border;
        const bPx = (b.stroke_width_pt ?? 1) * 1.333;
        const bRrX = elem.width_mm  > 0 ? ((b.border_radius_mm ?? 0) / elem.width_mm)  * 1000 : 0;
        const bRrY = elem.height_mm > 0 ? ((b.border_radius_mm ?? 0) / elem.height_mm) * 1000 : 0;
        return (
          <svg
            width="100%" height="100%"
            viewBox="0 0 1000 1000"
            preserveAspectRatio="none"
            style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none', opacity: b.opacity, zIndex: 5 }}
          >
            <rect
              x={bPx / 2} y={bPx / 2}
              width={1000 - bPx} height={1000 - bPx}
              rx={bRrX} ry={bRrY}
              fill={b.fill_color === 'none' ? 'none' : b.fill_color}
              stroke={b.stroke_width_pt > 0 ? b.stroke_color : 'none'}
              strokeWidth={bPx}
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        );
      })()}

      {/* Edge + corner resize handles (only shown when selected) */}
      {selected && (<>
        {/* Top edge */}
        <div onMouseDown={handleResizeN} style={{ position: 'absolute', top: -4, left: '20%', width: '60%', height: 8, cursor: 'n-resize', zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ width: '100%', height: 4, background: '#2563eb', borderRadius: 2 }} />
        </div>
        {/* Bottom edge */}
        <div onMouseDown={handleResizeS} style={{ position: 'absolute', bottom: -4, left: '20%', width: '60%', height: 8, cursor: 's-resize', zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ width: '100%', height: 4, background: '#2563eb', borderRadius: 2 }} />
        </div>
        {/* Left edge */}
        <div onMouseDown={handleResizeW} style={{ position: 'absolute', left: -4, top: '20%', width: 8, height: '60%', cursor: 'w-resize', zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ height: '100%', width: 4, background: '#2563eb', borderRadius: 2 }} />
        </div>
        {/* Right edge */}
        <div onMouseDown={handleResizeE} style={{ position: 'absolute', right: -4, top: '20%', width: 8, height: '60%', cursor: 'e-resize', zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ height: '100%', width: 4, background: '#2563eb', borderRadius: 2 }} />
        </div>
        {/* SE corner */}
        <div onMouseDown={handleResizeSE} style={{ position: 'absolute', right: -5, bottom: -5, width: 10, height: 10, background: '#2563eb', border: '2px solid #fff', borderRadius: 2, cursor: 'se-resize', zIndex: 11 }} />
      </>)}
    </div>
  );
};

// ─── Main component ───────────────────────────────────────────────────────────

const BadgeEditorPage: React.FC = () => {
  const { competitionId } = useParams<{ competitionId: string }>();
  const navigate = useNavigate();

  const [config, setConfig] = useState<BadgeConfig>({
    width_mm: 90,
    height_mm: 120,
    background_w_mm: 90,
    background_h_mm: 120,
    elements: [],
  });
  const [printPerPage, setPrintPerPage] = useState<4 | 6>(4);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [backgroundUrl, setBackgroundUrl] = useState<string | null>(null);
  // true when backgroundUrl was set from an imported file and hasn't been uploaded to the backend yet
  const [backgroundPendingUpload, setBackgroundPendingUpload] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddMenu, setShowAddMenu] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

  const selectedElem = config.elements.find((e) => e.id === selectedId) ?? null;

  // ── Load template on mount ────────────────────────────────────────────────

  useEffect(() => {
    if (!competitionId) return;
    setLoading(true);
    // Load available custom fonts from backend
    api.get<string[]>('admin/badge-fonts').then(({ data }) => {
      data.forEach((filename) => {
        const name = filename.replace(/\.(ttf|otf)$/i, '');
        loadCustomFont(name);
      });
    }).catch(() => {/* fonts optional */});

    api
      .get<{
        config_json: BadgeConfig;
        print_per_page: number;
        has_background: boolean;
      }>(`admin/competitions/${competitionId}/badge-template`)
      .then(({ data }) => {
        if (data.config_json) {
          const cfg = data.config_json as BadgeConfig;
          setConfig(cfg);
          // Pre-load fonts used in saved template
          cfg.elements?.forEach((el) => {
            if (el.font_family) loadCustomFont(el.font_family);
          });
        }
        setPrintPerPage((data.print_per_page === 6 ? 6 : 4) as 4 | 6);
        if (data.has_background) {
          fetchBackgroundAsDataUrl(competitionId).then(setBackgroundUrl);
        }
      })
      .catch(() => setError('Не удалось загрузить шаблон'))
      .finally(() => setLoading(false));
  }, [competitionId]);

  // ── Keyboard delete ───────────────────────────────────────────────────────

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        const tag = (e.target as HTMLElement).tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        setConfig((prev) => ({ ...prev, elements: prev.elements.filter((el) => el.id !== selectedId) }));
        setSelectedId(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedId]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  const addElement = (type: ElementType, fieldKey?: string, shapeType?: ShapeType) => {
    const elem = defaultElement(type, fieldKey, shapeType);
    setConfig((prev) => ({ ...prev, elements: [...prev.elements, elem] }));
    setSelectedId(elem.id);
    setShowAddMenu(false);
  };

  const updateElement = useCallback((id: string, partial: Partial<BadgeElement>) => {
    setConfig((prev) => ({
      ...prev,
      elements: prev.elements.map((e) => (e.id === id ? { ...e, ...partial } : e)),
    }));
  }, []);

  const deleteSelected = () => {
    if (!selectedId) return;
    setConfig((prev) => ({ ...prev, elements: prev.elements.filter((e) => e.id !== selectedId) }));
    setSelectedId(null);
  };

  const moveLayer = (id: string, dir: -1 | 1) => {
    setConfig((prev) => {
      const idx = prev.elements.findIndex((e) => e.id === id);
      if (idx < 0) return prev;
      const next = [...prev.elements];
      const target = idx + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      return { ...prev, elements: next };
    });
  };

  // ── Export / Import (.bdsm) ───────────────────────────────────────────────

  const handleExportTemplate = () => {
    const payload: Record<string, unknown> = {
      version: 1,
      config_json: config,
      print_per_page: printPerPage,
    };
    if (backgroundUrl) {
      payload.background_image = backgroundUrl; // already a data URL (base64)
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'badge_template.bdsm';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportTemplate = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const raw = JSON.parse(reader.result as string);
        const cfg: BadgeConfig = raw.config_json ?? raw;
        if (!cfg.elements || !Array.isArray(cfg.elements)) {
          setError('Неверный формат файла шаблона');
          return;
        }
        setConfig({
          width_mm: cfg.width_mm ?? 90,
          height_mm: cfg.height_mm ?? 120,
          background_w_mm: cfg.background_w_mm ?? cfg.width_mm ?? 90,
          background_h_mm: cfg.background_h_mm ?? cfg.height_mm ?? 120,
          elements: cfg.elements,
        });
        if (raw.print_per_page) {
          setPrintPerPage(raw.print_per_page === 6 ? 6 : 4);
        }
        // Restore background image from embedded data URL
        if (raw.background_image) {
          setBackgroundUrl(raw.background_image as string);
          setBackgroundPendingUpload(true);
        } else {
          setBackgroundPendingUpload(false);
        }
        cfg.elements.forEach((el) => {
          if (el.font_family) loadCustomFont(el.font_family);
        });
        setSelectedId(null);
        setError(null);
      } catch {
        setError('Ошибка чтения файла шаблона');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  // ── Save ──────────────────────────────────────────────────────────────────

  const handleSave = async () => {
    if (!competitionId) return;
    setSaving(true);
    setError(null);
    try {
      // 1. Upload pending background (imported from .bdsm) before saving config
      if (backgroundPendingUpload && backgroundUrl) {
        const res = await fetch(backgroundUrl);
        const blob = await res.blob();
        const form = new FormData();
        form.append('file', blob, 'background.png');
        await api.post(
          `admin/competitions/${competitionId}/badge-template/background`,
          form,
          { headers: { 'Content-Type': 'multipart/form-data' } },
        );
        setBackgroundPendingUpload(false);
      }
      // 2. Save config
      await api.post(`admin/competitions/${competitionId}/badge-template`, {
        config_json: config,
        print_per_page: printPerPage,
      });
    } catch {
      setError('Ошибка при сохранении');
    } finally {
      setSaving(false);
    }
  };

  const handleBackgroundUpload = async (file: File) => {
    if (!competitionId) return;
    const form = new FormData();
    form.append('file', file);
    try {
      await api.post(`admin/competitions/${competitionId}/badge-template/background`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const dataUrl = await fetchBackgroundAsDataUrl(competitionId);
      setBackgroundUrl(dataUrl);
      setBackgroundPendingUpload(false); // uploaded directly, no pending
      setConfig((prev) => ({
        ...prev,
        background_w_mm: prev.width_mm,
        background_h_mm: prev.height_mm,
      }));
    } catch {
      setError('Ошибка загрузки фона');
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <Layout>
        <div style={{ padding: 40, textAlign: 'center' }}>Загрузка шаблона…</div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

        {/* ── Toolbar ────────────────────────────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 8,
            alignItems: 'center',
            padding: '10px 16px',
            borderBottom: '1px solid #e2e8f0',
            background: '#f8fafc',
          }}
        >
          <Button variant="secondary" onClick={() => navigate('/admin/competitions')}>
            ← Назад
          </Button>

          <span style={{ fontWeight: 600, marginRight: 8 }}>Редактор бейджа</span>

          {/* Badge size */}
          <label style={{ fontSize: 13 }}>Ширина, мм:</label>
          <input
            type="number"
            min={20}
            max={300}
            value={config.width_mm}
            onChange={(e) =>
              setConfig((prev) => ({ ...prev, width_mm: Number(e.target.value) }))
            }
            style={{ width: 60, padding: '4px 6px', border: '1px solid #cbd5e1', borderRadius: 4 }}
          />
          <label style={{ fontSize: 13 }}>Высота, мм:</label>
          <input
            type="number"
            min={20}
            max={400}
            value={config.height_mm}
            onChange={(e) =>
              setConfig((prev) => ({ ...prev, height_mm: Number(e.target.value) }))
            }
            style={{ width: 60, padding: '4px 6px', border: '1px solid #cbd5e1', borderRadius: 4 }}
          />

          {/* Add element dropdown */}
          <div style={{ position: 'relative' }}>
            <Button onClick={() => setShowAddMenu((v) => !v)}>+ Добавить ▾</Button>
            {showAddMenu && (
              <div
                style={{
                  position: 'absolute',
                  top: '100%',
                  left: 0,
                  zIndex: 100,
                  background: '#fff',
                  border: '1px solid #e2e8f0',
                  borderRadius: 6,
                  boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
                  minWidth: 200,
                  padding: 4,
                }}
              >
                <MenuGroup label="Авто-поля (текст)">
                  {AUTO_FIELD_KEYS.map((key) => (
                    <MenuItem key={key} onClick={() => addElement('auto_text', key)}>
                      {FIELD_LABELS[key]}
                    </MenuItem>
                  ))}
                </MenuGroup>
                <MenuGroup label="Авто-поля (изображения)">
                  {IMAGE_FIELD_KEYS.map((key) => (
                    <MenuItem key={key} onClick={() => addElement('image', key)}>
                      {FIELD_LABELS[key]}
                    </MenuItem>
                  ))}
                </MenuGroup>
                <MenuGroup label="Произвольный текст">
                  <MenuItem onClick={() => addElement('custom_text')}>Текстовый блок</MenuItem>
                </MenuGroup>
                <MenuGroup label="Фигуры">
                  {SHAPE_TYPES.map((s) => (
                    <MenuItem key={s.value} onClick={() => addElement('shape', undefined, s.value)}>
                      {s.label}
                    </MenuItem>
                  ))}
                </MenuGroup>
              </div>
            )}
          </div>

          {/* Background image */}
          <label style={{ fontSize: 13, cursor: 'pointer', color: '#2563eb', textDecoration: 'underline' }}>
            {backgroundUrl ? 'Заменить фон' : 'Загрузить фон'}
            <input
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleBackgroundUpload(f);
              }}
            />
          </label>
          {backgroundUrl && (
            <button
              onClick={() => setBackgroundUrl(null)}
              style={{ fontSize: 12, color: '#e53e3e', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              Убрать фон
            </button>
          )}

          {/* Background size */}
          {backgroundUrl && (
            <>
              <label style={{ fontSize: 13 }}>Фон Ш, мм:</label>
              <input
                type="number"
                min={10}
                max={500}
                value={config.background_w_mm}
                onChange={(e) =>
                  setConfig((prev) => ({ ...prev, background_w_mm: Number(e.target.value) }))
                }
                style={{ width: 60, padding: '4px 6px', border: '1px solid #cbd5e1', borderRadius: 4 }}
              />
              <label style={{ fontSize: 13 }}>В, мм:</label>
              <input
                type="number"
                min={10}
                max={500}
                value={config.background_h_mm}
                onChange={(e) =>
                  setConfig((prev) => ({ ...prev, background_h_mm: Number(e.target.value) }))
                }
                style={{ width: 60, padding: '4px 6px', border: '1px solid #cbd5e1', borderRadius: 4 }}
              />
            </>
          )}

          {/* Per page */}
          <label style={{ fontSize: 13 }}>На листе:</label>
          <select
            value={printPerPage}
            onChange={(e) => setPrintPerPage(Number(e.target.value) as 4 | 6)}
            style={{ padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: 4 }}
          >
            <option value={4}>4 (2×2)</option>
            <option value={6}>6 (2×3)</option>
          </select>

          <Button onClick={handleSave} loading={saving}>
            Сохранить
          </Button>

          <Button variant="secondary" onClick={handleExportTemplate}>
            Экспорт .bdsm
          </Button>

          <label style={{ cursor: 'pointer' }}>
            <Button variant="secondary" onClick={() => importInputRef.current?.click()}>
              Импорт .bdsm
            </Button>
            <input
              ref={importInputRef}
              type="file"
              accept=".bdsm,.json"
              style={{ display: 'none' }}
              onChange={handleImportTemplate}
            />
          </label>

          {backgroundPendingUpload && (
            <span style={{ fontSize: 12, color: '#d97706' }}>
              ⚠ Фон из файла — будет загружен при сохранении
            </span>
          )}

          {error && <span style={{ color: 'red', fontSize: 13 }}>{error}</span>}
        </div>

        {/* ── Main area ──────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', flex: 1, overflow: 'auto', gap: 0 }}>

          {/* Canvas */}
          <div
            style={{
              flex: 1,
              padding: 24,
              background: '#e8edf2',
              overflow: 'auto',
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'center',
            }}
            onClick={() => {
              setSelectedId(null);
              setShowAddMenu(false);
            }}
          >
            <div
              ref={canvasRef}
              style={{
                position: 'relative',
                width: px(config.width_mm),
                height: px(config.height_mm),
                background: '#fff',
                boxShadow: '0 2px 16px rgba(0,0,0,0.18)',
                overflow: 'hidden',
                flexShrink: 0,
              }}
            >
              {/* Background image */}
              {backgroundUrl && (
                <img
                  src={backgroundUrl}
                  alt="фон"
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: px(config.background_w_mm),
                    height: px(config.background_h_mm),
                    objectFit: 'fill',
                    pointerEvents: 'none',
                  }}
                />
              )}

              {/* Elements */}
              {config.elements.map((elem) => (
                <ElementBox
                  key={elem.id}
                  elem={elem}
                  selected={selectedId === elem.id}
                  onSelect={() => setSelectedId(elem.id)}
                  onChange={(partial) => updateElement(elem.id, partial)}
                />
              ))}
            </div>
          </div>

          {/* Properties panel */}
          <div
            style={{
              width: 280,
              borderLeft: '1px solid #e2e8f0',
              background: '#fff',
              padding: 16,
              overflowY: 'auto',
              flexShrink: 0,
            }}
          >
            {selectedElem ? (
              <PropertiesPanel
                elem={selectedElem}
                onChange={(partial) => updateElement(selectedElem.id, partial)}
                onDelete={deleteSelected}
                onMoveUp={() => moveLayer(selectedElem.id, 1)}
                onMoveDown={() => moveLayer(selectedElem.id, -1)}
              />
            ) : (
              <div style={{ color: '#999', fontSize: 13 }}>
                Выберите элемент для редактирования
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
};

// ─── Properties panel ─────────────────────────────────────────────────────────

interface PropertiesPanelProps {
  elem: BadgeElement;
  onChange: (partial: Partial<BadgeElement>) => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

const SHAPE_LABELS: Record<ShapeType, string> = {
  rect: 'Прямоугольник',
  ellipse: 'Эллипс',
  line: 'Линия',
};

const PropertiesPanel: React.FC<PropertiesPanelProps> = ({
  elem,
  onChange,
  onDelete,
  onMoveUp,
  onMoveDown,
}) => {
  const isText  = elem.type === 'auto_text' || elem.type === 'custom_text';
  const isShape = elem.type === 'shape';

  const title =
    elem.type === 'auto_text'  ? `Авто-поле: ${FIELD_LABELS[elem.field_key ?? ''] ?? elem.field_key}` :
    elem.type === 'custom_text'? 'Текстовый блок' :
    elem.type === 'shape'      ? `Фигура: ${SHAPE_LABELS[elem.shape_type ?? 'rect']}` :
                                 `Изображение: ${FIELD_LABELS[elem.field_key ?? ''] ?? elem.field_key}`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>{title}</div>

      {/* Position & size */}
      <Section label="Позиция и размер">
        <Row>
          <SmallField label="X, мм" value={elem.x_mm} onChange={(v) => onChange({ x_mm: v })} />
          <SmallField label="Y, мм" value={elem.y_mm} onChange={(v) => onChange({ y_mm: v })} />
        </Row>
        <Row>
          <SmallField label="Ш, мм" value={elem.width_mm} onChange={(v) => onChange({ width_mm: v })} />
          <SmallField label="В, мм" value={elem.height_mm} onChange={(v) => onChange({ height_mm: v })} />
        </Row>
      </Section>

      {/* Shape properties */}
      {isShape && (
        <Section label="Фигура">
          <div>
            <label style={labelStyle}>Тип фигуры</label>
            <select
              value={elem.shape_type ?? 'rect'}
              onChange={(e) => onChange({ shape_type: e.target.value as ShapeType })}
              style={selectStyle}
            >
              {SHAPE_TYPES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          {(elem.shape_type ?? 'rect') !== 'line' && (
            <Row>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>Заливка</label>
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                  <input
                    type="color"
                    value={elem.fill_color === 'none' ? '#ffffff' : (elem.fill_color ?? '#ffffff')}
                    onChange={(e) => onChange({ fill_color: e.target.value })}
                    disabled={elem.fill_color === 'none'}
                    style={{ flex: 1, height: 30, padding: 2, border: '1px solid #cbd5e1', borderRadius: 4, cursor: 'pointer', opacity: elem.fill_color === 'none' ? 0.4 : 1 }}
                  />
                  <button
                    title="Прозрачная заливка"
                    onClick={() => onChange({ fill_color: elem.fill_color === 'none' ? '#ffffff' : 'none' })}
                    style={{ padding: '3px 6px', fontSize: 11, border: '1px solid #cbd5e1', borderRadius: 4, background: elem.fill_color === 'none' ? '#2563eb' : '#fff', color: elem.fill_color === 'none' ? '#fff' : '#333', cursor: 'pointer', whiteSpace: 'nowrap' }}
                  >
                    Нет
                  </button>
                </div>
              </div>
            </Row>
          )}

          <Row>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Обводка</label>
              <input
                type="color"
                value={elem.stroke_color ?? '#000000'}
                onChange={(e) => onChange({ stroke_color: e.target.value })}
                style={{ width: '100%', height: 30, padding: 2, border: '1px solid #cbd5e1', borderRadius: 4, cursor: 'pointer' }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Толщина, пт</label>
              <input
                type="number"
                min={0}
                max={20}
                step={0.5}
                value={elem.stroke_width_pt ?? 1}
                onChange={(e) => onChange({ stroke_width_pt: Number(e.target.value) })}
                style={{ ...inputStyle, width: '100%' }}
              />
            </div>
          </Row>

          {(elem.shape_type ?? 'rect') === 'rect' && (
            <div>
              <label style={labelStyle}>Скругление углов, мм</label>
              <input
                type="number"
                min={0}
                step={0.5}
                value={elem.border_radius_mm ?? 0}
                onChange={(e) => onChange({ border_radius_mm: Number(e.target.value) })}
                style={{ ...inputStyle, width: '100%' }}
              />
            </div>
          )}

          <div>
            <label style={labelStyle}>Прозрачность: {Math.round((elem.opacity ?? 1) * 100)}%</label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={elem.opacity ?? 1}
              onChange={(e) => onChange({ opacity: Number(e.target.value) })}
              style={{ width: '100%' }}
            />
          </div>
        </Section>
      )}

      {/* Text formatting */}
      {isText && (
        <Section label="Текст">
          {elem.type === 'custom_text' && (
            <div>
              <label style={labelStyle}>Текст</label>
              <textarea
                value={elem.text ?? ''}
                onChange={(e) => onChange({ text: e.target.value })}
                rows={3}
                style={{ width: '100%', padding: 6, border: '1px solid #cbd5e1', borderRadius: 4, fontSize: 13, resize: 'vertical' }}
              />
            </div>
          )}

          <div>
            <label style={labelStyle}>Шрифт</label>
            <select
              value={elem.font_family}
              onChange={(e) => {
                const name = e.target.value;
                loadCustomFont(name);
                onChange({ font_family: name });
              }}
              style={selectStyle}
            >
              {FONT_FAMILIES.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>

          <Row>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Кегль, пт</label>
              <input
                type="number"
                min={6}
                max={144}
                value={elem.font_size_pt}
                onChange={(e) => onChange({ font_size_pt: Number(e.target.value) })}
                style={{ ...inputStyle, width: '100%' }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Цвет</label>
              <input
                type="color"
                value={elem.font_color}
                onChange={(e) => onChange({ font_color: e.target.value })}
                style={{ width: '100%', height: 34, padding: 2, border: '1px solid #cbd5e1', borderRadius: 4, cursor: 'pointer' }}
              />
            </div>
          </Row>

          {/* Bold / Italic / Underline */}
          <div style={{ display: 'flex', gap: 6 }}>
            <ToggleBtn active={elem.bold} onClick={() => onChange({ bold: !elem.bold })} label="B" title="Жирный" bold />
            <ToggleBtn active={elem.italic} onClick={() => onChange({ italic: !elem.italic })} label="I" title="Курсив" italic />
            <ToggleBtn active={elem.underline} onClick={() => onChange({ underline: !elem.underline })} label="U" title="Подчёркнутый" underline />
          </div>

          {/* Alignment */}
          <div>
            <label style={labelStyle}>Выравнивание</label>
            <div style={{ display: 'flex', gap: 6 }}>
              {(['left', 'center', 'right'] as AlignType[]).map((a) => (
                <button
                  key={a}
                  onClick={() => onChange({ align: a })}
                  title={a === 'left' ? 'По левому краю' : a === 'center' ? 'По центру' : 'По правому краю'}
                  style={{
                    flex: 1,
                    padding: '4px 0',
                    border: '1px solid #cbd5e1',
                    borderRadius: 4,
                    background: elem.align === a ? '#2563eb' : '#fff',
                    color: elem.align === a ? '#fff' : '#333',
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  {a === 'left' ? '◄' : a === 'center' ? '═' : '►'}
                </button>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* Embedded border (non-shape elements only) */}
      {!isShape && (
        <Section label="Рамка">
          {elem.border ? (
            <>
              <Row>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Цвет обводки</label>
                  <input
                    type="color"
                    value={elem.border.stroke_color}
                    onChange={(e) => onChange({ border: { ...elem.border!, stroke_color: e.target.value } })}
                    style={{ width: '100%', height: 30, padding: 2, border: '1px solid #cbd5e1', borderRadius: 4, cursor: 'pointer' }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Толщина, пт</label>
                  <input
                    type="number" min={0} max={20} step={0.5}
                    value={elem.border.stroke_width_pt}
                    onChange={(e) => onChange({ border: { ...elem.border!, stroke_width_pt: Number(e.target.value) } })}
                    style={{ ...inputStyle, width: '100%' }}
                  />
                </div>
              </Row>
              <div>
                <label style={labelStyle}>Скругление углов, мм</label>
                <input
                  type="number" min={0} step={0.5}
                  value={elem.border.border_radius_mm}
                  onChange={(e) => onChange({ border: { ...elem.border!, border_radius_mm: Number(e.target.value) } })}
                  style={{ ...inputStyle, width: '100%' }}
                />
              </div>
              <div>
                <label style={labelStyle}>Заливка рамки</label>
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                  <input
                    type="color"
                    value={elem.border.fill_color === 'none' ? '#ffffff' : elem.border.fill_color}
                    disabled={elem.border.fill_color === 'none'}
                    onChange={(e) => onChange({ border: { ...elem.border!, fill_color: e.target.value } })}
                    style={{ flex: 1, height: 30, padding: 2, border: '1px solid #cbd5e1', borderRadius: 4, cursor: 'pointer', opacity: elem.border.fill_color === 'none' ? 0.4 : 1 }}
                  />
                  <button
                    title="Прозрачная заливка"
                    onClick={() => onChange({ border: { ...elem.border!, fill_color: elem.border!.fill_color === 'none' ? '#ffffff' : 'none' } })}
                    style={{ padding: '3px 6px', fontSize: 11, border: '1px solid #cbd5e1', borderRadius: 4, background: elem.border.fill_color === 'none' ? '#2563eb' : '#fff', color: elem.border.fill_color === 'none' ? '#fff' : '#333', cursor: 'pointer' }}
                  >
                    Нет
                  </button>
                </div>
              </div>
              <div>
                <label style={labelStyle}>Прозрачность: {Math.round((elem.border.opacity ?? 1) * 100)}%</label>
                <input
                  type="range" min={0} max={1} step={0.05}
                  value={elem.border.opacity}
                  onChange={(e) => onChange({ border: { ...elem.border!, opacity: Number(e.target.value) } })}
                  style={{ width: '100%' }}
                />
              </div>
              <button
                onClick={() => onChange({ border: undefined })}
                style={{ padding: '5px 8px', border: '1px solid #fca5a5', borderRadius: 4, background: '#fff1f2', color: '#b91c1c', cursor: 'pointer', fontSize: 12 }}
              >
                Удалить рамку
              </button>
            </>
          ) : (
            <button
              onClick={() => onChange({ border: { stroke_color: '#000000', stroke_width_pt: 1, border_radius_mm: 0, fill_color: 'none', opacity: 1 } })}
              style={{ width: '100%', padding: '5px 8px', border: '1px solid #cbd5e1', borderRadius: 4, background: '#f0f9ff', color: '#0369a1', cursor: 'pointer', fontSize: 12, textAlign: 'left' }}
            >
              + Добавить рамку
            </button>
          )}
        </Section>
      )}

      {/* Layer order */}
      <Section label="Порядок слоёв">
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={onMoveUp} style={layerBtnStyle} title="Выше">↑ Выше</button>
          <button onClick={onMoveDown} style={layerBtnStyle} title="Ниже">↓ Ниже</button>
        </div>
      </Section>

      {/* Delete */}
      <button
        onClick={onDelete}
        style={{
          padding: '8px 12px',
          background: '#fee2e2',
          color: '#b91c1c',
          border: '1px solid #fca5a5',
          borderRadius: 6,
          cursor: 'pointer',
          fontSize: 13,
          fontWeight: 600,
        }}
      >
        Удалить элемент
      </button>
    </div>
  );
};

// ─── Small UI helpers ─────────────────────────────────────────────────────────

const Section: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <div style={{ fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
      {label}
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{children}</div>
  </div>
);

const Row: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ display: 'flex', gap: 8 }}>{children}</div>
);

const SmallField: React.FC<{ label: string; value: number; onChange: (v: number) => void }> = ({
  label,
  value,
  onChange,
}) => (
  <div style={{ flex: 1 }}>
    <label style={labelStyle}>{label}</label>
    <input
      type="number"
      step={0.5}
      value={Math.round(value * 10) / 10}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{ ...inputStyle, width: '100%' }}
    />
  </div>
);

const ToggleBtn: React.FC<{
  active: boolean;
  onClick: () => void;
  label: string;
  title: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
}> = ({ active, onClick, label, title, bold, italic, underline }) => (
  <button
    onClick={onClick}
    title={title}
    style={{
      width: 36,
      height: 32,
      border: '1px solid #cbd5e1',
      borderRadius: 4,
      background: active ? '#2563eb' : '#fff',
      color: active ? '#fff' : '#333',
      cursor: 'pointer',
      fontWeight: bold ? 'bold' : 'normal',
      fontStyle: italic ? 'italic' : 'normal',
      textDecoration: underline ? 'underline' : 'none',
      fontSize: 14,
    }}
  >
    {label}
  </button>
);

const MenuGroup: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <div style={{ fontSize: 11, color: '#94a3b8', padding: '4px 10px', fontWeight: 600 }}>{label}</div>
    {children}
  </div>
);

const MenuItem: React.FC<{ onClick: () => void; children: React.ReactNode }> = ({ onClick, children }) => (
  <button
    onClick={onClick}
    style={{
      display: 'block',
      width: '100%',
      textAlign: 'left',
      padding: '6px 14px',
      background: 'none',
      border: 'none',
      cursor: 'pointer',
      fontSize: 13,
      color: '#1e293b',
      borderRadius: 4,
    }}
    onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.background = '#f1f5f9')}
    onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.background = 'none')}
  >
    {children}
  </button>
);

// ─── Styles ───────────────────────────────────────────────────────────────────

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 12,
  color: '#64748b',
  marginBottom: 3,
};

const inputStyle: React.CSSProperties = {
  padding: '4px 8px',
  border: '1px solid #cbd5e1',
  borderRadius: 4,
  fontSize: 13,
};

const selectStyle: React.CSSProperties = {
  width: '100%',
  padding: '5px 8px',
  border: '1px solid #cbd5e1',
  borderRadius: 4,
  fontSize: 13,
};

const layerBtnStyle: React.CSSProperties = {
  flex: 1,
  padding: '5px 8px',
  border: '1px solid #cbd5e1',
  borderRadius: 4,
  background: '#f8fafc',
  cursor: 'pointer',
  fontSize: 12,
};

export default BadgeEditorPage;
