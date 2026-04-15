import React, { useRef, useState } from 'react';
import api from '../../api/client';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';
import QRScanner from '../../components/qr/QRScanner';

interface ResolveQRResponse {
  attempt_id: string;
  tour_number: number | null;
  participant_name: string;
  participant_school: string | null;
  institution_name: string | null;
  institution_location: string | null;
  is_captain: boolean;
  dob: string | null;
  competition_id: string;
  competition_name: string;
  is_special: boolean;
  task_numbers: number[];
  tour_mode: string | null;
  is_captains_task: boolean;
  cap_task_number: number | null;
  captains_task_numbers: number[];
}

const TOUR_MODE_LABELS: Record<string, string> = {
  individual: 'Индивидуальный',
  individual_captains: 'Индивидуальный + задание капитана',
  team: 'Командный',
};

const QRLookupPage: React.FC = () => {
  const [inputMode, setInputMode] = useState<'laser' | 'camera'>('laser');
  const [laserInput, setLaserInput] = useState('');
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResolveQRResponse | null>(null);

  const laserRef = useRef<HTMLInputElement>(null);

  const handleToken = async (token: string) => {
    const t = token.trim();
    if (!t) return;
    setResolving(true);
    setError(null);
    setResult(null);
    try {
      const { data } = await api.post<ResolveQRResponse>('scans/resolve-qr', {
        sheet_token: t,
      });
      setResult(data);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(detail ?? 'QR-код не распознан');
    } finally {
      setResolving(false);
      setLaserInput('');
      // Re-focus laser input after resolve
      setTimeout(() => laserRef.current?.focus(), 50);
    }
  };

  const handleLaserKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleToken(laserInput);
  };

  const reset = () => {
    setResult(null);
    setError(null);
    setLaserInput('');
    setTimeout(() => laserRef.current?.focus(), 50);
  };

  return (
    <Layout>
      <div style={{ maxWidth: 600, margin: '0 auto' }}>
        <h2 style={{ marginTop: 0 }}>Проверка QR-кода</h2>

        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          <Button
            variant={inputMode === 'laser' ? 'primary' : 'secondary'}
            onClick={() => { setInputMode('laser'); setTimeout(() => laserRef.current?.focus(), 50); }}
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

        {/* Input */}
        <div className="card" style={{ padding: 20, marginBottom: 20 }}>
          {inputMode === 'laser' && (
            <>
              <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: '#555' }}>
                Наведите лазерный сканер и нажмите Enter:
              </label>
              <input
                ref={laserRef}
                autoFocus
                type="text"
                value={laserInput}
                onChange={(e) => setLaserInput(e.target.value)}
                onKeyDown={handleLaserKey}
                placeholder="QR-данные появятся здесь…"
                disabled={resolving}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  fontSize: 15,
                  borderRadius: 8,
                  border: '2px solid #3b82f6',
                  boxSizing: 'border-box',
                }}
              />
              {resolving && (
                <p style={{ color: '#888', marginTop: 8, fontSize: 13 }}>Определяем участника…</p>
              )}
            </>
          )}

          {inputMode === 'camera' && (
            <>
              <p style={{ fontSize: 13, color: '#555', marginTop: 0, marginBottom: 12 }}>
                Наведите камеру на QR-код — сканирование произойдёт автоматически:
              </p>
              <QRScanner
                onScan={(data) => { if (!resolving) void handleToken(data); }}
              />
              {resolving && (
                <p style={{ color: '#888', marginTop: 8, fontSize: 13 }}>Определяем участника…</p>
              )}
            </>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="alert alert-error" style={{ marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="card" style={{ padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 16, color: '#1e40af' }}>Участник найден</h3>
              <Button variant="secondary" onClick={reset}>
                Новое сканирование
              </Button>
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <tbody>
                <InfoRow label="ФИО" value={result.participant_name} />
                <InfoRow
                  label="Учреждение"
                  value={result.institution_name ?? result.participant_school ?? '—'}
                />
                {result.institution_location && (
                  <InfoRow label="Город" value={result.institution_location} />
                )}
                <InfoRow label="Олимпиада" value={result.competition_name} />
                {result.is_captain && (
                  <InfoRow label="Роль" value="Капитан команды" highlight />
                )}
                {result.dob && (
                  <InfoRow label="Дата рождения" value={result.dob} />
                )}
                {result.is_special && result.tour_number != null && (
                  <>
                    <InfoRow label="Тур" value={String(result.tour_number)} />
                    {result.tour_mode && (
                      <InfoRow
                        label="Режим тура"
                        value={TOUR_MODE_LABELS[result.tour_mode] ?? result.tour_mode}
                      />
                    )}
                    {result.task_numbers.length > 0 && (
                      <InfoRow
                        label="Задания"
                        value={result.task_numbers.join(', ')}
                      />
                    )}
                    {result.is_captains_task && (
                      <InfoRow
                        label="Задание капитана"
                        value={result.cap_task_number != null ? `#${result.cap_task_number}` : 'Да'}
                        highlight
                      />
                    )}
                  </>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  );
};

interface InfoRowProps {
  label: string;
  value: string;
  highlight?: boolean;
}

const InfoRow: React.FC<InfoRowProps> = ({ label, value, highlight }) => (
  <tr>
    <td
      style={{
        padding: '7px 0',
        paddingRight: 12,
        color: '#6b7280',
        fontWeight: 500,
        whiteSpace: 'nowrap',
        verticalAlign: 'top',
        width: '40%',
        borderBottom: '1px solid #f3f4f6',
      }}
    >
      {label}
    </td>
    <td
      style={{
        padding: '7px 0',
        fontWeight: highlight ? 700 : 400,
        color: highlight ? '#1d4ed8' : '#111827',
        borderBottom: '1px solid #f3f4f6',
      }}
    >
      {value}
    </td>
  </tr>
);

export default QRLookupPage;
