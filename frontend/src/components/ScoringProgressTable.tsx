import React, { useEffect, useRef, useState } from 'react';
import api from '../api/client';
import { ScoringProgressResponse, TourTimeItem } from '../types';

interface Props {
  competitionId: string;
  highlightAttemptId?: string;
  refreshTrigger: number;
  onTourTimesLoaded?: (tourTimes: TourTimeItem[]) => void;
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
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Ошибка загрузки данных');
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
            <th style={thStyle}>Участник</th>
            <th style={thStyle}>Школа</th>
            <th style={{ ...thStyle, textAlign: 'center' }}>Вар.</th>
            {data.is_special && tourColumns.map((t) => {
              const tt = tourTimeMap[t];
              return (
                <th key={t} style={{ ...thStyle, textAlign: 'center' }}>
                  <div>Тур {t}</div>
                  {tt?.duration_minutes != null && (
                    <div style={{ fontSize: 10, fontWeight: 400, color: '#6b7280' }}>
                      {tt.duration_minutes} мин
                    </div>
                  )}
                </th>
              );
            })}
            <th style={{ ...thStyle, textAlign: 'center' }}>Итог</th>
            <th style={{ ...thStyle, textAlign: 'center' }}>Статус</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => {
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
