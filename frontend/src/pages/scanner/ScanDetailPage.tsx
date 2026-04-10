import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api/client';
import type { ScanItem } from '../../types';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';
import Input from '../../components/common/Input';
import Spinner from '../../components/common/Spinner';

interface ParticipantEvent {
  id: string;
  event_type: string;
  timestamp: string;
}

interface AnswerSheetInfo {
  id: string;
  kind: string;
  created_at: string;
}

const EVENT_LABELS: Record<string, string> = {
  start_work: 'Начало работы',
  submit: 'Сдача работы',
  exit_room: 'Выход из аудитории',
  enter_room: 'Вход в аудиторию',
};

const ScanDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [scan, setScan] = useState<ScanItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [correctedScore, setCorrectedScore] = useState<string>('');
  const [manualAttemptId, setManualAttemptId] = useState<string>('');
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [events, setEvents] = useState<ParticipantEvent[]>([]);
  const [answerSheets, setAnswerSheets] = useState<AnswerSheetInfo[]>([]);

  useEffect(() => {
    const loadScan = async () => {
      try {
        const { data } = await api.get<ScanItem>(`scans/${id}`);
        setScan(data);
        if (data.ocr_score !== null) {
          setCorrectedScore(String(data.ocr_score));
        }
        // Load scan image
        try {
          const imgResp = await api.get(`scans/${id}/image`, { responseType: 'blob' });
          const url = URL.createObjectURL(imgResp.data as Blob);
          setImageUrl(url);
        } catch {
          // Image may not be available yet
        }
        // Load invigilator events and answer sheets for this attempt
        if (data.attempt_id) {
          try {
            const eventsResp = await api.get<{ events: ParticipantEvent[] }>(
              `invigilator/attempt/${data.attempt_id}/events`
            );
            setEvents(eventsResp.data.events || []);
          } catch {
            // Events endpoint may not be accessible for scanner role
          }
          try {
            const sheetsResp = await api.get<{ sheets: AnswerSheetInfo[] }>(
              `invigilator/attempt/${data.attempt_id}/sheets`
            );
            setAnswerSheets(sheetsResp.data.sheets || []);
          } catch {
            // Sheets endpoint may not exist yet
          }
        }
      } catch {
        setError('Не удалось загрузить скан.');
      } finally {
        setLoading(false);
      }
    };

    loadScan();
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    };
  }, [id]);

  const handleVerify = async () => {
    if (!scan) return;
    setVerifying(true);
    setError(null);
    setSuccess(null);

    try {
      const payload: { corrected_score: number; attempt_id?: string } = {
        corrected_score: Number(correctedScore),
      };
      if (!scan.attempt_id && manualAttemptId.trim()) {
        payload.attempt_id = manualAttemptId.trim();
      }
      const { data } = await api.post(`scans/${scan.id}/verify`, payload);
      setScan(data);
      setSuccess('Скан успешно подтверждён.');
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка подтверждения.';
      setError(message);
    } finally {
      setVerifying(false);
    }
  };

  if (loading) {
    return (
      <Layout>
        <Spinner />
      </Layout>
    );
  }

  if (!scan) {
    return (
      <Layout>
        <div className="alert alert-error">{error || 'Скан не найден.'}</div>
      </Layout>
    );
  }

  return (
    <Layout>
      <h1 className="mb-24">Детали скана</h1>

      {error && <div className="alert alert-error mb-16">{error}</div>}
      {success && <div className="alert alert-success mb-16">{success}</div>}

      <div className="card mb-16">
        <h2 className="mb-16">Информация о скане</h2>
        <table className="table">
          <tbody>
            <tr>
              <td><strong>ID</strong></td>
              <td>{scan.id}</td>
            </tr>
            <tr>
              <td><strong>ID попытки</strong></td>
              <td>{scan.attempt_id || '-'}</td>
            </tr>
            <tr>
              <td><strong>Путь к файлу</strong></td>
              <td>{scan.file_path}</td>
            </tr>
            <tr>
              <td><strong>Балл OCR</strong></td>
              <td>
                {scan.ocr_raw_text === null
                  ? 'Обрабатывается...'
                  : scan.ocr_score !== null
                    ? scan.ocr_score
                    : 'Не найден'}
              </td>
            </tr>
            <tr>
              <td><strong>Точность OCR</strong></td>
              <td>
                {scan.ocr_raw_text === null
                  ? 'Обрабатывается...'
                  : scan.ocr_confidence !== null
                    ? `${(scan.ocr_confidence * 100).toFixed(1)}%`
                    : '—'}
              </td>
            </tr>
            <tr>
              <td><strong>Проверил</strong></td>
              <td>{scan.verified_by || 'Не проверен'}</td>
            </tr>
            <tr>
              <td><strong>Загрузил</strong></td>
              <td>{scan.uploaded_by}</td>
            </tr>
            <tr>
              <td><strong>Создан</strong></td>
              <td>{new Date(scan.created_at).toLocaleString('ru-RU')}</td>
            </tr>
            <tr>
              <td><strong>Обновлён</strong></td>
              <td>{new Date(scan.updated_at).toLocaleString('ru-RU')}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {imageUrl && (
        <div className="card mb-16">
          <h2 className="mb-16">Изображение скана</h2>
          {scan.file_path.endsWith('.pdf') ? (
            <iframe
              src={imageUrl}
              style={{ width: '100%', height: '80vh', border: 'none', borderRadius: 6 }}
              title="Скан PDF"
            />
          ) : (
            <img
              src={imageUrl}
              alt="Скан"
              style={{ maxWidth: '100%', borderRadius: 6 }}
            />
          )}
        </div>
      )}

      {scan.ocr_raw_text && (
        <div className="card mb-16">
          <h2 className="mb-16">Распознанный текст OCR</h2>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, background: 'rgba(255,255,255,0.1)', padding: 12, borderRadius: 6 }}>
            {scan.ocr_raw_text}
          </pre>
        </div>
      )}

      {/* Answer sheets for this attempt */}
      {answerSheets.length > 0 && (
        <div className="card mb-16">
          <h2 className="mb-16">Бланки ответов ({answerSheets.length})</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Тип</th>
                <th>ID</th>
                <th>Дата создания</th>
              </tr>
            </thead>
            <tbody>
              {answerSheets.map((sheet) => (
                <tr key={sheet.id}>
                  <td>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      fontWeight: 600,
                      background: sheet.kind === 'primary' ? '#f0fff4' : '#fefcbf',
                      color: sheet.kind === 'primary' ? '#22543d' : '#744210',
                    }}>
                      {sheet.kind === 'primary' ? 'Основной' : 'Дополнительный'}
                    </span>
                  </td>
                  <td style={{ fontSize: 12 }}>{sheet.id.slice(0, 8)}...</td>
                  <td>{new Date(sheet.created_at).toLocaleString('ru-RU')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Invigilator events for this attempt */}
      {events.length > 0 && (
        <div className="card mb-16">
          <h2 className="mb-16">События надзирателя</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Событие</th>
                <th>Время</th>
              </tr>
            </thead>
            <tbody>
              {events.map((evt) => (
                <tr key={evt.id}>
                  <td>{EVENT_LABELS[evt.event_type] || evt.event_type}</td>
                  <td>{new Date(evt.timestamp).toLocaleString('ru-RU')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!scan.verified_by && (
        <div className="card">
          <h2 className="mb-16">Подтвердить балл</h2>
          {!scan.attempt_id && (
            <div className="alert alert-error mb-16" style={{ fontSize: 13 }}>
              QR-код не распознан. Укажите ID попытки вручную, чтобы привязать скан.
            </div>
          )}
          {!scan.attempt_id && (
            <Input
              label="ID попытки (attempt_id)"
              type="text"
              value={manualAttemptId}
              onChange={(e) => setManualAttemptId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
          )}
          <Input
            label="Исправленный балл"
            type="number"
            value={correctedScore}
            onChange={(e) => setCorrectedScore(e.target.value)}
            placeholder="Введите проверенный балл"
          />
          <Button onClick={handleVerify} loading={verifying}>
            Подтвердить
          </Button>
        </div>
      )}
    </Layout>
  );
};

export default ScanDetailPage;
