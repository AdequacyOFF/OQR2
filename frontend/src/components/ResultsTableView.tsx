import React, { useState, useMemo } from 'react';
import type {
  ScoringProgressResponse,
  ScoringProgressItem,
  TourConfig,
} from '../types';

// ── Utilities ────────────────────────────────────────────────────────────────

function toRoman(n: number): string {
  const vals = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1];
  const syms = ['M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I'];
  let r = '';
  for (let i = 0; i < vals.length; i++) {
    while (n >= vals[i]) { r += syms[i]; n -= vals[i]; }
  }
  return r;
}

/** "hh.mm.ss" → total seconds, or null */
function parseHms(s: string | null | undefined): number | null {
  if (!s) return null;
  const parts = s.split('.');
  if (parts.length !== 3) return null;
  const [h, m, sec] = parts.map(Number);
  if ([h, m, sec].some(isNaN)) return null;
  return h * 3600 + m * 60 + sec;
}

/** total seconds → "H:mm:ss" display string */
function fmtSec(secs: number | null): string {
  if (secs === null) return '—';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ── Styles ───────────────────────────────────────────────────────────────────

const TH: React.CSSProperties = {
  background: '#dbeafe',
  border: '1px solid #bfdbfe',
  padding: '5px 8px',
  fontSize: 12,
  fontWeight: 600,
  textAlign: 'center',
  whiteSpace: 'nowrap',
};
const TOUR_TH: React.CSSProperties = {
  ...TH,
  background: '#bdd7ee',
  border: '1px solid #93c5fd',
};
const TEAM_TOUR_TH: React.CSSProperties = {
  ...TH,
  background: '#c6efce',
  border: '1px solid #92c47e',
};
const TD: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  padding: '4px 8px',
  fontSize: 12,
  textAlign: 'center',
  whiteSpace: 'nowrap',
};
const TD_L: React.CSSProperties = { ...TD, textAlign: 'left', minWidth: 140 };
const TD_RANK: React.CSSProperties = { ...TD, background: '#f1f5f9', fontWeight: 600 };
const TD_FINAL: React.CSSProperties = {
  ...TD,
  background: '#fef9c3',
  fontWeight: 700,
  fontSize: 13,
};

// ── Personal standings ────────────────────────────────────────────────────────

interface PersonalRow {
  name: string;
  school: string;
  tourTotals: Record<number, number | null>;
  tourTimes: Record<number, number | null>;
  tourRanks: Record<number, number>;
  rankSum: number;
  timeSum: number | null;
  scoreSum: number | null;
  finalRank: number;
}

function computePersonalStandings(
  items: ScoringProgressItem[],
  individualTours: TourConfig[],
): PersonalRow[] {
  const rows: PersonalRow[] = items.map((item) => {
    const tourTotals: Record<number, number | null> = {};
    const tourTimes: Record<number, number | null> = {};
    for (const tc of individualTours) {
      const t = item.tours.find((t) => t.tour_number === tc.tour_number);
      tourTotals[tc.tour_number] = t?.tour_total ?? null;
      tourTimes[tc.tour_number] = parseHms(t?.tour_time);
    }
    return {
      name: item.participant_name,
      school: item.participant_school,
      tourTotals,
      tourTimes,
      tourRanks: {},
      rankSum: 0,
      timeSum: null,
      scoreSum: null,
      finalRank: 0,
    };
  });

  // Per-tour ranks (higher score = better; equal score: lower time = better)
  for (const tc of individualTours) {
    for (const row of rows) {
      const myTotal = row.tourTotals[tc.tour_number] ?? 0;
      const myTime = row.tourTimes[tc.tour_number] ?? Infinity;
      let rank = 1;
      for (const other of rows) {
        if (other === row) continue;
        const oTotal = other.tourTotals[tc.tour_number] ?? 0;
        const oTime = other.tourTimes[tc.tour_number] ?? Infinity;
        if (oTotal > myTotal) rank++;
        else if (oTotal === myTotal && oTime < myTime) rank++;
      }
      row.tourRanks[tc.tour_number] = rank;
    }
  }

  // Aggregates
  for (const row of rows) {
    const totals = individualTours
      .map((tc) => row.tourTotals[tc.tour_number])
      .filter((v): v is number => v !== null);
    const times = individualTours
      .map((tc) => row.tourTimes[tc.tour_number])
      .filter((v): v is number => v !== null);
    row.rankSum = individualTours.reduce((s, tc) => s + (row.tourRanks[tc.tour_number] ?? 0), 0);
    row.scoreSum = totals.length ? totals.reduce((a, b) => a + b, 0) : null;
    row.timeSum = times.length ? times.reduce((a, b) => a + b, 0) : null;
  }

  // Final rank: rankSum asc → timeSum asc → scoreSum desc
  for (const row of rows) {
    const myRS = row.rankSum;
    const myTS = row.timeSum ?? Infinity;
    const mySS = row.scoreSum ?? 0;
    let rank = 1;
    for (const other of rows) {
      if (other === row) continue;
      const oRS = other.rankSum;
      const oTS = other.timeSum ?? Infinity;
      const oSS = other.scoreSum ?? 0;
      if (oRS < myRS) rank++;
      else if (oRS === myRS && oTS < myTS) rank++;
      else if (oRS === myRS && oTS === myTS && oSS > mySS) rank++;
    }
    row.finalRank = rank;
  }

  return [...rows].sort((a, b) => a.finalRank - b.finalRank);
}

