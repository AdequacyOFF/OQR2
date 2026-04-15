import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api/client';
import type { ResultEntry } from '../../types';
import Spinner from '../../components/common/Spinner';

const ResultsPage: React.FC = () => {
  const { competitionId } = useParams<{ competitionId: string }>();
  const [results, setResults] = useState<ResultEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadResults = async () => {
      try {
        const { data } = await api.get<ResultEntry[]>(`results/${competitionId}`);
        setResults(data);
      } catch {
        setError('Не удалось загрузить результаты.');
      } finally {
        setLoading(false);
      }
    };

    loadResults();
  }, [competitionId]);

  if (loading) {
    return (
      <div className="container">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="container">
      <h1 className="mb-24 text-center">Результаты олимпиады</h1>

      {error && <div className="alert alert-error mb-16">{error}</div>}

      {results.length === 0 ? (
        <p className="text-center text-muted">Результаты пока недоступны.</p>
      ) : (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Место</th>
                <th>ФИО</th>
                <th>Учебное заведение</th>
                <th>Класс</th>
                <th>Балл</th>
                <th>Макс. балл</th>
              </tr>
            </thead>
            <tbody>
              {results.map((entry, index) => (
                <tr key={index}>
                  <td>
                    <strong>{entry.rank}</strong>
                  </td>
                  <td>{entry.participant_name}</td>
                  <td>{entry.school}</td>
                  <td>{entry.grade}</td>
                  <td>
                    <strong>{entry.score}</strong>
                  </td>
                  <td>{entry.max_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ResultsPage;
