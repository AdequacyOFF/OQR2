import React, { useState, useRef, useEffect } from 'react';
import api from '../../api/client';
import Layout from '../../components/layout/Layout';
import QRScanner from '../../components/qr/QRScanner';
import QRCodeDisplay from '../../components/qr/QRCodeDisplay';
import Button from '../../components/common/Button';
import type { ParticipantEvent } from '../../types';

const EVENT_TYPES = [
  { value: 'start_work', label: 'Начало работы' },
  { value: 'submit', label: 'Сдача работы' },
  { value: 'exit_room', label: 'Выход из аудитории' },
  { value: 'enter_room', label: 'Вход в аудиторию' },
];

interface ResolveSheetResult {
  attempt_id: string;
  answer_sheet_id: string | null;
  participant_name: string;
  competition_id: string;
  competition_name: string;
}

interface AttemptSheet {
  id: string;
  kind: 'primary' | 'extra' | string;
  created_at: string;
  pdf_file_path: string | null;
}

interface SearchParticipantItem {
  participant_id: string;
  participant_name: string;
  competition_id: string;
  competition_name: string;
  attempt_id: string;
  room_name: string | null;
  seat_number: number | null;
  primary_answer_sheet_id: string | null;
}

const InvigilatorPage: React.FC = () => {
  const [scanMode, setScanMode] = useState<'camera' | 'laser'>('laser');
  const [scanning, setScanning] = useState(true);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [resolved, setResolved] = useState<ResolveSheetResult | null>(null);
  const [events, setEvents] = useState<ParticipantEvent[]>([]);
  const [answerSheets, setAnswerSheets] = useState<AttemptSheet[]>([]);
  const [recording, setRecording] = useState(false);
  const [issuingExtra, setIssuingExtra] = useState(false);
  const [extraSheetToken, setExtraSheetToken] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchItems, setSearchItems] = useState<SearchParticipantItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const laserInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (scanMode === 'laser' && scanning && laserInputRef.current) {
      laserInputRef.current.focus();
    }
  }, [scanMode, scanning]);

  const handleScan = async (token: string) => {
    setError(null);
    try {
      const { data } = await api.post<ResolveSheetResult>('invigilator/resolve-sheet-token', {
        sheet_token: token,
      });
      setResolved(data);
      setAttemptId(data.attempt_id);
      setScanning(false);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Не удалось найти бланк по токену';
      setError(msg);
    }
  };

  const handleLaserInput = async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const value = (e.target as HTMLInputElement).value.trim();
      if (value) {
        (e.target as HTMLInputElement).value = '';
        await handleScan(value);
      }
    }
  };

  const fetchAttemptContext = async (aId: string) => {
    try {
      const [eventsRes, sheetsRes] = await Promise.all([
        api.get<{ events: ParticipantEvent[] }>(`invigilator/attempt/${aId}/events`),
        api.get<{ sheets: AttemptSheet[] }>(`invigilator/attempt/${aId}/sheets`),
      ]);
      setEvents(eventsRes.data.events || []);
      setAnswerSheets(sheetsRes.data.sheets || []);
    } catch {
      // Ignore context loading errors
    }
  };

  useEffect(() => {
    if (attemptId) {
      fetchAttemptContext(attemptId);
    }
  }, [attemptId]);

  const handleRecordEvent = async (eventType: string) => {
    if (!attemptId) return;
    setRecording(true);
    setError(null);

    try {
      await api.post('invigilator/events', {
        attempt_id: attemptId,
        event_type: eventType,
      });
      await fetchAttemptContext(attemptId);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Ошибка';
      setError(msg);
    } finally {
      setRecording(false);
    }
  };

  const handleIssueExtraSheet = async () => {
    if (!attemptId) return;
    setIssuingExtra(true);
    setError(null);

    try {
      const { data } = await api.post<{ answer_sheet_id: string; sheet_token: string; pdf_url: string }>(
        'invigilator/extra-sheet',
        { attempt_id: attemptId }
      );
      setExtraSheetToken(data.sheet_token);
      await fetchAttemptContext(attemptId);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Ошибка';
      setError(msg);
    } finally {
      setIssuingExtra(false);
    }
  };

  const handleSearchSheets = async () => {
    if (searchQuery.trim().length < 2) return;
    setSearching(true);
    setError(null);
    setHasSearched(true);
    try {
      const { data } = await api.get<{ items: SearchParticipantItem[] }>(
        `invigilator/search-participants?q=${encodeURIComponent(searchQuery.trim())}&limit=30`
      );
      setSearchItems(data.items || []);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Ошибка поиска';
      setError(msg);
    } finally {
      setSearching(false);
    }
  };

  const handleDownloadSheet = (answerSheetId: string) => {
    window.open(`/api/v1/invigilator/answer-sheet/${answerSheetId}/download`, '_blank');
  };

  const handleSelectParticipant = (item: SearchParticipantItem) => {
    setResolved({
      attempt_id: item.attempt_id,
      answer_sheet_id: item.primary_answer_sheet_id,
      participant_name: item.participant_name,
      competition_id: item.competition_id,
      competition_name: item.competition_name,
    });
    setAttemptId(item.attempt_id);
    setScanning(false);
    setExtraSheetToken(null);
  };

  const handleReset = () => {
    setScanning(true);
    setAttemptId(null);
    setResolved(null);
    setEvents([]);
    setAnswerSheets([]);
    setExtraSheetToken(null);
    setError(null);
  };

  return (
    <Layout>
      <h1 className="mb-24">Наблюдатель</h1>

      {error && <div className="alert alert-error mb-16">{error}</div>}

      {scanning && (
        <div className="card">
          <div className="scan-mode-toggle mb-24" style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
            <button
              className={`mode-btn ${scanMode === 'laser' ? 'active' : ''}`}
              onClick={() => setScanMode('laser')}
              style={{
                padding: '12px 24px', fontSize: 16, fontWeight: 600,
                border: scanMode === 'laser' ? '2px solid #4299e1' : '2px solid #cbd5e0',
                borderRadius: 8, background: scanMode === 'laser' ? '#4299e1' : 'white',
                color: scanMode === 'laser' ? 'white' : '#4a5568', cursor: 'pointer',
              }}
            >
              Лазер
            </button>
            <button
              className={`mode-btn ${scanMode === 'camera' ? 'active' : ''}`}
              onClick={() => setScanMode('camera')}
              style={{
                padding: '12px 24px', fontSize: 16, fontWeight: 600,
                border: scanMode === 'camera' ? '2px solid #4299e1' : '2px solid #cbd5e0',
                borderRadius: 8, background: scanMode === 'camera' ? '#4299e1' : 'white',
                color: scanMode === 'camera' ? 'white' : '#4a5568', cursor: 'pointer',
              }}
            >
              Камера
            </button>
          </div>

          <h2 className="mb-16">Сканировать QR-код бланка</h2>

          {scanMode === 'laser' ? (
            <input
              ref={laserInputRef}
              type="text"
              placeholder="Ожидание сканирования..."
              onKeyDown={handleLaserInput}
              autoFocus
              style={{
                width: '100%', padding: 16, fontSize: 18, textAlign: 'center',
                border: '2px solid #4299e1', borderRadius: 8,
              }}
            />
          ) : (
            <QRScanner
              onScan={handleScan}
              onError={(err) => console.error('QR error:', err)}
            />
          )}
        </div>
      )}

      {attemptId && (
        <div className="card">
          <h2 className="mb-16">
            Попытка: {attemptId.substring(0, 8)}...
            {resolved && (
              <span style={{ display: 'block', fontSize: 14, fontWeight: 500, marginTop: 4 }}>
                {resolved.participant_name} · {resolved.competition_name}
              </span>
            )}
          </h2>

          <div className="mb-16">
            <h3 className="mb-8">Записать событие</h3>
            <div className="flex gap-8" style={{ flexWrap: 'wrap' }}>
              {EVENT_TYPES.map((et) => (
                <Button
                  key={et.value}
                  onClick={() => handleRecordEvent(et.value)}
                  loading={recording}
                  variant="secondary"
                >
                  {et.label}
                </Button>
              ))}
            </div>
          </div>

          <div className="mb-16">
            <h3 className="mb-8">История событий</h3>
            {events.length === 0 ? (
              <p className="text-muted">Нет событий</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Событие</th>
                    <th>Время</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr key={ev.id}>
                      <td>{EVENT_TYPES.find((t) => t.value === ev.event_type)?.label || ev.event_type}</td>
                      <td>{new Date(ev.timestamp).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="mb-16">
            <h3 className="mb-8">Бланки участника</h3>
            {answerSheets.length === 0 ? (
              <p className="text-muted">Бланки не найдены</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {answerSheets.map((sheet) => (
                  <div
                    key={sheet.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      border: '1px solid #e2e8f0',
                      borderRadius: 8,
                    }}
                  >
                    <span>
                      <strong>{sheet.kind === 'primary' ? 'Основной' : 'Дополнительный'}</strong>
                      <span className="text-muted" style={{ marginLeft: 8, fontSize: 12 }}>
                        {new Date(sheet.created_at).toLocaleString('ru-RU')}
                      </span>
                    </span>
                    <Button variant="secondary" className="btn-sm" onClick={() => handleDownloadSheet(sheet.id)}>
                      Скачать PDF
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mb-16">
            <h3 className="mb-8">Дополнительный бланк</h3>
            <Button onClick={handleIssueExtraSheet} loading={issuingExtra}>
              Выдать дополнительный бланк
            </Button>
            {extraSheetToken && (
              <div className="mt-16">
                <div className="alert alert-success mb-8">Дополнительный бланк выдан!</div>
                <QRCodeDisplay value={extraSheetToken} size={150} />
                <p className="text-muted text-center mt-8" style={{ fontSize: 11, wordBreak: 'break-all' }}>
                  {extraSheetToken}
                </p>
              </div>
            )}
          </div>

          <Button variant="secondary" onClick={handleReset}>
            Следующий участник
          </Button>
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h2 className="mb-16">Поиск участника по ФИО</h2>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <input
            type="text"
            className="input"
            placeholder="Введите минимум 2 символа ФИО участника"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <Button onClick={handleSearchSheets} loading={searching}>
            Найти
          </Button>
        </div>
        {searchItems.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Участник</th>
                <th>Олимпиада</th>
                <th>Аудитория</th>
                <th>Место</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {searchItems.map((item, idx) => (
                <tr key={`${item.attempt_id}-${idx}`}>
                  <td>{item.participant_name}</td>
                  <td>{item.competition_name}</td>
                  <td>{item.room_name || '—'}</td>
                  <td>{item.seat_number ?? '—'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Button className="btn-sm" onClick={() => handleSelectParticipant(item)}>
                        Выбрать
                      </Button>
                      {item.primary_answer_sheet_id && (
                        <Button
                          variant="secondary"
                          className="btn-sm"
                          onClick={() => handleDownloadSheet(item.primary_answer_sheet_id)}
                        >
                          QR/PDF
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {hasSearched && !searching && searchItems.length === 0 && (
          <p className="text-muted">Участники с активной попыткой не найдены.</p>
        )}
      </div>
    </Layout>
  );
};

export default InvigilatorPage;
