import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../../api/client';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';
import Spinner from '../../components/common/Spinner';

interface StaffItem {
  user_id: string;
  email: string;
  role: string;
  assigned_at: string;
}

interface StaffList {
  items: StaffItem[];
  total: number;
}

interface UserOption {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface UserListResponse {
  items: UserOption[];
  total: number;
}

const ROLE_LABELS: Record<string, string> = {
  admitter: 'Допуск',
  scanner: 'Сканер',
  invigilator: 'Инвигилатор',
};

const CompetitionStaffPage: React.FC = () => {
  const { id: competitionId } = useParams<{ id: string }>();
  const [staff, setStaff] = useState<StaffItem[]>([]);
  const [allUsers, setAllUsers] = useState<UserOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadStaff = async () => {
    try {
      const { data } = await api.get<StaffList>(`admin/competitions/${competitionId}/staff`);
      setStaff(data.items);
    } catch {
      setError('Не удалось загрузить список сотрудников');
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await loadStaff();
      try {
        const { data } = await api.get<UserListResponse>('admin/users', {
          params: { limit: 500 },
        });
        // Show only staff roles (not admin, not participant)
        setAllUsers(
          data.items.filter((u) =>
            ['admitter', 'scanner', 'invigilator'].includes(u.role) && u.is_active
          )
        );
      } catch {
        // Non-critical
      }
      setLoading(false);
    };
    load();
  }, [competitionId]);

  const handleAssign = async () => {
    if (!selectedUserId) return;
    setAssigning(true);
    setError(null);
    setSuccess(null);
    try {
      await api.post(`admin/competitions/${competitionId}/staff`, { user_id: selectedUserId });
      setSuccess('Пользователь назначен');
      setSelectedUserId('');
      await loadStaff();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Ошибка назначения');
    } finally {
      setAssigning(false);
    }
  };

  const handleRevoke = async (userId: string) => {
    if (!confirm('Удалить доступ этого пользователя?')) return;
    try {
      await api.delete(`admin/competitions/${competitionId}/staff/${userId}`);
      setStaff((prev) => prev.filter((s) => s.user_id !== userId));
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Ошибка удаления');
    }
  };

  // Users not yet assigned
  const assignedIds = new Set(staff.map((s) => s.user_id));
  const availableUsers = allUsers.filter((u) => !assignedIds.has(u.id));

  if (loading) return <Layout><Spinner /></Layout>;

  return (
    <Layout>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <div style={{ marginBottom: 16 }}>
          <Link to="/admin/competitions">← Назад к олимпиадам</Link>
        </div>
        <h2>Сотрудники олимпиады</h2>

        {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}
        {success && <div className="alert alert-success" style={{ marginBottom: 12 }}>{success}</div>}

        {/* Assign form */}
        <div className="card" style={{ padding: 16, marginBottom: 24 }}>
          <h3 style={{ marginTop: 0 }}>Добавить сотрудника</h3>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
                Выберите пользователя
              </label>
              <select
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db' }}
              >
                <option value="">— Выберите —</option>
                {availableUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.email} ({ROLE_LABELS[u.role] ?? u.role})
                  </option>
                ))}
              </select>
            </div>
            <Button
              onClick={handleAssign}
              loading={assigning}
              disabled={!selectedUserId || assigning}
            >
              Назначить
            </Button>
          </div>
          {availableUsers.length === 0 && (
            <p style={{ fontSize: 13, color: '#888', marginTop: 8 }}>
              Все сотрудники уже имеют доступ, или нет пользователей с нужными ролями.
            </p>
          )}
        </div>

        {/* Staff table */}
        <div className="card" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Текущие сотрудники ({staff.length})</h3>
          {staff.length === 0 ? (
            <p style={{ color: '#888' }}>Нет назначенных сотрудников</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <th style={{ textAlign: 'left', padding: '8px 4px', fontSize: 13 }}>Email</th>
                  <th style={{ textAlign: 'left', padding: '8px 4px', fontSize: 13 }}>Роль</th>
                  <th style={{ textAlign: 'left', padding: '8px 4px', fontSize: 13 }}>Назначен</th>
                  <th style={{ width: 80 }}></th>
                </tr>
              </thead>
              <tbody>
                {staff.map((s) => (
                  <tr key={s.user_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '8px 4px', fontSize: 14 }}>{s.email}</td>
                    <td style={{ padding: '8px 4px', fontSize: 14 }}>
                      {ROLE_LABELS[s.role] ?? s.role}
                    </td>
                    <td style={{ padding: '8px 4px', fontSize: 13, color: '#888' }}>
                      {new Date(s.assigned_at).toLocaleDateString('ru-RU')}
                    </td>
                    <td style={{ padding: '8px 4px' }}>
                      <Button
                        variant="danger"
                        onClick={() => handleRevoke(s.user_id)}
                        style={{ fontSize: 12, padding: '4px 10px' }}
                      >
                        Убрать
                      </Button>
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

export default CompetitionStaffPage;
