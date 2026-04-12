import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/client';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';

interface StaffBadgeItem {
  id: string;
  competition_id: string | null;
  full_name: string;
  role: string;
  institution: string | null;
  has_photo: boolean;
  created_at: string;
}

interface CompetitionOption {
  id: string;
  name: string;
}

const StaffBadgesPage: React.FC = () => {
  const navigate = useNavigate();
  const [badges, setBadges] = useState<StaffBadgeItem[]>([]);
  const [competitions, setCompetitions] = useState<CompetitionOption[]>([]);
  const [selectedCompetitionId, setSelectedCompetitionId] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Manual form
  const [showManualForm, setShowManualForm] = useState(false);
  const [manualName, setManualName] = useState('');
  const [manualRole, setManualRole] = useState('');
  const [manualInstitution, setManualInstitution] = useState('');
  const [manualPhoto, setManualPhoto] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Import
  const [importing, setImporting] = useState(false);
  const [generating, setGenerating] = useState(false);

  const jsonFileRef = useRef<HTMLInputElement>(null);
  const xlsxFileRef = useRef<HTMLInputElement>(null);
  const jsonZipRef = useRef<HTMLInputElement>(null);
  const xlsxZipRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadCompetitions();
  }, []);

  useEffect(() => {
    loadBadges();
  }, [selectedCompetitionId]);

  const loadCompetitions = async () => {
    try {
      const { data } = await api.get<{ competitions: CompetitionOption[] }>('competitions');
      setCompetitions(data.competitions || []);
    } catch {
      // ignore
    }
  };

  const loadBadges = async () => {
    setLoading(true);
    try {
      const params = selectedCompetitionId ? `?competition_id=${selectedCompetitionId}` : '';
      const { data } = await api.get<{ items: StaffBadgeItem[]; total: number }>(`admin/staff-badges${params}`);
      setBadges(data.items || []);
    } catch {
      setError('Не удалось загрузить бейджи');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateManual = async () => {
    if (!manualName.trim() || !manualRole.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('full_name', manualName.trim());
      formData.append('role', manualRole.trim());
      if (manualInstitution.trim()) formData.append('institution', manualInstitution.trim());
      if (selectedCompetitionId) formData.append('competition_id', selectedCompetitionId);
      if (manualPhoto) formData.append('photo', manualPhoto);

      await api.post('admin/staff-badges', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setManualName('');
      setManualRole('');
      setManualInstitution('');
      setManualPhoto(null);
      setSuccess('Бейдж добавлен');
      await loadBadges();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Ошибка добавления');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`admin/staff-badges/${id}`);
      setBadges((prev) => prev.filter((b) => b.id !== id));
    } catch {
      setError('Ошибка удаления');
    }
  };

  const handleDeleteAll = async () => {
    if (!confirm('Удалить все бейджи руководителей?')) return;
    try {
      const params = selectedCompetitionId ? `?competition_id=${selectedCompetitionId}` : '';
      await api.delete(`admin/staff-badges${params}`);
      setBadges([]);
      setSuccess('Все бейджи удалены');
    } catch {
      setError('Ошибка удаления');
    }
  };

  const handleImportJson = async () => {
    const dataFile = jsonFileRef.current?.files?.[0];
    if (!dataFile) return;
    setImporting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('data_file', dataFile);
      const zipFile = jsonZipRef.current?.files?.[0];
      if (zipFile) formData.append('photos_zip', zipFile);
      if (selectedCompetitionId) formData.append('competition_id', selectedCompetitionId);

      const { data } = await api.post<{ total: number }>('admin/staff-badges/import-json', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSuccess(`Импортировано ${data.total} записей из JSON`);
      if (jsonFileRef.current) jsonFileRef.current.value = '';
      if (jsonZipRef.current) jsonZipRef.current.value = '';
      await loadBadges();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Ошибка импорта JSON');
    } finally {
      setImporting(false);
    }
  };

  const handleImportXlsx = async () => {
    const dataFile = xlsxFileRef.current?.files?.[0];
    if (!dataFile) return;
    setImporting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('data_file', dataFile);
      const zipFile = xlsxZipRef.current?.files?.[0];
      if (zipFile) formData.append('photos_zip', zipFile);
      if (selectedCompetitionId) formData.append('competition_id', selectedCompetitionId);

      const { data } = await api.post<{ total: number }>('admin/staff-badges/import-xlsx', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSuccess(`Импортировано ${data.total} записей из XLSX`);
      if (xlsxFileRef.current) xlsxFileRef.current.value = '';
      if (xlsxZipRef.current) xlsxZipRef.current.value = '';
      await loadBadges();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Ошибка импорта XLSX');
    } finally {
      setImporting(false);
    }
  };

  const handleGeneratePdf = async () => {
    setGenerating(true);
    setError(null);
    try {
      const body: Record<string, any> = {};
      if (selectedCompetitionId) body.competition_id = selectedCompetitionId;

      const response = await api.post('admin/staff-badges/generate-pdf', body, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data as Blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'staff_badges.pdf';
      a.click();
      URL.revokeObjectURL(url);
      setSuccess('PDF сгенерирован');
    } catch (err: any) {
      let detail = 'Ошибка генерации PDF';
      if (err?.response?.data instanceof Blob) {
        try {
          const text = await (err.response.data as Blob).text();
          const parsed = JSON.parse(text);
          detail = parsed.detail || detail;
        } catch { /* ignore */ }
      } else {
        detail = err?.response?.data?.detail || detail;
      }
      setError(detail);
    } finally {
      setGenerating(false);
    }
  };

  const handleUploadPhoto = async (badgeId: string, file: File) => {
    const formData = new FormData();
    formData.append('photo', file);
    try {
      await api.post(`admin/staff-badges/${badgeId}/photo`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await loadBadges();
    } catch {
      setError('Ошибка загрузки фото');
    }
  };

  return (
    <Layout>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <h1 style={{ marginTop: 0 }}>Бейджи руководителей</h1>

        {error && <div className="alert alert-error mb-16">{error}</div>}
        {success && (
          <div className="alert alert-success mb-16" onClick={() => setSuccess(null)} style={{ cursor: 'pointer' }}>
            {success}
          </div>
        )}

        {/* Competition selector */}
        <div style={{ marginBottom: 20, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ fontWeight: 600, fontSize: 14 }}>Олимпиада:</label>
          <select
            value={selectedCompetitionId}
            onChange={(e) => setSelectedCompetitionId(e.target.value)}
            style={{ padding: '7px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14, minWidth: 280 }}
          >
            <option value="">— Все —</option>
            {competitions.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' }}>
          {selectedCompetitionId && (
            <Button onClick={() => navigate(`/admin/badge-editor/${selectedCompetitionId}`)}>
              Редактор бейджей
            </Button>
          )}
          <Button onClick={() => setShowManualForm(!showManualForm)} variant="secondary">
            {showManualForm ? 'Скрыть форму' : 'Добавить вручную'}
          </Button>
          <Button onClick={handleGeneratePdf} loading={generating} disabled={badges.length === 0 || generating}>
            Сгенерировать PDF
          </Button>
          {badges.length > 0 && (
            <Button onClick={handleDeleteAll} variant="secondary" style={{ color: '#dc2626' }}>
              Удалить все
            </Button>
          )}
        </div>

        {/* Manual form */}
        {showManualForm && (
          <div className="card" style={{ padding: 20, marginBottom: 20 }}>
            <h3 style={{ marginTop: 0 }}>Добавить бейдж вручную</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>ФИО *</label>
                <input
                  type="text" value={manualName} onChange={(e) => setManualName(e.target.value)}
                  placeholder="Иванов Иван Иванович"
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Роль *</label>
                <input
                  type="text" value={manualRole} onChange={(e) => setManualRole(e.target.value)}
                  placeholder="ПРЕДСТАВИТЕЛЬ БВВМУ"
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Учреждение</label>
                <input
                  type="text" value={manualInstitution} onChange={(e) => setManualInstitution(e.target.value)}
                  placeholder="БВВМУ"
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 14 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Фото</label>
                <input
                  type="file" accept="image/*" onChange={(e) => setManualPhoto(e.target.files?.[0] || null)}
                  style={{ fontSize: 13 }}
                />
              </div>
            </div>
            <div style={{ marginTop: 14 }}>
              <Button onClick={handleCreateManual} loading={submitting} disabled={!manualName.trim() || !manualRole.trim()}>
                Добавить
              </Button>
            </div>
          </div>
        )}

        {/* Import sections */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
          {/* JSON import */}
          <div className="card" style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0, fontSize: 15 }}>Импорт из JSON</h3>
            <div style={{ marginBottom: 8 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>JSON файл *</label>
              <input ref={jsonFileRef} type="file" accept=".json" style={{ fontSize: 13 }} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>ZIP с фотографиями</label>
              <input ref={jsonZipRef} type="file" accept=".zip" style={{ fontSize: 13 }} />
            </div>
            <Button onClick={handleImportJson} loading={importing} variant="secondary">
              Импортировать JSON
            </Button>
          </div>

          {/* XLSX import */}
          <div className="card" style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0, fontSize: 15 }}>Импорт из XLSX (Руководители)</h3>
            <div style={{ marginBottom: 8 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>XLSX файл *</label>
              <input ref={xlsxFileRef} type="file" accept=".xlsx,.xls" style={{ fontSize: 13 }} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>ZIP с фотографиями</label>
              <input ref={xlsxZipRef} type="file" accept=".zip" style={{ fontSize: 13 }} />
            </div>
            <Button onClick={handleImportXlsx} loading={importing} variant="secondary">
              Импортировать XLSX
            </Button>
          </div>
        </div>

        {/* Badges table */}
        <div className="card" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Список ({badges.length})</h3>
          {loading ? (
            <p style={{ color: '#9ca3af' }}>Загрузка...</p>
          ) : badges.length === 0 ? (
            <p style={{ color: '#9ca3af' }}>Нет бейджей. Добавьте вручную или импортируйте.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>ФИО</th>
                  <th>Роль</th>
                  <th>Учреждение</th>
                  <th>Фото</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {badges.map((b) => (
                  <tr key={b.id}>
                    <td>{b.full_name}</td>
                    <td>{b.role}</td>
                    <td>{b.institution || '—'}</td>
                    <td>
                      {b.has_photo ? (
                        <span style={{ color: '#16a34a', fontWeight: 600 }}>Есть</span>
                      ) : (
                        <label style={{ cursor: 'pointer', color: '#3b82f6', fontSize: 13 }}>
                          Загрузить
                          <input
                            type="file"
                            accept="image/*"
                            style={{ display: 'none' }}
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) handleUploadPhoto(b.id, file);
                            }}
                          />
                        </label>
                      )}
                    </td>
                    <td>
                      <button
                        onClick={() => handleDelete(b.id)}
                        style={{
                          background: 'none', border: 'none', color: '#dc2626',
                          cursor: 'pointer', fontSize: 13, fontWeight: 600,
                        }}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </Layout>
  );
};

export default StaffBadgesPage;
