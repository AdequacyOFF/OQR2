import React, { useState, useRef, useEffect } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import api from '../../api/client';
import Layout from '../../components/layout/Layout';
import QRScanner from '../../components/qr/QRScanner';
import QRCodeDisplay from '../../components/qr/QRCodeDisplay';
import Button from '../../components/common/Button';
import Spinner from '../../components/common/Spinner';
import FileUploader from '../../components/upload/FileUploader';

interface DocumentInfo {
  id: string;
  file_path: string;
  file_type: string;
  created_at: string;
}

interface VerifyResponse {
  registration_id: string;
  participant_name: string;
  participant_school: string;
  participant_grade: number;
  competition_name: string;
  competition_id: string;
  can_proceed: boolean;
  message: string;
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
  has_documents: boolean;
  participant_id?: string;
}

interface ApproveResponse {
  attempt_id: string;
  variant_number: number;
  pdf_url: string;
  sheet_token: string;
  room_name: string | null;
  seat_number: number | null;
}

const AdmissionPage: React.FC = () => {
  const [scanMode, setScanMode] = useState<'camera' | 'upload' | 'laser'>('camera');
  const [scanning, setScanning] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [approving, setApproving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifyData, setVerifyData] = useState<VerifyResponse | null>(null);
  const [approveData, setApproveData] = useState<ApproveResponse | null>(null);
  const [scannedToken, setScannedToken] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [docViewUrl, setDocViewUrl] = useState<string | null>(null);
  const [docViewType, setDocViewType] = useState<string>('');
  const laserInputRef = useRef<HTMLInputElement>(null);

  // Auto-focus laser input when in laser mode
  useEffect(() => {
    if (scanMode === 'laser' && scanning && laserInputRef.current) {
      laserInputRef.current.focus();
    }
  }, [scanMode, scanning]);

  const handleScan = async (data: string) => {
    setScanning(false);
    setError(null);
    setVerifying(true);
    setScannedToken(data);

    try {
      const { data: result } = await api.post<VerifyResponse>('admission/verify', {
        token: data,
      });
      setVerifyData(result);
      // Load documents if available
      if (result.has_documents && result.participant_id) {
        try {
          const { data: docs } = await api.get<{ documents: DocumentInfo[] }>(
            `documents/participant/${result.participant_id}`
          );
          setDocuments(docs.documents || []);
        } catch {
          // Documents may not be accessible
        }
      }
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка проверки.';
      setError(message);
    } finally {
      setVerifying(false);
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

  const handleApprove = async () => {
    if (!verifyData || !scannedToken) return;
    setApproving(true);
    setError(null);

    try {
      const { data: result } = await api.post<ApproveResponse>(
        `admission/${verifyData.registration_id}/approve`,
        {
          raw_entry_token: scannedToken,
        }
      );
      setApproveData(result);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка подтверждения.';
      setError(message);
    } finally {
      setApproving(false);
    }
  };

  const handleReset = () => {
    setScanning(true);
    setVerifyData(null);
    setApproveData(null);
    setError(null);
    setScannedToken(null);
    setProcessing(false);
    setDocuments([]);
    if (docViewUrl) {
      URL.revokeObjectURL(docViewUrl);
      setDocViewUrl(null);
    }
    setDocViewType('');
  };

  const handleViewDocument = async (doc: DocumentInfo) => {
    try {
      if (docViewUrl) URL.revokeObjectURL(docViewUrl);
      const response = await api.get(`documents/${doc.id}/download`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data as Blob);
      setDocViewUrl(url);
      setDocViewType(doc.file_type);
    } catch {
      setError('Не удалось загрузить документ.');
    }
  };

  const handleFileUpload = async (file: File) => {
    setProcessing(true);
    setError(null);
    setScanning(false);

    try {
      const tempId = 'qr-temp-' + Date.now();
      const tempDiv = document.createElement('div');
      tempDiv.id = tempId;
      tempDiv.style.display = 'none';
      document.body.appendChild(tempDiv);

      try {
        const html5QrCode = new Html5Qrcode(tempId);
        const decodedText = await html5QrCode.scanFile(file, false);
        await handleScan(decodedText);
        html5QrCode.clear();
      } finally {
        document.body.removeChild(tempDiv);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Не удалось распознать QR-код на изображении';
      setError(message);
      setScanning(true);
    } finally {
      setProcessing(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!approveData) return;
    setDownloading(true);
    setError(null);

    try {
      const response = await api.get(approveData.pdf_url, {
        responseType: 'blob',
      });

      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `answer_sheet_${approveData.attempt_id}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка скачивания PDF.';
      setError(message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Layout>
      <h1 className="mb-24">Допуск участников</h1>

      {error && <div className="alert alert-error mb-16">{error}</div>}

      {scanning && (
        <div className="card">
          {/* Mode toggle buttons */}
          <div className="scan-mode-toggle mb-24">
            <button
              className={`mode-btn ${scanMode === 'camera' ? 'active' : ''}`}
              onClick={() => setScanMode('camera')}
              disabled={processing}
            >
              Камера
            </button>
            <button
              className={`mode-btn ${scanMode === 'upload' ? 'active' : ''}`}
              onClick={() => setScanMode('upload')}
              disabled={processing}
            >
              Загрузить фото
            </button>
            <button
              className={`mode-btn ${scanMode === 'laser' ? 'active' : ''}`}
              onClick={() => setScanMode('laser')}
              disabled={processing}
            >
              Лазер
            </button>
          </div>

          {scanMode === 'camera' ? (
            <>
              <h2 className="mb-16">Сканировать входной QR-код камерой</h2>
              <QRScanner
                onScan={handleScan}
                onError={(err) => console.error('Ошибка QR:', err)}
              />
            </>
          ) : scanMode === 'upload' ? (
            <>
              <h2 className="mb-16">Загрузить фото QR-кода</h2>
              <FileUploader
                onUpload={handleFileUpload}
                uploading={processing}
                accept="image/*"
                maxSizeMB={10}
              />
            </>
          ) : (
            <>
              <h2 className="mb-16">Лазерный сканер</h2>
              <p className="text-muted mb-16">
                Наведите лазерный сканер на QR-код. Результат появится автоматически.
              </p>
              <input
                ref={laserInputRef}
                type="text"
                className="input laser-input"
                placeholder="Ожидание сканирования..."
                onKeyDown={handleLaserInput}
                autoFocus
                style={{
                  width: '100%',
                  padding: '16px',
                  fontSize: '18px',
                  textAlign: 'center',
                  border: '2px solid #4299e1',
                  borderRadius: '8px',
                }}
              />
            </>
          )}
        </div>
      )}

      {verifying && (
        <div className="card">
          <Spinner />
          <p className="text-center mt-16">Проверка участника...</p>
        </div>
      )}

      {processing && (
        <div className="card">
          <Spinner />
          <p className="text-center mt-16">Распознавание QR-кода...</p>
        </div>
      )}

      {verifyData && !approveData && (
        <div className="card">
          <h2 className="mb-16">Проверка участника</h2>

          {!verifyData.can_proceed && (
            <div className="alert alert-error mb-16">
              {verifyData.message}
            </div>
          )}

          <table className="table mb-16">
            <tbody>
              <tr>
                <td><strong>ФИО</strong></td>
                <td>{verifyData.participant_name}</td>
              </tr>
              <tr>
                <td><strong>Школа</strong></td>
                <td>{verifyData.participant_school}</td>
              </tr>
              {verifyData.institution_name && (
                <tr>
                  <td><strong>Учреждение</strong></td>
                  <td>{verifyData.institution_name}{verifyData.institution_location ? ` (${verifyData.institution_location})` : ''}</td>
                </tr>
              )}
              <tr>
                <td><strong>Класс</strong></td>
                <td>{verifyData.participant_grade}</td>
              </tr>
              {verifyData.dob && (
                <tr>
                  <td><strong>Дата рождения</strong></td>
                  <td>{new Date(verifyData.dob).toLocaleDateString('ru-RU')}</td>
                </tr>
              )}
              {verifyData.is_captain && (
                <tr>
                  <td><strong>Капитан</strong></td>
                  <td style={{ color: '#2563eb', fontWeight: 600 }}>Да</td>
                </tr>
              )}
              {verifyData.position && (
                <tr>
                  <td><strong>Должность</strong></td>
                  <td>{verifyData.position}</td>
                </tr>
              )}
              {verifyData.military_rank && (
                <tr>
                  <td><strong>Воинское звание</strong></td>
                  <td>{verifyData.military_rank}</td>
                </tr>
              )}
              {verifyData.passport_series_number && (
                <tr>
                  <td><strong>Паспорт</strong></td>
                  <td>{verifyData.passport_series_number}</td>
                </tr>
              )}
              {verifyData.passport_issued_by && (
                <tr>
                  <td><strong>Выдан</strong></td>
                  <td>{verifyData.passport_issued_by}</td>
                </tr>
              )}
              {verifyData.passport_issued_date && (
                <tr>
                  <td><strong>Дата выдачи</strong></td>
                  <td>{new Date(verifyData.passport_issued_date).toLocaleDateString('ru-RU')}</td>
                </tr>
              )}
              {verifyData.military_booklet_number && (
                <tr>
                  <td><strong>Военный билет</strong></td>
                  <td>{verifyData.military_booklet_number}</td>
                </tr>
              )}
              {verifyData.military_personal_number && (
                <tr>
                  <td><strong>Личный номер</strong></td>
                  <td>{verifyData.military_personal_number}</td>
                </tr>
              )}
              <tr>
                <td><strong>Олимпиада</strong></td>
                <td>{verifyData.competition_name}</td>
              </tr>
              <tr>
                <td><strong>Документы</strong></td>
                <td>{verifyData.has_documents ? 'Загружены' : 'Не загружены'}</td>
              </tr>
              <tr>
                <td><strong>Статус</strong></td>
                <td>{verifyData.message}</td>
              </tr>
            </tbody>
          </table>

          {/* Document viewer */}
          {documents.length > 0 && (
            <div className="mb-16">
              <h3 className="mb-8">Документы участника</h3>
              <div className="flex gap-8 mb-8" style={{ flexWrap: 'wrap' }}>
                {documents.map((doc) => (
                  <button
                    key={doc.id}
                    className="btn btn-secondary"
                    style={{ fontSize: '13px', padding: '6px 12px' }}
                    onClick={() => handleViewDocument(doc)}
                  >
                    {doc.file_type.toUpperCase()} ({new Date(doc.created_at).toLocaleDateString('ru-RU')})
                  </button>
                ))}
              </div>
              {docViewUrl && (
                <div style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  background: '#f7fafc',
                }}>
                  {docViewType === 'pdf' ? (
                    <iframe
                      src={docViewUrl}
                      style={{ width: '100%', height: '500px', border: 'none' }}
                      title="Документ участника"
                    />
                  ) : (
                    <img
                      src={docViewUrl}
                      alt="Документ участника"
                      style={{ maxWidth: '100%', maxHeight: '500px', display: 'block', margin: '0 auto' }}
                    />
                  )}
                </div>
              )}
            </div>
          )}

          <div className="flex gap-8">
            <Button
              onClick={handleApprove}
              loading={approving}
              disabled={!verifyData.can_proceed}
            >
              Подтвердить допуск
            </Button>
            <Button variant="secondary" onClick={handleReset}>
              Отмена
            </Button>
          </div>
        </div>
      )}

      {approveData && (
        <div className="card">
          <div className="alert alert-success mb-16">
            Участник успешно допущен!
          </div>
          <h2 className="mb-16">Бланк ответов</h2>

          {(approveData.room_name || approveData.seat_number) && (
            <div className="seating-info mb-16" style={{
              background: '#ebf8ff',
              border: '2px solid #4299e1',
              borderRadius: '8px',
              padding: '16px',
              textAlign: 'center',
            }}>
              {approveData.room_name && (
                <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#2b6cb0' }}>
                  Аудитория: {approveData.room_name}
                </div>
              )}
              {approveData.seat_number && (
                <div style={{ fontSize: '18px', fontWeight: '600', color: '#2c5282', marginTop: '4px' }}>
                  Место: {approveData.seat_number}
                </div>
              )}
              <div style={{ fontSize: '16px', color: '#4a5568', marginTop: '4px' }}>
                Вариант: {approveData.variant_number}
              </div>
            </div>
          )}

          <div className="mb-16">
            <Button onClick={handleDownloadPdf} loading={downloading}>
              Скачать бланк ответов PDF
            </Button>
          </div>
          <h3 className="mb-16">QR-код бланка</h3>
          <QRCodeDisplay value={approveData.sheet_token} size={200} />
          <p className="text-muted text-center mt-16" style={{ fontSize: 12, wordBreak: 'break-all' }}>
            Токен бланка: {approveData.sheet_token}
          </p>
          <div className="mt-16">
            <Button variant="secondary" onClick={handleReset}>
              Следующий участник
            </Button>
          </div>
        </div>
      )}

      <style>{`
        .scan-mode-toggle {
          display: flex;
          gap: 12px;
          justify-content: center;
          border-bottom: 2px solid #e2e8f0;
          padding-bottom: 16px;
        }

        .mode-btn {
          flex: 1;
          max-width: 200px;
          padding: 12px 24px;
          font-size: 16px;
          font-weight: 600;
          border: 2px solid #cbd5e0;
          border-radius: 8px;
          background: white;
          color: #4a5568;
          cursor: pointer;
          transition: all 0.3s ease;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }

        .mode-btn:hover:not(:disabled) {
          border-color: #4299e1;
          background: #ebf8ff;
          color: #2b6cb0;
          transform: translateY(-2px);
          box-shadow: 0 4px 8px rgba(66, 153, 225, 0.2);
        }

        .mode-btn.active {
          border-color: #4299e1;
          background: #4299e1;
          color: white;
          box-shadow: 0 4px 12px rgba(66, 153, 225, 0.4);
        }

        .mode-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        @media (max-width: 640px) {
          .scan-mode-toggle {
            flex-direction: column;
          }

          .mode-btn {
            max-width: 100%;
          }
        }
      `}</style>
    </Layout>
  );
};

export default AdmissionPage;
