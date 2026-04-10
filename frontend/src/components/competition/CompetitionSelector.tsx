import React, { useEffect, useState } from 'react';
import api from '../../api/client';
import useCompetitionStore from '../../store/competitionStore';

interface CompetitionOption {
  id: string;
  name: string;
}

interface CompetitionListResponse {
  competitions: CompetitionOption[];
  total: number;
}

const CompetitionSelector: React.FC = () => {
  const { selectedCompetitionId, setSelectedCompetition, loadFromStorage } = useCompetitionStore();
  const [competitions, setCompetitions] = useState<CompetitionOption[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadFromStorage();
    api
      .get<CompetitionListResponse>('competitions/my')
      .then(({ data }) => {
        setCompetitions(data.competitions);
        // Auto-select if only one competition available
        if (data.competitions.length === 1 && !selectedCompetitionId) {
          setSelectedCompetition(data.competitions[0].id, data.competitions[0].name);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;
  if (competitions.length === 0) return null;

  return (
    <div className="competition-selector" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <label htmlFor="competition-select" style={{ fontSize: 13, color: 'var(--color-muted, #888)', whiteSpace: 'nowrap' }}>
        Олимпиада:
      </label>
      <select
        id="competition-select"
        value={selectedCompetitionId ?? ''}
        onChange={(e) => {
          const comp = competitions.find((c) => c.id === e.target.value);
          if (comp) setSelectedCompetition(comp.id, comp.name);
        }}
        style={{
          padding: '4px 8px',
          borderRadius: 6,
          border: '1px solid #d1d5db',
          fontSize: 13,
          maxWidth: 240,
        }}
      >
        {!selectedCompetitionId && (
          <option value="" disabled>
            — Выберите олимпиаду —
          </option>
        )}
        {competitions.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
};

export default CompetitionSelector;
