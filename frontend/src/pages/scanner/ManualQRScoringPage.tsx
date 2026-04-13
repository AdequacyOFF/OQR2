import React, { useRef, useState } from 'react';
import api from '../../api/client';
import { toRoman } from '../../utils/roman';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';
import QRScanner from '../../components/qr/QRScanner';
import ScoringProgressTable from '../../components/ScoringProgressTable';

interface ResolveQRResponse {
  attempt_id: string;
  tour_number: number | null;
  participant_name: string;
  participant_school: string | null;
  institution_name: string | null;
  institution_location: string | null;
  is_captain: boolean;
  dob: string | null;
  position: string | null;
  military_rank: string | null;
  passport_series_number: string | null;
  passport_issued_by: string | null;
  passport_issued_date: string | null;
  military_booklet_number: string | null;
  military_personal_number: string | null;
  competition_id: string;
  competition_name: string;
  is_special: boolean;
  task_numbers: number[];
}

interface AttemptResponse {
  id: string;
  score_total: number | null;
  task_scores: Record<string, Record<string, number>> | null;
  status: string;
}

type Step = 'scan' | 'entry' | 'confirm';

const ManualQRScoringPage: React.FC = () => {
  const [step, setStep] = useState<Step>('scan');
  const [inputMode, setInputMode] = useState<'laser' | 'camera'>('laser');
  const [laserInput, setLaserInput] = useState('');
  const [resolving, setResolving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [resolved, setResolved] = useState<ResolveQRResponse | null>(null);
  const [taskScores, setTaskScores] = useState<Record<number, string>>({});
  const [tourTime, setTourTime] = useState('');
  const [resultAttempt, setResultAttempt] = useState<AttemptResponse | null>(null);

  // Progress table state
  const [competitionId, setCompetitionId] = useState<string | null>(null);
  const [lastAttemptId, setLastAttemptId] = useState<string | undefined>();
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const laserRef = useRef<HTMLInputElement>(null);

  const handleQRToken = async (token: string) => {
    if (!token.trim()) return;
    setResolving(true);
    setError(null);
    try {
      const { data } = await api.post<ResolveQRResponse>('scans/resolve-qr', {
        sheet_token: token.trim(),
      });
      setResolved(data);
      // Auto-detect competition for the table from first scan
      if (!competitionId) {
        setCompetitionId(data.competition_id);
      }
      // Initialize scores map
      const initial: Record<number, string> = {};
      for (const t of data.task_numbers) initial[t] = '';
      setTaskScores(initial);
      setTourTime('');
      setStep('entry');
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'QR-код не распознан');
    } finally {
      setResolving(false);
      setLaserInput('');
    }
  };

  const handleLaserKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleQRToken(laserInput);
    }
  };

  const handleSubmitScores = async () => {
    if (!resolved) return;
    setSubmitting(true);
    setError(null);

    const taskScoreList = Object.entries(taskScores).map(([task, score]) => ({
      task_number: parseInt(task),
      score: parseInt(score) || 0,
    }));

    try {
      const payload: Record<string, unknown> = {
        attempt_id: resolved.attempt_id,
        tour_number: resolved.tour_number ?? 1,
        task_scores: taskScoreList,
      };
      if (tourTime.trim()) {
        payload.tour_time = tourTime.trim();
      }
      const { data } = await api.post<AttemptResponse>('scans/qr-score-entry', payload);
      setResultAttempt(data);
      setLastAttemptId(data.id);
      setRefreshTrigger((n) => n + 1);
      setStep('confirm');
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Ошибка сохранения баллов');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setStep('scan');
    setResolved(null);
    setTaskScores({});
    setTourTime('');
    setResultAttempt(null);
    setError(null);
    setLaserInput('');
    setTimeout(() => laserRef.current?.focus(), 100);
  };

  const totalScore = Object.values(taskScores).reduce(
    (sum, v) => sum + (parseInt(v) || 0),
    0
  );

  return (
    <Layout>
      <div
        style={{
          display: 'flex',
          gap: 24,
          alignItems: 'flex-start',
          flexWrap: 'wrap',
        }}
      >
        {/* Left panel: scanning workflow */}
        <div style={{ flex: '0 0 520px', minWidth: 300, maxWidth: '100%' }}>
          <h2 style={{ marginTop: 0 }}>Ввод баллов по QR-коду</h2>

          {error && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              {error}
            </div>
          )}

          {/* Step 1: Scan QR */}
          {step === 'scan' && (
            <div className="card" style={{ padding: 24 }}>
              <p style={{ marginTop: 0, color: '#555' }}>
                Отсканируйте QR-код с A3-папки участника. Система определит участника и тур.
              </p>

              <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                <Button
                  variant={inputMode === 'laser' ? 'primary' : 'secondary'}
                  onClick={() => setInputMode('laser')}
                >
                  Лазерный сканер
                </Button>
                <Button
                  variant={inputMode === 'camera' ? 'primary' : 'secondary'}
                  onClick={() => setInputMode('camera')}
                >
                  Камера
                </Button>
              </div>

              {inputMode === 'laser' && (
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontSize: 13 }}>
                    Наведите лазерный сканер и нажмите Enter:
                  </label>
                  <input
                    ref={laserRef}
                    autoFocus
                    type="text"
                    value={laserInput}
                    onChange={(e) => setLaserInput(e.target.value)}
                    onKeyDown={handleLaserKey}
                    placeholder="QR-данные появятся здесь..."
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      fontSize: 15,
                      borderRadius: 8,
                      border: '2px solid #3b82f6',
                      boxSizing: 'border-box',
                    }}
                    disabled={resolving}
                  />
                  {resolving && (
                    <p style={{ color: '#888', marginTop: 8, fontSize: 13 }}>Определяем участника...</p>
                  )}
                </div>
              )}

              {inputMode === 'camera' && (
                <div>
                  <p style={{ fontSize: 13, color: '#555', marginBottom: 12 }}>
                    Наведите камеру на QR-код — сканирование произойдёт автоматически:
                  </p>
                  <QRScanner
                    onScan={(data) => {
                      if (!resolving) handleQRToken(data);
                    }}
                  />
                  {resolving && (
                    <p style={{ color: '#888', marginTop: 8, fontSize: 13 }}>Определяем участника...</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Step 2: Enter scores */}
          {step === 'entry' && resolved && (
            <div className="card" style={{ padding: 24 }}>
              <div style={{ background: '#f0f9ff', borderRadius: 8, padding: 12, marginBottom: 20 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>{resolved.participant_name}</div>
                <div style={{ color: '#555', fontSize: 13 }}>{resolved.competition_name}</div>
                {resolved.tour_number && (
                  <div style={{ color: '#2563eb', fontSize: 13, marginTop: 4 }}>
                    Тур {toRoman(resolved.tour_number)}
                  </div>
                )}
                {(resolved.institution_name || resolved.position || resolved.military_rank) && (
                  <div style={{ borderTop: '1px solid #dbeafe', marginTop: 8, paddingTop: 8, fontSize: 13, color: '#555' }}>
                    {resolved.institution_name && <div>{resolved.institution_name}{resolved.institution_location ? ` (${resolved.institution_location})` : ''}</div>}
                    {resolved.position && <div>Должность: {resolved.position}</div>}
                    {resolved.military_rank && <div>Воинское звание: {resolved.military_rank}</div>}
                    {resolved.is_captain && <div style={{ color: '#2563eb', fontWeight: 600 }}>Капитан команды</div>}
                  </div>
                )}
              </div>

              {resolved.task_numbers.length === 0 ? (
                <div>
                  <p style={{ color: '#555' }}>
                    Задания тура не определены автоматически. Введите итоговый балл:
                  </p>
                  <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
                    Итоговый балл
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={taskScores[1] ?? ''}
                    onChange={(e) => setTaskScores({ 1: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: 6,
                      border: '1px solid #d1d5db',
                      fontSize: 15,
                    }}
                  />
                </div>
              ) : (
                <div>
                  <p style={{ color: '#555', marginTop: 0 }}>
                    Введите балл за каждое задание:
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {resolved.task_numbers.map((taskNum) => (
                      <div key={taskNum} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <label style={{ minWidth: 80, fontSize: 14 }}>
                          Задание {taskNum}:
                        </label>
                        <input
                          type="number"
                          min="0"
                          value={taskScores[taskNum] ?? ''}
                          onChange={(e) =>
                            setTaskScores((prev) => ({ ...prev, [taskNum]: e.target.value }))
                          }
                          style={{
                            flex: 1,
                            padding: '8px 12px',
                            borderRadius: 6,
                            border: '1px solid #d1d5db',
                            fontSize: 15,
                          }}
                        />
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
                    <label style={{ minWidth: 80, fontSize: 14 }}>
                      Время:
                    </label>
                    <input
                      type="text"
                      placeholder="чч.мм.сс"
                      value={tourTime}
                      onChange={(e) => setTourTime(e.target.value)}
                      style={{
                        flex: 1,
                        padding: '8px 12px',
                        borderRadius: 6,
                        border: '1px solid #d1d5db',
                        fontSize: 15,
                      }}
                    />
                  </div>
                  <div
                    style={{
                      marginTop: 16,
                      padding: '8px 12px',
                      background: '#f3f4f6',
                      borderRadius: 6,
                      fontWeight: 600,
                    }}
                  >
                    Сумма: {totalScore}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
                <Button onClick={handleReset} variant="secondary">
                  Отмена
                </Button>
                <Button onClick={handleSubmitScores} loading={submitting} disabled={submitting}>
                  Сохранить баллы
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Confirmation */}
          {step === 'confirm' && resolved && resultAttempt && (
            <div className="card" style={{ padding: 24 }}>
              <div
                style={{
                  background: '#f0fdf4',
                  border: '1px solid #86efac',
                  borderRadius: 8,
                  padding: 16,
                  marginBottom: 20,
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 16, color: '#15803d' }}>
                  ✓ Баллы сохранены
                </div>
                <div style={{ marginTop: 8 }}>
                  <strong>{resolved.participant_name}</strong>
                </div>
                <div style={{ color: '#555', fontSize: 13 }}>{resolved.competition_name}</div>
                {resolved.tour_number && (
                  <div style={{ fontSize: 13, color: '#555' }}>Тур {toRoman(resolved.tour_number)}</div>
                )}
                <div style={{ marginTop: 8, fontSize: 16, fontWeight: 600 }}>
                  Итоговый балл: {resultAttempt.score_total ?? '—'}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 12 }}>
                <Button onClick={handleReset}>
                  Следующий участник
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Right panel: progress table */}
        <div style={{ flex: '1 1 500px', minWidth: 320 }}>
          <h2 style={{ marginTop: 0 }}>Таблица участников</h2>
          {competitionId ? (
            <div className="card" style={{ padding: 16 }}>
              <ScoringProgressTable
                competitionId={competitionId}
                highlightAttemptId={lastAttemptId}
                refreshTrigger={refreshTrigger}
              />
            </div>
          ) : (
            <div
              className="card"
              style={{
                padding: 32,
                textAlign: 'center',
                color: '#9ca3af',
                fontSize: 14,
              }}
            >
              Отсканируйте первый QR-код, чтобы загрузить таблицу участников
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};

export default ManualQRScoringPage;
