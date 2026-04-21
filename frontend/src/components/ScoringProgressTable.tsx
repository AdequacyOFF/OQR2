import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { ScoringProgressItem, ScoringProgressResponse, TourConfig, TourTimeItem } from '../types';
import { toRoman } from '../utils/roman';

type FilterMode = 'all' | 'personal_1' | 'personal_2' | 'personal_12' | 'team';

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

function parseTourTimeToSeconds(timeStr: string | null | undefined): number | null {
  if (!timeStr) return null;
  const parts = timeStr.split('.');
  if (parts.length !== 3) return null;
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  const s = parseInt(parts[2], 10);
  if (isNaN(h) || isNaN(m) || isNaN(s)) return null;
  return h * 3600 + m * 60 + s;
}

function getTotalTimeSeconds(item: ScoringProgressItem): number | null {
  let total = 0;
  let hasAny = false;
  for (const tour of item.tours) {
    const secs = parseTourTimeToSeconds(tour.tour_time);
    if (secs !== null) {
      total += secs;
      hasAny = true;
    }
  }
  return hasAny ? total : null;
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
      // Time tiebreaker: when scores are equal, prefer less time (ascending)
      if (key.col === 'total' || key.col.startsWith('tour_')) {
        const ta = getTotalTimeSeconds(a);
        const tb = getTotalTimeSeconds(b);
        const timeCmp = compareValues(ta, tb);
        if (timeCmp !== 0) return timeCmp; // ascending: less time = higher rank
      }
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
  const [sortKeys, setSortKeys] = useState<SortKey[]>([{ col: 'total', dir: 'desc' }]);
  const [filterMode, setFilterMode] = useState<FilterMode>('all');
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
  const tourConfigMap: Record<number, TourConfig> = {};
  for (const tc of (data.tour_configs ?? [])) {
    tourConfigMap[tc.tour_number] = tc;
  }

  // Determine which tours are captains_task tours
  const captainsTaskTours = new Set(
    (data.tour_configs ?? []).filter((tc) => tc.captains_task).map((tc) => tc.tour_number)
  );

  // Filter visible tour columns based on filter mode
  const getVisibleTours = (): number[] => {
    if (filterMode === 'personal_1') return tourColumns.filter((t) => t === 1);
    if (filterMode === 'personal_2') return tourColumns.filter((t) => t === 2);
    if (filterMode === 'personal_12') return tourColumns.filter((t) => t === 1 || t === 2);
    if (filterMode === 'team') return tourColumns.filter((t) => t === 3 || captainsTaskTours.has(t));
    return tourColumns;
  };
  const visibleTours = getVisibleTours();

  // Get tour total excluding captains task score (key "0") when in personal mode
  const getTourTotalFiltered = (item: ScoringProgressItem, tourNum: number, excludeCaptains: boolean): number | null => {
    const tour = item.tours.find((t) => t.tour_number === tourNum);
    if (!tour?.task_scores) return tour?.tour_total ?? null;
    if (!excludeCaptains || !captainsTaskTours.has(tourNum)) return tour.tour_total ?? null;
    let sum = 0;
    let hasAny = false;
    for (const [k, v] of Object.entries(tour.task_scores)) {
      if (k === '0') continue;
      sum += v;
      hasAny = true;
    }
    return hasAny ? sum : null;
  };

  // Recalculate totals for filtered view
  const isPersonalMode = filterMode.startsWith('personal');
  const calcFilteredTotal = (item: ScoringProgressItem): number | null => {
    if (filterMode === 'all') return item.score_total;
    let sum = 0;
    let hasAny = false;
    for (const t of visibleTours) {
      const val = getTourTotalFiltered(item, t, isPersonalMode);
      if (val !== null) { sum += val; hasAny = true; }
    }
    return hasAny ? sum : null;
  };

  // Team standings grouping
  interface TeamRow {
    institution: string;
    members: ScoringProgressItem[];
    teamTotal: number | null;
    teamTime: number | null;
  }

  const buildTeamRows = (): TeamRow[] => {
    const groups: Record<string, ScoringProgressItem[]> = {};
    for (const item of data.items) {
      const key = item.participant_school || '—';
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    }
    const rows: TeamRow[] = Object.entries(groups).map(([inst, members]) => {
      let teamTotal: number | null = null;
      let teamTime: number | null = null;
      for (const m of members) {
        const t = calcFilteredTotal(m);
        if (t !== null) {
          teamTotal = (teamTotal ?? 0) + t;
        }
        const secs = getTotalTimeSeconds(m);
        if (secs !== null) {
          teamTime = (teamTime ?? 0) + secs;
        }
      }
      return { institution: inst, members, teamTotal, teamTime };
    });
    // Sort using sortKeys; default: by teamTotal desc + time asc tiebreaker
    const sortCol = sortKeys.length > 0 ? sortKeys[0].col : 'total';
    const sortDir = sortKeys.length > 0 ? sortKeys[0].dir : 'desc';
    rows.sort((a, b) => {
      let va: number | null = null;
      let vb: number | null = null;
      if (sortCol === 'total') {
        va = a.teamTotal; vb = b.teamTotal;
      }
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;
      const cmp = sortDir === 'desc' ? vb - va : va - vb;
      if (cmp !== 0) return cmp;
      // time tiebreaker: less time = higher rank
      if (a.teamTime === null && b.teamTime === null) return 0;
      if (a.teamTime === null) return 1;
      if (b.teamTime === null) return -1;
      return a.teamTime - b.teamTime;
    });
    return rows;
  };

  const isTeamMode = filterMode === 'team';
  const teamRows = isTeamMode ? buildTeamRows() : [];

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

      {/* Filter dropdown */}
      {data.is_special && (
        <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 2 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Зачет:</label>
          <select
            value={filterMode}
            onChange={(e) => setFilterMode(e.target.value as FilterMode)}
            style={{
              padding: '5px 10px',
              borderRadius: 6,
              border: '1px solid #d1d5db',
              fontSize: 13,
              background: 'white',
            }}
          >
            <option value="all">Все</option>
            <option value="personal_1">Личный зачет (Тур I)</option>
            <option value="personal_2">Личный зачет (Тур II)</option>
            <option value="personal_12">Личный зачет (Тур I + II)</option>
            <option value="team">Общий зачет по командам</option>
          </select>
        </div>
      )}

      {sortKeys.length > 0 && (
        <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6, paddingLeft: 2 }}>
          Сортировка: {sortKeys.map((k, i) => {
            const labels: Record<string, string> = {
              name: 'ФИО', school: 'Учебное заведение', variant: 'Вар.', total: 'Итог',
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
            {isTeamMode ? (
              <th style={{ ...thStyle }}>ВУЗ</th>
            ) : (
              <>
                {makeTh('name', 'Участник')}
                {makeTh('school', 'Учебное заведение')}
              </>
            )}
            {!isTeamMode && makeTh('variant', 'Вар.', { textAlign: 'center' })}
            {data.is_special && visibleTours.map((t) => {
              const tt = tourTimeMap[t];
              const cfg = tourConfigMap[t];
              const modeLabel = cfg ? MODE_LABELS[cfg.mode] : null;
              const isCaptainsTour = cfg?.captains_task;
              return makeTh(`tour_${t}`, (
                <div>
                  <div>Тур {toRoman(t)}</div>
                  {modeLabel && (
                    <div style={{ fontSize: 10, fontWeight: 400, color: '#6b7280' }}>
                      {modeLabel}
                    </div>
                  )}
                  {isCaptainsTour && (
                    <div style={{ fontSize: 9, fontWeight: 600, color: '#b45309' }}>
                      + Задача капитанов
                    </div>
                  )}
                </div>
              ), { textAlign: 'center' });
            })}
            {makeTh('total', isTeamMode ? 'Сумма' : 'Итог', { textAlign: 'center' })}
            <th style={{ ...thStyle, textAlign: 'center' }}>{isTeamMode ? '' : 'Статус'}</th>
          </tr>
        </thead>
        <tbody>
          {isTeamMode ? (
            <>
              {teamRows.map((team, teamIdx) => (
                <React.Fragment key={team.institution}>
                  {/* Team header row */}
                  <tr style={{ background: '#e0e7ff', borderBottom: '2px solid #c7d2fe' }}>
                    <td style={{ ...tdStyle, fontWeight: 700, fontSize: 14 }}>
                      {teamIdx + 1}. {team.institution}
                    </td>
                    {data.is_special && visibleTours.map((tourNum) => {
                      let tourSum: number | null = null;
                      for (const m of team.members) {
                        const val = getTourTotal(m, tourNum);
                        if (val !== null) tourSum = (tourSum ?? 0) + val;
                      }
                      return (
                        <td key={tourNum} style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, color: '#4338ca' }}>
                          {tourSum !== null ? tourSum : '—'}
                        </td>
                      );
                    })}
                    <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, fontSize: 15, color: '#4338ca' }}>
                      {team.teamTotal !== null ? team.teamTotal : '—'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center', fontSize: 12, color: '#6b7280' }}>
                      {team.members.length} уч.
                    </td>
                  </tr>
                  {/* Individual members */}
                  {team.members.map((item) => {
                    const filteredTotal = calcFilteredTotal(item);
                    return (
                      <tr
                        key={item.registration_id}
                        style={{ background: 'white', borderBottom: '1px solid #e5e7eb' }}
                      >
                        <td style={{ ...tdStyle, paddingLeft: 28, color: '#555', fontSize: 12 }}>
                          {item.participant_name}
                          {item.is_captain && (
                            <span style={{ marginLeft: 6, fontSize: 10, color: '#b45309', fontWeight: 600 }}>К</span>
                          )}
                        </td>
                        {data.is_special && visibleTours.map((tourNum) => {
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
                                fontSize: 12,
                              }}
                            >
                              <div>{tour?.tour_total != null ? tour.tour_total : '—'}</div>
                              {taskEntries && taskEntries.length > 0 && (
                                <div style={{ fontSize: 9, fontWeight: 400, color: '#9ca3af', marginTop: 1 }}>
                                  {taskEntries.map(([k, v]) => `${k}:${v}`).join(' ')}
                                </div>
                              )}
                              {captainsTaskTours.has(tourNum) && item.captains_task_by_tour?.[tourNum] != null && (
                                <div style={{ fontSize: 9, fontWeight: 600, color: '#b45309', marginTop: 1 }}>
                                  К: {item.captains_task_by_tour[tourNum]}
                                </div>
                              )}
                            </td>
                          );
                        })}
                        <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 600, color: filteredTotal !== null ? '#15803d' : '#9ca3af', fontSize: 12 }}>
                          {filteredTotal !== null ? filteredTotal : '—'}
                        </td>
                        <td />
                      </tr>
                    );
                  })}
                </React.Fragment>
              ))}
              {teamRows.length === 0 && (
                <tr>
                  <td colSpan={3 + visibleTours.length} style={{ textAlign: 'center', padding: 24, color: '#9ca3af' }}>
                    Нет данных
                  </td>
                </tr>
              )}
            </>
          ) : (
            <>
              {sortedItems.map((item) => {
                const isHighlighted = item.attempt_id === highlightAttemptId;
                const filteredTotal = calcFilteredTotal(item);
                const isScored = filteredTotal !== null;
                return (
                  <tr
                    key={item.registration_id}
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
                    {data.is_special && visibleTours.map((tourNum) => {
                      const tour = item.tours.find((t) => t.tour_number === tourNum);
                      const displayTotal = getTourTotalFiltered(item, tourNum, isPersonalMode);
                      const taskEntries = tour?.task_scores
                        ? Object.entries(tour.task_scores)
                            .filter(([k]) => !(isPersonalMode && captainsTaskTours.has(tourNum) && k === '0'))
                            .sort(([a], [b]) => Number(a) - Number(b))
                        : null;
                      return (
                        <td
                          key={tourNum}
                          style={{
                            ...tdStyle,
                            textAlign: 'center',
                            fontWeight: displayTotal != null ? 600 : 400,
                            color: displayTotal != null ? '#15803d' : '#9ca3af',
                          }}
                        >
                          <div>{displayTotal != null ? displayTotal : '—'}</div>
                          {taskEntries && taskEntries.length > 0 && (
                            <div style={{ fontSize: 10, fontWeight: 400, color: '#9ca3af', marginTop: 2 }}>
                              {taskEntries.map(([k, v]) => `${k}:${v}`).join(' ')}
                            </div>
                          )}
                          {tour?.tour_time && (
                            <div style={{ fontSize: 9, fontWeight: 400, color: '#6b7280', marginTop: 1 }}>
                              {tour.tour_time}
                            </div>
                          )}
                          {captainsTaskTours.has(tourNum) && item.captains_task_by_tour?.[tourNum] != null && (
                            <div style={{ fontSize: 10, fontWeight: 600, color: '#b45309', marginTop: 1 }}>
                              К: {item.captains_task_by_tour[tourNum]}
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
                      {isScored ? filteredTotal : '—'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {data.is_special && visibleTours.length > 0 ? (
                        <div style={{ display: 'flex', gap: 3, justifyContent: 'center', flexWrap: 'wrap' }}>
                          {visibleTours.map((tourNum) => {
                            const tourData = item.tours.find((t) => t.tour_number === tourNum);
                            const tourScored = tourData?.tour_total !== null && tourData?.tour_total !== undefined;
                            return (
                              <span
                                key={tourNum}
                                title={`Тур ${tourNum}: ${tourScored ? 'заполнен' : 'не заполнен'}`}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  width: 16,
                                  height: 16,
                                  borderRadius: '50%',
                                  background: tourScored ? '#22c55e' : '#e5e7eb',
                                  color: 'white',
                                  fontSize: 9,
                                  fontWeight: 700,
                                  flexShrink: 0,
                                }}
                              >
                                {tourScored ? '✓' : ''}
                              </span>
                            );
                          })}
                        </div>
                      ) : isScored ? (
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
                    colSpan={4 + visibleTours.length}
                    style={{ textAlign: 'center', padding: 24, color: '#9ca3af' }}
                  >
                    Нет участников
                  </td>
                </tr>
              )}
            </>
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
