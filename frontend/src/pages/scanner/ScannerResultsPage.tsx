import React, { useEffect, useState } from 'react';
import api from '../../api/client';
import { toRoman } from '../../utils/roman';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';
import ScoringProgressTable from '../../components/ScoringProgressTable';
import type { Competition, TourTimeItem } from '../../types';

interface TourTimeFormEntry {
  started_at: string;
  finished_at: string;
}

const toLocalDatetimeValue = (iso: string | null): string => {
  if (!iso) return '';
  // Convert UTC ISO string to local datetime-local input value
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const ScannerResultsPage: React.FC = () => {
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [competitionsLoading, setCompetitionsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string>('');
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [exportLoading, setExportLoading] = useState(false);
  const [resultsTableLoading, setResultsTableLoading] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState<{ updated: number; skipped: string[] } | null>(null);

  // Tour time form state: tourNumber → { started_at, finished_at }
  const [tourTimes, setTourTimes] = useState<Record<number, TourTimeFormEntry>>({});
  const [savingTimes, setSavingTimes] = useState(false);
  const [timesError, setTimesError] = useState<string | null>(null);
  const [timesSaved, setTimesSaved] = useState(false);

  const selectedCompetition = competitions.find((c) => c.id === selectedId) ?? null;
  const toursCount = selectedCompetition?.is_special
    ? (selectedCompetition.special_tours_count ?? 0)
    : 0;

  // Load assigned competitions on mount
  useEffect(() => {
    const load = async () => {
      setCompetitionsLoading(true);
      try {
        const res = await api.get<{ competitions: Competition[]; total: number }>('competitions/my');
        setCompetitions(res.data.competitions ?? []);
      } catch {
        setCompetitions([]);
      } finally {
        setCompetitionsLoading(false);
      }
    };
    load();
  }, []);

  // When competition changes, reset tour time form
  useEffect(() => {
    setTourTimes({});
    setTimesError(null);
    setTimesSaved(false);
  }, [selectedId]);

  // Pre-fill tour time form from scoring progress data
  const handleTourTimesLoaded = (items: TourTimeItem[]) => {
    const map: Record<number, TourTimeFormEntry> = {};
    for (const tt of items) {
      map[tt.tour_number] = {
        started_at: toLocalDatetimeValue(tt.started_at),
        finished_at: toLocalDatetimeValue(tt.finished_at),
      };
    }
    setTourTimes((prev) => {
      // Only pre-fill if the user hasn't typed anything yet
      const isEmpty = Object.keys(prev).length === 0;
      return isEmpty ? map : prev;
    });
  };

  const handleExport = async () => {
    if (!selectedId) return;
    setExportLoading(true);
    try {
      const response = await api.get(`admin/competitions/${selectedId}/scoring-progress/export`, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data as Blob);
      const competition = competitions.find((c) => c.id === selectedId);
      const safeName = competition ? competition.name.replace(/[^\w\-]/g, '_').slice(0, 40) : selectedId;
      const a = document.createElement('a');
      a.href = url;
      a.download = `results_${safeName}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // silent — user sees no download
    } finally {
      setExportLoading(false);
    }
  };

  const handleExportResultsTable = async () => {
    if (!selectedId) return;
    setResultsTableLoading(true);
    try {
      const response = await api.get(
        `admin/competitions/${selectedId}/results-table/export`,
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(response.data as Blob);
      const safeName = selectedCompetition
        ? selectedCompetition.name.replace(/[^\w\-]/g, '_').slice(0, 40)
        : selectedId;
      const a = document.createElement('a');
      a.href = url;
      a.download = `results_table_${safeName}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // silent
    } finally {
      setResultsTableLoading(false);
    }
  };

  const handleImportResultsTable = async () => {
    if (!selectedId) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      setImportLoading(true);
      setImportResult(null);
      try {
        const form = new FormData();
        form.append('file', file);
        const { data } = await api.post(
          `admin/competitions/${selectedId}/results-table/import`,
          form,
          { headers: { 'Content-Type': 'multipart/form-data' } }
        );
        setImportResult({ updated: data.updated, skipped: data.skipped });
        setRefreshTrigger((n) => n + 1);
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Ошибка импорта.';
        alert(msg);
      } finally {
        setImportLoading(false);
      }
    };
    input.click();
  };

  const handleSaveTimes = async () => {
    if (!selectedId) return;
    setSavingTimes(true);
    setTimesError(null);
    setTimesSaved(false);
    try {
      for (let t = 1; t <= toursCount; t++) {
        const entry = tourTimes[t];
        const startedAt = entry?.started_at ? new Date(entry.started_at).toISOString() : null;
        const finishedAt = entry?.finished_at ? new Date(entry.finished_at).toISOString() : null;
        await api.put(`admin/competitions/${selectedId}/tour-times/${t}`, {
          started_at: startedAt,
          finished_at: finishedAt,
        });
      }
      setTimesSaved(true);
      setRefreshTrigger((n) => n + 1);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка сохранения времени туров.';
      setTimesError(msg);
    } finally {
      setSavingTimes(false);
    }
  };

  return (
    <Layout>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <h2 style={{ marginTop: 0 }}>Таблица результатов</h2>

        {/* Competition selector */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ fontWeight: 600, fontSize: 14, marginRight: 12 }}>
            Олимпиада:
          </label>
          {competitionsLoading ? (
            <span style={{ color: '#9ca3af', fontSize: 13 }}>Загрузка…</span>
          ) : competitions.length === 0 ? (
            <span style={{ color: '#9ca3af', fontSize: 13 }}>Нет доступных олимпиад</span>
          ) : (
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              style={{
                padding: '7px 12px',
                borderRadius: 6,
                border: '1px solid #d1d5db',
                fontSize: 14,
                minWidth: 300,
              }}
            >
              <option value="">— Выберите олимпиаду —</option>
              {competitions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.date})
                </option>
              ))}
            </select>
          )}
        </div>

        {selectedId && (
          <>
            {/* Tour time form — only for special olympiads with tours */}
            {toursCount > 0 && (
              <div
                style={{
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: 8,
                  padding: 16,
                  marginBottom: 24,
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12 }}>
                  Время выполнения туров
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {Array.from({ length: toursCount }, (_, i) => i + 1).map((t) => {
                    const entry = tourTimes[t] ?? { started_at: '', finished_at: '' };
                    return (
                      <div
                        key={t}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 12,
                          flexWrap: 'wrap',
                        }}
                      >
                        <span style={{ minWidth: 56, fontSize: 13, fontWeight: 600 }}>
                          Тур {toRoman(t)}
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <label style={{ fontSize: 12, color: '#6b7280', minWidth: 48 }}>
                            Начало:
                          </label>
                          <input
                            type="datetime-local"
                            value={entry.started_at}
                            onChange={(e) =>
                              setTourTimes((prev) => ({
                                ...prev,
                                [t]: { ...entry, started_at: e.target.value },
                              }))
                            }
                            style={{
                              padding: '5px 8px',
                              borderRadius: 5,
                              border: '1px solid #d1d5db',
                              fontSize: 13,
                            }}
                          />
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <label style={{ fontSize: 12, color: '#6b7280', minWidth: 60 }}>
                            Окончание:
                          </label>
                          <input
                            type="datetime-local"
                            value={entry.finished_at}
                            onChange={(e) =>
                              setTourTimes((prev) => ({
                                ...prev,
                                [t]: { ...entry, finished_at: e.target.value },
                              }))
                            }
                            style={{
                              padding: '5px 8px',
                              borderRadius: 5,
                              border: '1px solid #d1d5db',
                              fontSize: 13,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 12 }}>
                  <Button onClick={handleSaveTimes} loading={savingTimes} disabled={savingTimes}>
                    Сохранить время
                  </Button>
                  {timesSaved && (
                    <span style={{ fontSize: 13, color: '#15803d' }}>✓ Время сохранено</span>
                  )}
                  {timesError && (
                    <span style={{ fontSize: 13, color: '#dc2626' }}>{timesError}</span>
                  )}
                </div>
              </div>
            )}

            {/* Results table */}
            <div className="card" style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                <Button
                  onClick={handleImportResultsTable}
                  loading={importLoading}
                  disabled={importLoading}
                  variant="secondary"
                >
                  Импорт таблицы (.xlsx)
                </Button>
                <Button
                  onClick={handleExportResultsTable}
                  loading={resultsTableLoading}
                  disabled={resultsTableLoading}
                >
                  Итоговая таблица (.xlsx)
                </Button>
                <Button
                  onClick={handleExport}
                  loading={exportLoading}
                  disabled={exportLoading}
                >
                  Экспорт в Excel
                </Button>
              </div>
              {importResult && (
                <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 6, fontSize: 13 }}>
                  Импортировано: {importResult.updated} участник(ов).
                  {importResult.skipped.length > 0 && (
                    <span style={{ color: '#b45309' }}>
                      {' '}Не найдено: {importResult.skipped.join(', ')}
                    </span>
                  )}
                </div>
              )}
              <ScoringProgressTable
                competitionId={selectedId}
                refreshTrigger={refreshTrigger}
                onTourTimesLoaded={handleTourTimesLoaded}
              />
            </div>
          </>
        )}

        {!selectedId && !competitionsLoading && competitions.length > 0 && (
          <div
            className="card"
            style={{
              padding: 32,
              textAlign: 'center',
              color: '#9ca3af',
              fontSize: 14,
            }}
          >
            Выберите олимпиаду для просмотра таблицы результатов
          </div>
        )}
      </div>
    </Layout>
  );
};

export default ScannerResultsPage;
