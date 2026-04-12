import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import api from '../../api/client';
import type { Competition, Registration, ParticipantProfile } from '../../types';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';
import Spinner from '../../components/common/Spinner';
import Input from '../../components/common/Input';
import InstitutionAutocomplete from '../../components/common/InstitutionAutocomplete';
import QRCodeDisplay from '../../components/qr/QRCodeDisplay';
import useAuthStore from '../../store/authStore';
import logoBlue from '../../assets/images/logo/logo_blue.png';

type TabType = 'profile' | 'registrations' | 'competitions';

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<TabType>('profile');
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [profile, setProfile] = useState<ParticipantProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [registeringId, setRegisteringId] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editForm, setEditForm] = useState({
    full_name: '',
    school: '',
    grade: 0,
    dob: '',
    institution_id: null as string | null | undefined,
  });
  const [printingReg, setPrintingReg] = useState<{ token: string; compName: string } | null>(null);
  const printRef = useRef<HTMLDivElement>(null);

  const handlePrintBadge = useCallback((token: string, compName: string) => {
    setPrintingReg({ token, compName });
    setTimeout(() => {
      window.print();
      setPrintingReg(null);
    }, 300);
  }, []);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [compRes, regRes, profileRes] = await Promise.all([
        api.get<{ competitions: Competition[]; total: number }>('competitions'),
        api.get<{ items: Registration[]; total: number }>('registrations'),
        api.get<ParticipantProfile>('profile'),
      ]);
      setCompetitions(compRes.data.competitions || []);
      setRegistrations(regRes.data.items || []);
      setProfile(profileRes.data);
      setEditForm({
        full_name: profileRes.data.full_name,
        school: profileRes.data.school,
        grade: profileRes.data.grade,
        dob: profileRes.data.dob || '',
        institution_id: profileRes.data.institution_id,
      });
    } catch {
      setError('Не удалось загрузить данные.');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (competitionId: string) => {
    setRegisteringId(competitionId);
    setError(null);
    try {
      const { data } = await api.post<Registration>('registrations', {
        competition_id: competitionId,
      });
      setRegistrations((prev) => [...prev, data]);
      setActiveTab('registrations');
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка регистрации.';
      setError(message);
    } finally {
      setRegisteringId(null);
    }
  };

  const handleSaveProfile = async () => {
    setSaving(true);
    setError(null);
    try {
      const { data } = await api.put<ParticipantProfile>('profile', editForm);
      setProfile(data);
      setEditMode(false);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка сохранения профиля.';
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const isRegistered = (competitionId: string) =>
    registrations.some((r) => r.competition_id === competitionId);

  const getStatusLabel = (status: string): string => {
    const labels: Record<string, string> = {
      draft: 'Черновик',
      registration_open: 'Регистрация открыта',
      in_progress: 'Проходит',
      checking: 'Проверка работ',
      published: 'Результаты опубликованы',
    };
    return labels[status] || status;
  };

  const getRegStatusLabel = (status: string): string => {
    const labels: Record<string, string> = {
      pending: 'Зарегистрирован',
      admitted: 'Допущен',
      completed: 'Завершен',
      cancelled: 'Отменен',
    };
    return labels[status] || status;
  };

  const getRegStatusColor = (status: string): string => {
    const colors: Record<string, string> = {
      pending: 'blue',
      admitted: 'green',
      completed: 'purple',
      cancelled: 'red',
    };
    return colors[status] || 'gray';
  };

  if (loading) {
    return (
      <Layout>
        <Spinner />
      </Layout>
    );
  }

  return (
    <Layout>
      <h1 className="mb-24">Личный кабинет</h1>

      {error && <div className="alert alert-error mb-16">{error}</div>}

      {/* Tabs */}
      <div className="tabs mb-24">
        <button
          className={`tab ${activeTab === 'profile' ? 'active' : ''}`}
          onClick={() => setActiveTab('profile')}
        >
          Профиль
        </button>
        <button
          className={`tab ${activeTab === 'registrations' ? 'active' : ''}`}
          onClick={() => setActiveTab('registrations')}
        >
          Мои регистрации ({registrations.length})
        </button>
        <button
          className={`tab ${activeTab === 'competitions' ? 'active' : ''}`}
          onClick={() => setActiveTab('competitions')}
        >
          Доступные олимпиады ({competitions.filter(c => !isRegistered(c.id)).length})
        </button>
      </div>

      {/* Profile Tab */}
      {activeTab === 'profile' && profile && (
        <div className="card">
          <div className="flex-between mb-24">
            <h2>Личная информация</h2>
            {!editMode && (
              <Button variant="secondary" onClick={() => setEditMode(true)}>
                Редактировать
              </Button>
            )}
          </div>

          {editMode ? (
            <div>
              <Input
                label="ФИО"
                value={editForm.full_name}
                onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
              />
              <div className="form-group">
                <label className="label">Учебное учреждение</label>
                <InstitutionAutocomplete
                  value={editForm.school}
                  onChange={(val, instId) => setEditForm({
                    ...editForm,
                    school: val,
                    institution_id: instId || editForm.institution_id,
                  })}
                  placeholder="Начните вводить название..."
                />
              </div>
              <Input
                label="Дата рождения"
                type="date"
                value={editForm.dob}
                onChange={(e) => setEditForm({ ...editForm, dob: e.target.value })}
              />
              <Input
                label="Класс"
                type="number"
                value={editForm.grade}
                onChange={(e) => setEditForm({ ...editForm, grade: parseInt(e.target.value) })}
              />
              <div className="flex gap-8 mt-16">
                <Button onClick={handleSaveProfile} loading={saving}>
                  Сохранить
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setEditMode(false);
                    setEditForm({
                      full_name: profile.full_name,
                      school: profile.school,
                      grade: profile.grade,
                      dob: profile.dob || '',
                      institution_id: profile.institution_id,
                    });
                  }}
                >
                  Отмена
                </Button>
              </div>
            </div>
          ) : (
            <div className="profile-info">
              <div className="info-row">
                <span className="info-label">Email:</span>
                <span className="info-value">{user?.email}</span>
              </div>
              <div className="info-row">
                <span className="info-label">ФИО:</span>
                <span className="info-value">{profile.full_name}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Учебное учреждение:</span>
                <span className="info-value">{profile.school}</span>
              </div>
              {profile.dob && (
                <div className="info-row">
                  <span className="info-label">Дата рождения:</span>
                  <span className="info-value">{new Date(profile.dob).toLocaleDateString('ru-RU')}</span>
                </div>
              )}
              <div className="info-row">
                <span className="info-label">Класс:</span>
                <span className="info-value">{profile.grade}</span>
              </div>
              {profile.position && (
                <div className="info-row">
                  <span className="info-label">Должность:</span>
                  <span className="info-value">{profile.position}</span>
                </div>
              )}
              {profile.military_rank && (
                <div className="info-row">
                  <span className="info-label">Воинское звание:</span>
                  <span className="info-value">{profile.military_rank}</span>
                </div>
              )}
              {profile.passport_series_number && (
                <div className="info-row">
                  <span className="info-label">Паспорт:</span>
                  <span className="info-value">{profile.passport_series_number}</span>
                </div>
              )}
              {profile.passport_issued_by && (
                <div className="info-row">
                  <span className="info-label">Выдан:</span>
                  <span className="info-value">{profile.passport_issued_by}</span>
                </div>
              )}
              {profile.passport_issued_date && (
                <div className="info-row">
                  <span className="info-label">Дата выдачи:</span>
                  <span className="info-value">{new Date(profile.passport_issued_date).toLocaleDateString('ru-RU')}</span>
                </div>
              )}
              {profile.military_booklet_number && (
                <div className="info-row">
                  <span className="info-label">Военный билет:</span>
                  <span className="info-value">{profile.military_booklet_number}</span>
                </div>
              )}
              {profile.military_personal_number && (
                <div className="info-row">
                  <span className="info-label">Личный номер:</span>
                  <span className="info-value">{profile.military_personal_number}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Registrations Tab */}
      {activeTab === 'registrations' && (
        <div>
          {registrations.length === 0 ? (
            <div className="card text-center">
              <p className="text-muted mb-16">Вы пока не зарегистрированы ни на одну олимпиаду</p>
              <Button onClick={() => setActiveTab('competitions')}>
                Посмотреть доступные олимпиады
              </Button>
            </div>
          ) : (
            <div className="registrations-grid">
              {registrations.map((reg) => {
                const comp = competitions.find((c) => c.id === reg.competition_id);
                return (
                  <div key={reg.id} className="card registration-card">
                    <div className="reg-header">
                      <h3>{comp?.name || 'Олимпиада'}</h3>
                      <span className={`status-badge status-${getRegStatusColor(reg.status)}`}>
                        {getRegStatusLabel(reg.status)}
                      </span>
                    </div>

                    {comp && (
                      <div className="reg-info">
                        <p className="text-muted">
                          Дата: {new Date(comp.date).toLocaleDateString('ru-RU')}
                        </p>
                        {reg.variant_number && (
                          <p className="text-muted">Вариант: {reg.variant_number}</p>
                        )}
                      </div>
                    )}

                    {reg.entry_token && (reg.status === 'pending' || reg.status === 'admitted') && (
                      <div className="qr-section mt-16">
                        <p className="text-center mb-8"><strong>QR-код для допуска</strong></p>
                        <div className="qr-container">
                          <QRCodeDisplay value={reg.entry_token} size={180} />
                        </div>
                        <p className="text-muted text-center mt-8" style={{ fontSize: 10 }}>
                          {reg.status === 'pending'
                            ? 'Покажите этот QR-код при допуске'
                            : 'Вы допущены к олимпиаде'}
                        </p>
                        <Button
                          variant="secondary"
                          className="mt-8 btn-sm"
                          onClick={() => handlePrintBadge(reg.entry_token!, comp?.name || 'Олимпиада')}
                        >
                          Распечатать бейдж
                        </Button>
                      </div>
                    )}

                    {reg.final_score !== undefined && reg.final_score !== null && comp && (
                      <div className="score-section mt-16">
                        <div className="score-display">
                          <span className="score-label">Итоговый балл:</span>
                          <span className="score-value">
                            {reg.final_score} / {comp.max_score}
                          </span>
                        </div>
                        {comp.status === 'published' && (
                          <Button
                            variant="secondary"
                            className="mt-8"
                            onClick={() => navigate(`/results/${comp.id}`)}
                          >
                            Посмотреть результаты
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Competitions Tab */}
      {activeTab === 'competitions' && (
        <div className="grid grid-2">
          {competitions.filter(c => !isRegistered(c.id)).length === 0 ? (
            <p className="text-muted">Нет доступных олимпиад для регистрации.</p>
          ) : (
            competitions
              .filter(c => !isRegistered(c.id))
              .map((comp) => (
                <div key={comp.id} className="card">
                  <h3>{comp.name}</h3>
                  <p className="text-muted">
                    Дата: {new Date(comp.date).toLocaleDateString('ru-RU')}
                  </p>
                  <p className="text-muted">
                    Регистрация: {new Date(comp.registration_start).toLocaleDateString('ru-RU')} -{' '}
                    {new Date(comp.registration_end).toLocaleDateString('ru-RU')}
                  </p>
                  <p className="text-muted">Статус: {getStatusLabel(comp.status)}</p>
                  <p className="text-muted">Макс. балл: {comp.max_score}</p>
                  <p className="text-muted">Вариантов: {comp.variants_count}</p>
                  <div className="mt-16">
                    {comp.status === 'registration_open' ? (
                      <Button
                        onClick={() => handleRegister(comp.id)}
                        loading={registeringId === comp.id}
                      >
                        Зарегистрироваться
                      </Button>
                    ) : (
                      <span className="text-muted">Регистрация закрыта</span>
                    )}
                  </div>
                </div>
              ))
          )}
        </div>
      )}

      {/* Print-only badge */}
      {printingReg && profile && (
        <div ref={printRef} className="print-badge-wrapper">
          <div className="print-badge">
            <img src={logoBlue} alt="OlimpQR" className="print-badge-logo" />
            <div className="print-badge-title">OlimpQR</div>
            <div className="print-badge-comp">{printingReg.compName}</div>
            <div className="print-badge-name">{profile.full_name}</div>
            <div className="print-badge-school">{profile.school}</div>
            <div className="print-badge-qr">
              <QRCodeSVG value={printingReg.token} size={180} />
            </div>
            <div className="print-badge-hint">Покажите QR-код для допуска</div>
          </div>
        </div>
      )}

      <style>{`
        .tabs {
          display: flex;
          gap: 8px;
          border-bottom: 2px solid var(--glass-border);
          padding-bottom: 0;
        }

        .tab {
          padding: 12px 24px;
          background: none;
          border: none;
          border-bottom: 3px solid transparent;
          color: var(--text-secondary);
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
          position: relative;
          bottom: -2px;
        }

        .tab:hover {
          color: var(--accent-primary);
          background: var(--glass-light);
        }

        .tab.active {
          color: var(--accent-primary);
          border-bottom-color: var(--accent-primary);
        }

        .profile-info {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .info-row {
          display: flex;
          padding: 12px 0;
          border-bottom: 1px solid var(--glass-border);
        }

        .info-row:last-child {
          border-bottom: none;
        }

        .info-label {
          font-weight: 600;
          color: var(--text-secondary);
          min-width: 120px;
        }

        .info-value {
          color: var(--text-primary);
        }

        .registrations-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 24px;
        }

        .registration-card {
          display: flex;
          flex-direction: column;
        }

        .reg-header {
          display: flex;
          justify-content: space-between;
          align-items: start;
          margin-bottom: 16px;
          gap: 12px;
        }

        .reg-header h3 {
          margin: 0;
          flex: 1;
        }

        .status-badge {
          padding: 4px 12px;
          border-radius: 12px;
          font-size: 12px;
          font-weight: 600;
          white-space: nowrap;
        }

        .status-blue {
          background: #ebf8ff;
          color: #2b6cb0;
        }

        .status-green {
          background: #f0fff4;
          color: #22543d;
        }

        .status-purple {
          background: #faf5ff;
          color: #553c9a;
        }

        .status-red {
          background: #fff5f5;
          color: #c53030;
        }

        .status-gray {
          background: #f7fafc;
          color: #4a5568;
        }

        .reg-info {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .qr-section {
          background: var(--glass-light);
          padding: 16px;
          border-radius: 8px;
          text-align: center;
        }

        .qr-container {
          display: flex;
          justify-content: center;
          padding: 12px;
          background: white;
          border-radius: 8px;
        }

        .score-section {
          background: var(--glass-light);
          padding: 16px;
          border-radius: 8px;
        }

        .score-display {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 16px;
        }

        .score-label {
          font-weight: 600;
          color: var(--text-secondary);
        }

        .score-value {
          font-size: 24px;
          font-weight: 800;
          color: var(--accent-primary);
        }

        @media (max-width: 640px) {
          .tabs {
            overflow-x: auto;
          }

          .tab {
            padding: 10px 16px;
            font-size: 13px;
          }

          .registrations-grid {
            grid-template-columns: 1fr;
          }

          .reg-header {
            flex-direction: column;
            align-items: start;
          }
        }

        /* Print badge - hidden on screen */
        .print-badge-wrapper {
          display: none;
        }

        @media print {
          /* Hide everything except badge */
          body > *:not(.print-badge-wrapper) {
            display: none !important;
          }
          .print-badge-wrapper {
            display: flex !important;
            justify-content: center;
            align-items: center;
            width: 100vw;
            height: 100vh;
            position: fixed;
            top: 0;
            left: 0;
            background: white;
            z-index: 99999;
          }
          .print-badge {
            width: 90mm;
            height: 130mm;
            border: 1px solid #ccc;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 8mm;
            box-sizing: border-box;
            background: white;
          }
          .print-badge-logo {
            width: 20mm;
            height: 20mm;
            object-fit: contain;
            margin-bottom: 3mm;
          }
          .print-badge-title {
            font-size: 16pt;
            font-weight: 700;
            margin-bottom: 2mm;
          }
          .print-badge-comp {
            font-size: 9pt;
            color: #555;
            margin-bottom: 4mm;
            text-align: center;
          }
          .print-badge-name {
            font-size: 12pt;
            font-weight: 700;
            margin-bottom: 2mm;
            text-align: center;
          }
          .print-badge-school {
            font-size: 9pt;
            color: #555;
            margin-bottom: 4mm;
            text-align: center;
          }
          .print-badge-qr {
            margin-bottom: 3mm;
          }
          .print-badge-hint {
            font-size: 7pt;
            color: #888;
          }
        }
      `}</style>
    </Layout>
  );
};

export default DashboardPage;
