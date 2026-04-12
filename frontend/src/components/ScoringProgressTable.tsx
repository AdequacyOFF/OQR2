import React, { useEffect, useRef, useState } from 'react';
import api from '../api/client';
import { ScoringProgressItem, ScoringProgressResponse, TourTimeItem } from '../types';
import { toRoman } from '../utils/roman';

interface Props {
  competitionId: string;
  highlightAttemptId?: string;
  refreshTrigger: number;
  onTourTimesLoaded?: (tourTimes: TourTimeItem[]) => void;
}

interface SortKey {
  col: string;
  dir: 'asc' | 'desc';
}

const MODE_LABELS: Record<string, string> = {
  individual: 'Личный зачет',
  individual_captains: 'Капитанское',
  team: 'Командный',
};

function getTourTotal(item: ScoringProgressItem, tourNum: number): number | null {
  const tour = item.tours.find((t) => t.tour_number === tourNum);
  return tour?.tour_total ?? null;
}

function compareValues(a: unknown, b: unknown): number {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === 'string' && typeof b === 'string') {
    return a.localeCompare(b, 'ru');
  }
  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }
  return 0;
}

function getColValue(item: ScoringProgressItem, col: string): unknown {
  if (col === 'name') return item.participant_name;
  if (col === 'school') return item.participant_school;
  if (col === 'variant') return item.variant_number;
  if (col === 'total') return item.score_total;
  if (col.startsWith('tour_')) {
    const tourNum = parseInt(col.slice(5), 10);
    return getTourTotal(item, tourNum);
  }
  return null;
}

function sortItems(items: ScoringProgressItem[], sortKeys: SortKey[]): ScoringProgressItem[] {
  if (sortKeys.length === 0) return items;
  return [...items].sort((a, b) => {
    for (const key of sortKeys) {
      const va = getColValue(a, key.col);
      const vb = getColValue(b, key.col);
      const cmp = compareValues(va, vb);
      if (cmp !== 0) return key.dir === 'asc' ? cmp : -cmp;
    }
    return 0;
  });
}

