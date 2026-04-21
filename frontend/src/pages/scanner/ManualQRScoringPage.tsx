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
  tour_mode: string | null;
  is_captains_task: boolean;
  cap_task_number: number | null;
  captains_task_numbers: number[];
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
  const [captainTaskScores, setCaptainTaskScores] = useState<Record<number, string>>({});
  const [tourStart, setTourStart] = useState('');
  const [tourEnd, setTourEnd] = useState('');
  const [captainTaskStart, setCaptainTaskStart] = useState('');
  const [captainTaskEnd, setCaptainTaskEnd] = useState('');
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
      // Initialize captain task scores if captain in individual_captains tour
      const initCap: Record<number, string> = {};
      for (const n of data.captains_task_numbers ?? []) initCap[n] = '';
      setCaptainTaskScores(initCap);
      setTourStart('');
      setTourEnd('');
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
      score: parseFloat(score) || 0,
    }));

    try {
      const payload: Record<string, unknown> = {
        attempt_id: resolved.attempt_id,
        tour_number: resolved.tour_number ?? 1,
        task_scores: taskScoreList,
        is_captains_task: resolved.is_captains_task,
      };
      const computed = computeTourTime(tourStart, tourEnd);
      if (computed) {
        payload.tour_time = computed;
      }
      const { data } = await api.post<AttemptResponse>('scans/qr-score-entry', payload);

      // If captain in individual_captains tour and captain task scores were entered, submit them too
      const capEntries = Object.entries(captainTaskScores).filter(([, v]) => v !== '');
      if (!resolved.is_captains_task && capEntries.length > 0) {
        const capPayload: Record<string, unknown> = {
          attempt_id: resolved.attempt_id,
          tour_number: resolved.tour_number ?? 1,
          task_scores: capEntries.map(([task, score]) => ({
            task_number: parseInt(task),
            score: parseFloat(score) || 0,
          })),
          is_captains_task: true,
        };
        const capTime = computeTourTime(captainTaskStart, captainTaskEnd);
        if (capTime) capPayload.tour_time = capTime;
        await api.post<AttemptResponse>('scans/qr-score-entry', capPayload);
      }

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

  const computeTourTime = (start: string, end: string): string | null => {
    if (!start || !end) return null;
    const [sh, sm] = start.split(':').map(Number);
    const [eh, em] = end.split(':').map(Number);
    if (isNaN(sh) || isNaN(sm) || isNaN(eh) || isNaN(em)) return null;
    const startSecs = sh * 3600 + sm * 60;
    const endSecs = eh * 3600 + em * 60;
    if (endSecs <= startSecs) return null;
    const diff = endSecs - startSecs;
    const h = Math.floor(diff / 3600);
    const m = Math.floor((diff % 3600) / 60);
    const s = diff % 60;
    return `${String(h).padStart(2, '0')}.${String(m).padStart(2, '0')}.${String(s).padStart(2, '0')}`;
  };

  const handleReset = () => {
    setStep('scan');
    setResolved(null);
    setTaskScores({});
    setCaptainTaskScores({});
    setTourStart('');
    setTourEnd('');
    setCaptainTaskStart('');
    setCaptainTaskEnd('');
    setResultAttempt(null);
    setError(null);
    setLaserInput('');
    setTimeout(() => laserRef.current?.focus(), 100);
  };

  const totalScore = Object.values(taskScores).reduce(
    (sum, v) => sum + (parseFloat(v) || 0),
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
              {/* Captain task banner */}
              {resolved.is_captains_task && (
                <div style={{
                  background: '#fef3c7',
                  border: '2px solid #f59e0b',
                  borderRadius: 8,
                  padding: '12px 16px',
                  marginBottom: 12,
                  fontWeight: 700,
                  color: '#92400e',
                  fontSize: 15,
                  textAlign: 'center',
                  letterSpacing: '0.02em',
                }}>
                  ★ БЛАНК ЗАДАНИЯ КАПИТАНА ★
                  <div style={{ fontSize: 12, fontWeight: 400, marginTop: 4 }}>
                    Баллы записываются в командный зачёт
                  </div>
                </div>
              )}
              {/* Team tour banner */}
              {!resolved.is_captains_task && resolved.tour_mode === 'team' && (
                <div style={{
                  background: '#ede9fe',
                  border: '1px solid #7c3aed',
                  borderRadius: 8,
                  padding: '10px 14px',
                  marginBottom: 12,
                  fontWeight: 600,
                  color: '#4c1d95',
                  fontSize: 14,
                }}>
                  КОМАНДНЫЙ ТУР
                </div>
              )}
              <div style={{ background: '#f0f9ff', borderRadius: 8, padding: 12, marginBottom: 20 }}>
                <div style={{ fontWeight: 600, fontSize: 16 }}>
                  {resolved.tour_mode === 'team'
                    ? (resolved.institution_name || resolved.participant_name)
                    : resolved.participant_name}
                </div>
                <div style={{ color: '#555', fontSize: 13 }}>{resolved.competition_name}</div>
                {resolved.tour_number && (
                  <div style={{ color: '#2563eb', fontSize: 13, marginTop: 4 }}>
                    Тур {toRoman(resolved.tour_number)}
                    {resolved.is_captains_task && resolved.cap_task_number != null
                      ? ` — Задание капитана №${resolved.cap_task_number}`
                      : ''}
                  </div>
                )}
                {(resolved.institution_name || resolved.position || resolved.military_rank) && (
                  <div style={{ borderTop: '1px solid #dbeafe', marginTop: 8, paddingTop: 8, fontSize: 13, color: '#555' }}>
                    {resolved.institution_name && <div>{resolved.institution_name}{resolved.institution_location ? ` (${resolved.institution_location})` : ''}</div>}
                    {resolved.tour_mode !== 'team' && resolved.participant_name && resolved.institution_name && (
                      <div style={{ color: '#374151' }}>{resolved.participant_name}</div>
                    )}
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
                    step="any"
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
                          step="any"
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
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: '#374151' }}>
                      Время выполнения тура (необязательно):
                    </div>
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <label style={{ fontSize: 13, minWidth: 60 }}>Начало:</label>
                        <input
                          type="time"
                          value={tourStart}
                          onChange={(e) => setTourStart(e.target.value)}
                          style={{
                            padding: '6px 10px',
                            borderRadius: 6,
                            border: '1px solid #d1d5db',
                            fontSize: 14,
                          }}
                        />
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <label style={{ fontSize: 13, minWidth: 60 }}>Конец:</label>
                        <input
                          type="time"
                          value={tourEnd}
                          onChange={(e) => setTourEnd(e.target.value)}
                          style={{
                            padding: '6px 10px',
                            borderRadius: 6,
                            border: '1px solid #d1d5db',
                            fontSize: 14,
                          }}
                        />
                      </div>
                    </div>
                    {tourStart && tourEnd && (() => {
                      const ct = computeTourTime(tourStart, tourEnd);
                      if (!ct) return (
                        <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>
                          Время конца должно быть позже начала
                        </div>
                      );
                      return (
                        <div style={{ fontSize: 12, color: '#15803d', marginTop: 4 }}>
                          Продолжительность: {ct.replace(/\./g, ':')}
                        </div>
                      );
                    })()}
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

                  {/* Captain task score inputs (for captains in individual_captains tours) */}
                  {!resolved.is_captains_task && resolved.is_captain && (resolved.captains_task_numbers?.length ?? 0) > 0 && (
                    <div style={{
                      marginTop: 20,
                      borderTop: '2px solid #f59e0b',
                      paddingTop: 16,
                    }}>
                      <div style={{
                        fontWeight: 700,
                        color: '#92400e',
                        fontSize: 14,
                        marginBottom: 10,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}>
                        ★ Задание капитана (командный зачёт)
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        {resolved.captains_task_numbers.map((n) => (
                          <div key={n} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <label style={{ minWidth: 80, fontSize: 14 }}>Задание {n}:</label>
                            <input
                              type="number"
                              min="0"
                              step="any"
                              value={captainTaskScores[n] ?? ''}
                              onChange={(e) =>
                                setCaptainTaskScores((prev) => ({ ...prev, [n]: e.target.value }))
                              }
                              style={{
                                flex: 1,
                                padding: '8px 12px',
                                borderRadius: 6,
                                border: '1px solid #f59e0b',
                                fontSize: 15,
                              }}
                            />
                          </div>
                        ))}
                      </div>
                      <div style={{ marginTop: 12 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: '#92400e' }}>
                          Время задания капитана (необязательно):
                        </div>
                        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <label style={{ fontSize: 13, minWidth: 60 }}>Начало:</label>
                            <input
                              type="time"
                              value={captainTaskStart}
                              onChange={(e) => setCaptainTaskStart(e.target.value)}
                              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #f59e0b', fontSize: 14 }}
                            />
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <label style={{ fontSize: 13, minWidth: 60 }}>Конец:</label>
                            <input
                              type="time"
                              value={captainTaskEnd}
                              onChange={(e) => setCaptainTaskEnd(e.target.value)}
                              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #f59e0b', fontSize: 14 }}
                            />
                          </div>
                        </div>
                        {captainTaskStart && captainTaskEnd && (() => {
                          const ct = computeTourTime(captainTaskStart, captainTaskEnd);
                          if (!ct) return (
                            <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>
                              Время конца должно быть позже начала
                            </div>
                          );
                          return (
                            <div style={{ fontSize: 12, color: '#15803d', marginTop: 4 }}>
                              Продолжительность: {ct.replace(/\./g, ':')}
                            </div>
                          );
                        })()}
                      </div>
                    </div>
                  )}
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
                  <strong>
                    {resolved.tour_mode === 'team'
                      ? (resolved.institution_name || resolved.participant_name)
                      : resolved.participant_name}
                  </strong>
                </div>
                <div style={{ color: '#555', fontSize: 13 }}>{resolved.competition_name}</div>
                {resolved.tour_number && (
                  <div style={{ fontSize: 13, color: '#555' }}>
                    Тур {toRoman(resolved.tour_number)}
                    {resolved.is_captains_task ? ' — Задание капитана' : ''}
                  </div>
                )}
                {resolved.is_captains_task ? (
                  <div style={{ marginTop: 8, fontSize: 13, color: '#92400e' }}>
                    Баллы записаны в командный зачёт
                  </div>
                ) : (
                  <div style={{ marginTop: 8, fontSize: 16, fontWeight: 600 }}>
                    Итоговый балл: {resultAttempt.score_total ?? '—'}
                  </div>
                )}
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
