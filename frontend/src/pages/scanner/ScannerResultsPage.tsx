import React, { useEffect, useState, useCallback } from 'react';
import api from '../../api/client';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';
import ScoringProgressTable from '../../components/ScoringProgressTable';
import ResultsTableView from '../../components/ResultsTableView';
import type { Competition, ScoringProgressResponse } from '../../types';

const ScannerResultsPage: React.FC = () => {
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [competitionsLoading, setCompetitionsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string>('');
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [exportLoading, setExportLoading] = useState(false);
  const [resultsTableLoading, setResultsTableLoading] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState<{ updated: number; skipped: string[] } | null>(null);

  // View mode: 'progress' = existing scoring table, 'results' = final standings
  const [viewMode, setViewMode] = useState<'progress' | 'results'>('progress');
  const [resultsData, setResultsData] = useState<ScoringProgressResponse | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);

  const selectedCompetition = competitions.find((c) => c.id === selectedId) ?? null;

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

  const fetchResultsData = useCallback(async () => {
    if (!selectedId) return;
    setResultsLoading(true);
    try {
      const res = await api.get<ScoringProgressResponse>(
        `admin/competitions/${selectedId}/scoring-progress`,
      );
      setResultsData(res.data);
    } catch {
      setResultsData(null);
    } finally {
      setResultsLoading(false);
    }
  }, [selectedId]);

  // Fetch results data whenever switching to results view or changing competition in that mode
  useEffect(() => {
    if (viewMode === 'results' && selectedId) {
      void fetchResultsData();
    }
  }, [viewMode, selectedId, fetchResultsData]);

  // Reset results data when competition changes
  useEffect(() => {
    setResultsData(null);
  }, [selectedId]);

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
            <div className="card" style={{ padding: 16 }}>
              {/* Toolbar */}
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

              {/* View-mode tabs */}
              <div style={{ display: 'flex', borderBottom: '2px solid #e5e7eb', marginBottom: 16 }}>
                {(['progress', 'results'] as const).map((mode) => {
                  const active = viewMode === mode;
                  return (
                    <button
                      key={mode}
                      onClick={() => setViewMode(mode)}
                      style={{
                        padding: '8px 20px',
                        border: 'none',
                        borderBottom: active ? '2px solid #2563eb' : '2px solid transparent',
                        marginBottom: -2,
                        background: 'none',
                        cursor: 'pointer',
                        fontWeight: active ? 700 : 400,
                        color: active ? '#2563eb' : '#6b7280',
                        fontSize: 14,
                      }}
                    >
                      {mode === 'progress' ? 'Прогресс' : 'Итоговая таблица'}
                    </button>
                  );
                })}
              </div>

              {/* Content */}
              {viewMode === 'progress' && (
                <ScoringProgressTable
                  competitionId={selectedId}
                  refreshTrigger={refreshTrigger}
                />
              )}

              {viewMode === 'results' && (
                resultsLoading ? (
                  <div style={{ padding: 32, textAlign: 'center', color: '#9ca3af', fontSize: 14 }}>
                    Загрузка…
                  </div>
                ) : resultsData ? (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                      <Button onClick={() => { void fetchResultsData(); }} loading={resultsLoading} variant="secondary">
                        Обновить
                      </Button>
                    </div>
                    <ResultsTableView data={resultsData} />
                  </div>
                ) : (
                  <div style={{ padding: 32, textAlign: 'center', color: '#9ca3af', fontSize: 14 }}>
                    Нет данных
                  </div>
                )
              )}
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