const ScoringProgressTable: React.FC<Props> = ({
  competitionId,
  highlightAttemptId,
  refreshTrigger,
  onTourTimesLoaded,
}) => {
  const [data, setData] = useState<ScoringProgressResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortKeys, setSortKeys] = useState<SortKey[]>([]);
  const highlightRef = useRef<HTMLTableRowElement | null>(null);

  const fetchProgress = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data: res } = await api.get<ScoringProgressResponse>(
        `admin/competitions/${competitionId}/scoring-progress`
      );
      setData(res);
      if (onTourTimesLoaded && res.tour_times) {
        onTourTimesLoaded(res.tour_times);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err?.response?.data?.detail ?? 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProgress();
  }, [competitionId, refreshTrigger]);

  // Auto-poll every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchProgress, 30000);
    return () => clearInterval(interval);
  }, [competitionId]);

  // Scroll highlighted row into view
  useEffect(() => {
    if (highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [highlightAttemptId, data]);

  const handleHeaderClick = (col: string, e: React.MouseEvent) => {
    if (e.shiftKey) {
      // Secondary sort
      setSortKeys((prev) => {
        const existing = prev.findIndex((k) => k.col === col);
        if (existing === 0) {
          // Primary → toggle direction as secondary doesn't make sense, just toggle primary
          return [{ col, dir: prev[0].dir === 'asc' ? 'desc' : 'asc' }];
        }
        if (existing === 1) {
          // Already secondary → toggle direction
          const next = [...prev];
          next[1] = { col, dir: prev[1].dir === 'asc' ? 'desc' : 'asc' };
          return next;
        }
        // Add as secondary (replace if there's already a secondary)
        return [prev[0] ?? { col, dir: 'asc' }, { col, dir: 'asc' }];
      });
    } else {
      setSortKeys((prev) => {
        if (prev.length > 0 && prev[0].col === col) {
          return [{ col, dir: prev[0].dir === 'asc' ? 'desc' : 'asc' }];
        }
        return [{ col, dir: 'asc' }];
      });
    }
  };

  const getSortIndicator = (col: string): React.ReactNode => {
    const idx = sortKeys.findIndex((k) => k.col === col);
    if (idx === -1) return null;
    const key = sortKeys[idx];
    const arrow = key.dir === 'asc' ? '▲' : '▼';
    const badge = sortKeys.length > 1 ? (
      <sup style={{ fontSize: 9, marginLeft: 1 }}>{idx + 1}</sup>
    ) : null;
    return (
      <span style={{ marginLeft: 4, color: '#2563eb' }}>
        {arrow}{badge}
      </span>
    );
  };

  if (error) {
    return (
      <div className="alert alert-error" style={{ margin: 0 }}>
        {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: 16, color: '#888', fontSize: 13 }}>
        {loading ? 'Загрузка таблицы...' : null}
      </div>
    );
  }

  const scored = data.items.filter((i) => i.score_total !== null).length;
  const total = data.total;

  const tourColumns = data.is_special && data.tours_count > 0
    ? Array.from({ length: data.tours_count }, (_, i) => i + 1)
    : [];

  // Build lookup: tour_number → TourTimeItem
  const tourTimeMap: Record<number, TourTimeItem> = {};
  for (const tt of (data.tour_times ?? [])) {
    tourTimeMap[tt.tour_number] = tt;
  }

  // Build tour config lookup
  const tourConfigMap: Record<number, { mode: string }> = {};
  for (const tc of (data.tour_configs ?? [])) {
    tourConfigMap[tc.tour_number] = tc;
  }

  const sortedItems = sortItems(data.items, sortKeys);

  const makeTh = (col: string, label: React.ReactNode, style?: React.CSSProperties) => (
    <th
      key={col}
      onClick={(e) => handleHeaderClick(col, e)}
      style={{
        ...thStyle,
        ...style,
        cursor: 'pointer',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
      title="Нажмите для сортировки. Shift+клик — вторичная сортировка"
    >
      {label}{getSortIndicator(col)}
    </th>
  );

  return (
    <div style={{ overflowX: 'auto' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
          padding: '0 2px',
        }}
      >
        <div style={{ fontWeight: 600, fontSize: 15 }}>
          {data.competition_name}
        </div>
        <div style={{ fontSize: 13, color: '#555' }}>
          Внесено:{' '}
          <span style={{ fontWeight: 700, color: scored === total ? '#15803d' : '#2563eb' }}>
            {scored}
          </span>
          {' / '}
          {total}
          {loading && (
            <span style={{ marginLeft: 8, color: '#aaa' }}>↻</span>
          )}
        </div>
      </div>

      {sortKeys.length > 0 && (
        <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6, paddingLeft: 2 }}>
          Сортировка: {sortKeys.map((k, i) => {
            const labels: Record<string, string> = {
              name: 'ФИО', school: 'Школа', variant: 'Вар.', total: 'Итог',
            };
            const label = k.col.startsWith('tour_')
              ? `Тур ${toRoman(k.col.slice(5))}`
              : (labels[k.col] ?? k.col);
            return (
              <span key={k.col}>
                {i > 0 && ' → '}
                <strong>{label}</strong> {k.dir === 'asc' ? '▲' : '▼'}
              </span>
            );
          })}
          {' '}
          <button
            onClick={() => setSortKeys([])}
            style={{
              marginLeft: 6,
              fontSize: 11,
              color: '#9ca3af',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '0 2px',
            }}
          >
            ✕ сбросить
          </button>
        </div>
      )}

      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 13,
          tableLayout: 'auto',
        }}
      >
        <thead>
          <tr style={{ background: '#f3f4f6', borderBottom: '2px solid #e5e7eb' }}>
            {makeTh('name', 'Участник')}
            {makeTh('school', 'Школа')}
            {makeTh('variant', 'Вар.', { textAlign: 'center' })}
            {data.is_special && tourColumns.map((t) => {
              const tt = tourTimeMap[t];
              const cfg = tourConfigMap[t];
              const modeLabel = cfg ? MODE_LABELS[cfg.mode] : null;
              return makeTh(`tour_${t}`, (
                <div>
                  <div>Тур {toRoman(t)}</div>
                  {modeLabel && (
                    <div style={{ fontSize: 10, fontWeight: 400, color: '#6b7280' }}>
                      {modeLabel}
                    </div>
                  )}
                  {tt?.duration_minutes != null && (
                    <div style={{ fontSize: 10, fontWeight: 400, color: '#6b7280' }}>
                      {tt.duration_minutes} мин
                    </div>
                  )}
                </div>
              ), { textAlign: 'center' });
            })}
            {makeTh('total', 'Итог', { textAlign: 'center' })}
            <th style={{ ...thStyle, textAlign: 'center' }}>Статус</th>
          </tr>
        </thead>
        <tbody>
          {sortedItems.map((item) => {
            const isHighlighted = item.attempt_id === highlightAttemptId;
            const isScored = item.score_total !== null;
            return (
              <tr
                key={item.registration_id}
                ref={isHighlighted ? highlightRef : null}
                style={{
                  background: isHighlighted
                    ? '#fef9c3'
                    : isScored
                    ? '#f0fdf4'
                    : 'white',
                  borderBottom: '1px solid #e5e7eb',
                  transition: 'background 0.3s',
                }}
              >
                <td style={tdStyle}>{item.participant_name}</td>
                <td style={{ ...tdStyle, color: '#555', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.participant_school}
                </td>
                <td style={{ ...tdStyle, textAlign: 'center', color: '#6b7280' }}>
                  {item.variant_number ?? '—'}
                </td>
                {data.is_special && tourColumns.map((tourNum) => {
                  const tour = item.tours.find((t) => t.tour_number === tourNum);
                  const taskEntries = tour?.task_scores
                    ? Object.entries(tour.task_scores).sort(([a], [b]) => Number(a) - Number(b))
                    : null;
                  return (
                    <td
                      key={tourNum}
                      style={{
                        ...tdStyle,
                        textAlign: 'center',
                        fontWeight: tour?.tour_total != null ? 600 : 400,
                        color: tour?.tour_total != null ? '#15803d' : '#9ca3af',
                      }}
                    >
                      <div>{tour?.tour_total != null ? tour.tour_total : '—'}</div>
                      {taskEntries && taskEntries.length > 0 && (
                        <div style={{ fontSize: 10, fontWeight: 400, color: '#9ca3af', marginTop: 2 }}>
                          {taskEntries.map(([k, v]) => `${k}:${v}`).join(' ')}
                        </div>
                      )}
                    </td>
                  );
                })}
                <td
                  style={{
                    ...tdStyle,
                    textAlign: 'center',
                    fontWeight: 700,
                    color: isScored ? '#15803d' : '#9ca3af',
                  }}
                >
                  {isScored ? item.score_total : '—'}
                </td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  {isScored ? (
                    <span
                      title="Баллы внесены"
                      style={{
                        display: 'inline-block',
                        width: 20,
                        height: 20,
                        borderRadius: '50%',
                        background: '#22c55e',
                        color: 'white',
                        lineHeight: '20px',
                        fontSize: 12,
                        fontWeight: 700,
                      }}
                    >
                      ✓
                    </span>
                  ) : (
                    <span
                      title="Баллы не внесены"
                      style={{
                        display: 'inline-block',
                        width: 20,
                        height: 20,
                        borderRadius: '50%',
                        background: '#e5e7eb',
                      }}
                    />
                  )}
                </td>
              </tr>
            );
          })}
          {data.items.length === 0 && (
            <tr>
              <td
                colSpan={4 + tourColumns.length}
                style={{ textAlign: 'center', padding: 24, color: '#9ca3af' }}
              >
                Нет участников
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

const thStyle: React.CSSProperties = {
  padding: '8px 10px',
  textAlign: 'left',
  fontWeight: 600,
  fontSize: 12,
  color: '#374151',
  whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  padding: '7px 10px',
  verticalAlign: 'middle',
};

export default ScoringProgressTable;