function PersonalTable({ rows, tours }: { rows: PersonalRow[]; tours: TourConfig[] }) {
  if (rows.length === 0) return <p style={{ color: '#9ca3af', padding: 16 }}>Нет данных</p>;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
        <thead>
          <tr>
            <th rowSpan={2} style={TH}>№</th>
            <th rowSpan={2} style={{ ...TH, minWidth: 180 }}>Команда (ВУЗ)</th>
            <th rowSpan={2} style={{ ...TH, minWidth: 160 }}>ФИО</th>
            {tours.map((tc) => (
              <th key={tc.tour_number} colSpan={3} style={TOUR_TH}>
                Тур {toRoman(tc.tour_number)}
              </th>
            ))}
            <th rowSpan={2} style={TH}>Σ мест</th>
            <th rowSpan={2} style={TH}>Σ время</th>
            <th rowSpan={2} style={TH}>Σ баллов</th>
            <th rowSpan={2} style={{ ...TH, background: '#fef9c3', border: '1px solid #fde047' }}>
              Место
            </th>
          </tr>
          <tr>
            {tours.map((tc) => (
              <React.Fragment key={tc.tour_number}>
                <th style={TH}>Баллы</th>
                <th style={TH}>Время</th>
                <th style={TH}>Место</th>
              </React.Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx} style={{ background: idx % 2 === 0 ? '#fff' : '#f9fafb' }}>
              <td style={TD}>{idx + 1}</td>
              <td style={TD_L}>{row.school}</td>
              <td style={TD_L}>{row.name}</td>
              {tours.map((tc) => (
                <React.Fragment key={tc.tour_number}>
                  <td style={TD}>{row.tourTotals[tc.tour_number] ?? '—'}</td>
                  <td style={TD}>{fmtSec(row.tourTimes[tc.tour_number])}</td>
                  <td style={TD_RANK}>{row.tourRanks[tc.tour_number] ?? '—'}</td>
                </React.Fragment>
              ))}
              <td style={TD}>{row.rankSum}</td>
              <td style={TD}>{fmtSec(row.timeSum)}</td>
              <td style={TD}>{row.scoreSum ?? '—'}</td>
              <td style={TD_FINAL}>{row.finalRank}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Team standings ────────────────────────────────────────────────────────────

interface TeamRow {
  institution: string;
  tourTotals: Record<number, number | null>;
  tourBonuses: Record<number, number | null>;
  tourTimes: Record<number, number | null>;
  tourRanks: Record<number, number>;
  rankSum: number;
  timeSum: number | null;
  finalRank: number;
}

function computeTeamStandings(
  items: ScoringProgressItem[],
  allTours: TourConfig[],
  captainTours: TourConfig[],
  teamTours: TourConfig[],
): TeamRow[] {
  // Preserve institution order from items
  const instOrder: string[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    const inst = item.participant_school || '';
    if (!seen.has(inst)) { seen.add(inst); instOrder.push(inst); }
  }

  // captain_bonus[inst][tourN]: mirrors Python export logic exactly
  // (1) for individual_captains tours: captain's regular tour_total
  // (2) + captains_task_by_tour scores (cap_N keys)
  const captainBonus: Record<string, Record<number, number>> = {};
  for (const item of items) {
    if (!item.is_captain) continue;
    const inst = item.participant_school || '';
    for (const tc of captainTours) {
      const t = item.tours.find((t) => t.tour_number === tc.tour_number);
      if (t?.tour_total != null) {
        if (!captainBonus[inst]) captainBonus[inst] = {};
        captainBonus[inst][tc.tour_number] =
          (captainBonus[inst][tc.tour_number] ?? 0) + t.tour_total;
      }
    }
    for (const [tourNStr, capScore] of Object.entries(item.captains_task_by_tour)) {
      const tourN = Number(tourNStr);
      if (!captainBonus[inst]) captainBonus[inst] = {};
      captainBonus[inst][tourN] = (captainBonus[inst][tourN] ?? 0) + capScore;
    }
  }

  // captainTime[inst][tourN] for team tours: captain's per-participant tour_time
  const captainTime: Record<string, Record<number, number | null>> = {};
  for (const item of items) {
    if (!item.is_captain) continue;
    const inst = item.participant_school || '';
    for (const tc of teamTours) {
      const t = item.tours.find((t) => t.tour_number === tc.tour_number);
      if (t?.tour_time) {
        if (!captainTime[inst]) captainTime[inst] = {};
        captainTime[inst][tc.tour_number] = parseHms(t.tour_time);
      }
    }
  }

  // Aggregate per-institution, per-tour: sum of all participants' regular tour_total & times
  const aggScores: Record<string, Record<number, number>> = {};
  const aggTimesInd: Record<string, Record<number, number>> = {};
  for (const item of items) {
    const inst = item.participant_school || '';
    for (const tc of allTours) {
      const t = item.tours.find((t) => t.tour_number === tc.tour_number);
      if (t?.tour_total != null) {
        if (!aggScores[inst]) aggScores[inst] = {};
        aggScores[inst][tc.tour_number] = (aggScores[inst][tc.tour_number] ?? 0) + t.tour_total;
      }
      if (tc.mode !== 'team') {
        const secs = parseHms(t?.tour_time);
        if (secs !== null) {
          if (!aggTimesInd[inst]) aggTimesInd[inst] = {};
          aggTimesInd[inst][tc.tour_number] =
            (aggTimesInd[inst][tc.tour_number] ?? 0) + secs;
        }
      }
    }
  }

  const rows: TeamRow[] = instOrder.map((inst) => {
    const tourTotals: Record<number, number | null> = {};
    const tourBonuses: Record<number, number | null> = {};
    const tourTimes: Record<number, number | null> = {};

    for (const tc of allTours) {
      const base = aggScores[inst]?.[tc.tour_number] ?? null;
      const bonus = captainBonus[inst]?.[tc.tour_number] ?? 0;

      if (tc.mode === 'individual_captains') {
        tourBonuses[tc.tour_number] = bonus || null;
        tourTotals[tc.tour_number] =
          base !== null || bonus ? (base ?? 0) + bonus : null;
        tourTimes[tc.tour_number] = aggTimesInd[inst]?.[tc.tour_number] ?? null;
      } else if (tc.mode === 'individual') {
        tourTotals[tc.tour_number] = base;
        tourTimes[tc.tour_number] = aggTimesInd[inst]?.[tc.tour_number] ?? null;
      } else {
        // team tour
        tourTotals[tc.tour_number] =
          base !== null || bonus ? (base ?? 0) + bonus : null;
        tourTimes[tc.tour_number] = captainTime[inst]?.[tc.tour_number] ?? null;
      }
    }

    return {
      institution: inst,
      tourTotals,
      tourBonuses,
      tourTimes,
      tourRanks: {},
      rankSum: 0,
      timeSum: null,
      finalRank: 0,
    };
  });

  // Per-tour ranks
  for (const tc of allTours) {
    for (const row of rows) {
      const myTotal = row.tourTotals[tc.tour_number] ?? 0;
      const myTime = row.tourTimes[tc.tour_number] ?? Infinity;
      let rank = 1;
      for (const other of rows) {
        if (other === row) continue;
        const oTotal = other.tourTotals[tc.tour_number] ?? 0;
        const oTime = other.tourTimes[tc.tour_number] ?? Infinity;
        if (oTotal > myTotal) rank++;
        else if (oTotal === myTotal && oTime < myTime) rank++;
      }
      row.tourRanks[tc.tour_number] = rank;
    }
  }

  // Aggregates
  for (const row of rows) {
    const times = allTours
      .map((tc) => row.tourTimes[tc.tour_number])
      .filter((v): v is number => v !== null);
    row.rankSum = allTours.reduce((s, tc) => s + (row.tourRanks[tc.tour_number] ?? 0), 0);
    row.timeSum = times.length ? times.reduce((a, b) => a + b, 0) : null;
  }

  // Final rank: rankSum asc → timeSum asc
  for (const row of rows) {
    const myRS = row.rankSum;
    const myTS = row.timeSum ?? Infinity;
    let rank = 1;
    for (const other of rows) {
      if (other === row) continue;
      const oRS = other.rankSum;
      const oTS = other.timeSum ?? Infinity;
      if (oRS < myRS) rank++;
      else if (oRS === myRS && oTS < myTS) rank++;
    }
    row.finalRank = rank;
  }

  return [...rows].sort((a, b) => a.finalRank - b.finalRank);
}

function TeamTable({
  rows,
  allTours,
  individualTours,
  teamTours,
}: {
  rows: TeamRow[];
  allTours: TourConfig[];
  individualTours: TourConfig[];
  teamTours: TourConfig[];
}) {
  if (rows.length === 0) return <p style={{ color: '#9ca3af', padding: 16 }}>Нет данных</p>;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
        <thead>
          <tr>
            <th rowSpan={2} style={TH}>№</th>
            <th rowSpan={2} style={{ ...TH, minWidth: 200 }}>Команда (ВУЗ)</th>
            {individualTours.map((tc) => (
              <th
                key={tc.tour_number}
                colSpan={tc.mode === 'individual_captains' ? 4 : 3}
                style={TOUR_TH}
              >
                Тур {toRoman(tc.tour_number)}
              </th>
            ))}
            {teamTours.map((tc) => (
              <th key={tc.tour_number} colSpan={3} style={TEAM_TOUR_TH}>
                Тур {toRoman(tc.tour_number)} (командный)
              </th>
            ))}
            <th rowSpan={2} style={TH}>Σ мест</th>
            <th rowSpan={2} style={TH}>Σ время</th>
            <th rowSpan={2} style={{ ...TH, background: '#fef9c3', border: '1px solid #fde047' }}>
              Место
            </th>
          </tr>
          <tr>
            {individualTours.map((tc) => (
              <React.Fragment key={tc.tour_number}>
                {tc.mode === 'individual_captains' && (
                  <th style={TH}>Доп. задание (капитан)</th>
                )}
                <th style={TH}>Баллы</th>
                <th style={TH}>Время</th>
                <th style={TH}>Место</th>
              </React.Fragment>
            ))}
            {teamTours.map((tc) => (
              <React.Fragment key={tc.tour_number}>
                <th style={TEAM_TOUR_TH}>Баллы</th>
                <th style={TEAM_TOUR_TH}>Время</th>
                <th style={TEAM_TOUR_TH}>Место</th>
              </React.Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx} style={{ background: idx % 2 === 0 ? '#fff' : '#f9fafb' }}>
              <td style={TD}>{idx + 1}</td>
              <td style={TD_L}>{row.institution}</td>
              {individualTours.map((tc) => (
                <React.Fragment key={tc.tour_number}>
                  {tc.mode === 'individual_captains' && (
                    <td style={TD}>{row.tourBonuses[tc.tour_number] ?? '—'}</td>
                  )}
                  <td style={TD}>{row.tourTotals[tc.tour_number] ?? '—'}</td>
                  <td style={TD}>{fmtSec(row.tourTimes[tc.tour_number])}</td>
                  <td style={TD_RANK}>{row.tourRanks[tc.tour_number] ?? '—'}</td>
                </React.Fragment>
              ))}
              {teamTours.map((tc) => (
                <React.Fragment key={tc.tour_number}>
                  <td style={{ ...TD, background: '#f0fff4' }}>
                    {row.tourTotals[tc.tour_number] ?? '—'}
                  </td>
                  <td style={{ ...TD, background: '#f0fff4' }}>
                    {fmtSec(row.tourTimes[tc.tour_number])}
                  </td>
                  <td style={{ ...TD_RANK, background: '#dcfce7' }}>
                    {row.tourRanks[tc.tour_number] ?? '—'}
                  </td>
                </React.Fragment>
              ))}
              <td style={TD}>{row.rankSum}</td>
              <td style={TD}>{fmtSec(row.timeSum)}</td>
              <td style={TD_FINAL}>{row.finalRank}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Simple standings (non-special competitions) ───────────────────────────────

function SimpleTable({ items }: { items: ScoringProgressItem[] }) {
  const sorted = useMemo(() => {
    const rows = items.map((item) => ({
      name: item.participant_name,
      school: item.participant_school,
      score: item.score_total ?? 0,
    }));
    rows.sort((a, b) => b.score - a.score);
    // Compute dense rank: 1 + count of rows with strictly higher score
    return rows.map((row) => ({
      ...row,
      rank: 1 + rows.filter((r) => r.score > row.score).length,
    }));
  }, [items]);

  if (sorted.length === 0) return <p style={{ color: '#9ca3af', padding: 16 }}>Нет данных</p>;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
        <thead>
          <tr>
            <th style={TH}>№</th>
            <th style={{ ...TH, minWidth: 180 }}>Команда (ВУЗ)</th>
            <th style={{ ...TH, minWidth: 160 }}>ФИО</th>
            <th style={TH}>Сумма баллов</th>
            <th style={{ ...TH, background: '#fef9c3', border: '1px solid #fde047' }}>Место</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, idx) => (
            <tr key={idx} style={{ background: idx % 2 === 0 ? '#fff' : '#f9fafb' }}>
              <td style={TD}>{idx + 1}</td>
              <td style={TD_L}>{row.school}</td>
              <td style={TD_L}>{row.name}</td>
              <td style={TD}>{row.score ?? '—'}</td>
              <td style={TD_FINAL}>{row.rank}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

interface ResultsTableViewProps {
  data: ScoringProgressResponse;
}

const ResultsTableView: React.FC<ResultsTableViewProps> = ({ data }) => {
  const [activeTab, setActiveTab] = useState<'personal' | 'team'>('personal');

  const individualTours = useMemo(
    () => data.tour_configs.filter((tc) => tc.mode !== 'team'),
    [data.tour_configs],
  );
  const captainTours = useMemo(
    () => data.tour_configs.filter((tc) => tc.mode === 'individual_captains'),
    [data.tour_configs],
  );
  const teamTours = useMemo(
    () => data.tour_configs.filter((tc) => tc.mode === 'team'),
    [data.tour_configs],
  );

  const personalRows = useMemo(
    () => computePersonalStandings(data.items, individualTours),
    [data.items, individualTours],
  );
  const teamRows = useMemo(
    () => computeTeamStandings(data.items, data.tour_configs, captainTours, teamTours),
    [data.items, data.tour_configs, captainTours, teamTours],
  );

  const isSpecial = data.is_special && data.tour_configs.length > 0;
  const hasTeamTours = teamTours.length > 0;

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: '8px 20px',
    border: 'none',
    borderBottom: active ? '3px solid #2563eb' : '3px solid transparent',
    background: 'none',
    cursor: 'pointer',
    fontWeight: active ? 700 : 400,
    color: active ? '#2563eb' : '#6b7280',
    fontSize: 14,
  });

  if (!isSpecial) {
    return <SimpleTable items={data.items} />;
  }

  return (
    <div>
      {hasTeamTours && (
        <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb', marginBottom: 16 }}>
          <button style={tabStyle(activeTab === 'personal')} onClick={() => setActiveTab('personal')}>
            Личный зачет
          </button>
          <button style={tabStyle(activeTab === 'team')} onClick={() => setActiveTab('team')}>
            Командный зачет
          </button>
        </div>
      )}

      {(!hasTeamTours || activeTab === 'personal') && (
        <PersonalTable rows={personalRows} tours={individualTours} />
      )}
      {hasTeamTours && activeTab === 'team' && (
        <TeamTable
          rows={teamRows}
          allTours={data.tour_configs}
          individualTours={individualTours}
          teamTours={teamTours}
        />
      )}
    </div>
  );
};

export default ResultsTableView;
