import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import Spinner from '../../components/common/Spinner';
import api from '../../api/client';

interface Statistics {
  total_competitions: number;
  total_users: number;
  total_scans: number;
  total_registrations: number;
  total_participants: number;
}

const AdminDashboardPage: React.FC = () => {
  const [stats, setStats] = useState<Statistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadStatistics();
  }, []);

  const loadStatistics = async () => {
    try {
      const { data } = await api.get<Statistics>('admin/statistics');
      setStats(data);
    } catch (err) {
      setError('Не удалось загрузить статистику');
      console.error('Failed to load statistics:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <h1 className="mb-24">Панель администратора</h1>
      <div className="grid grid-3">
        <Link to="/admin/competitions" style={{ textDecoration: 'none' }}>
          <div className="card text-center">
            <h2>Олимпиады</h2>
            <p className="text-muted mt-16">Управление олимпиадами, статусами и настройками</p>
          </div>
        </Link>
        <Link to="/admin/users" style={{ textDecoration: 'none' }}>
          <div className="card text-center">
            <h2>Пользователи</h2>
            <p className="text-muted mt-16">Управление аккаунтами и ролями</p>
          </div>
        </Link>
        <Link to="/admin/audit-log" style={{ textDecoration: 'none' }}>
          <div className="card text-center">
            <h2>Журнал действий</h2>
            <p className="text-muted mt-16">Просмотр активности и изменений в системе</p>
          </div>
        </Link>
        <Link to="/admin/institutions" style={{ textDecoration: 'none' }}>
          <div className="card text-center">
            <h2>Учреждения</h2>
            <p className="text-muted mt-16">Справочник учебных учреждений</p>
          </div>
        </Link>
        <Link to="/admin/rooms" style={{ textDecoration: 'none' }}>
          <div className="card text-center">
            <h2>Аудитории</h2>
            <p className="text-muted mt-16">Управление аудиториями и рассадкой</p>
          </div>
        </Link>
        <Link to="/admin/staff-badges" style={{ textDecoration: 'none' }}>
          <div className="card text-center">
            <h2>Бейджи руководителей</h2>
            <p className="text-muted mt-16">Генерация бейджей для представителей</p>
          </div>
        </Link>
      </div>

      <div className="card mt-16">
        <h2 className="mb-16">Краткая статистика</h2>
        {error && <div className="alert alert-error mb-16">{error}</div>}
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px' }}>
            <Spinner />
          </div>
        ) : (
          <div className="grid grid-3">
            <div className="text-center">
              <p className="text-muted">Всего олимпиад</p>
              <p style={{ fontSize: 28, fontWeight: 700 }}>{stats?.total_competitions ?? 0}</p>
            </div>
            <div className="text-center">
              <p className="text-muted">Всего пользователей</p>
              <p style={{ fontSize: 28, fontWeight: 700 }}>{stats?.total_users ?? 0}</p>
            </div>
            <div className="text-center">
              <p className="text-muted">Всего сканов</p>
              <p style={{ fontSize: 28, fontWeight: 700 }}>{stats?.total_scans ?? 0}</p>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
};

export default AdminDashboardPage;
