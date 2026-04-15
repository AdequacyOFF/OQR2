import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toRoman } from '../../utils/roman';
import { useNavigate } from 'react-router-dom';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import api from '../../api/client';
import type { Competition, Room, AdminRegistrationItem, ReplaceParticipantResponse } from '../../types';
import Layout from '../../components/layout/Layout';
import Button from '../../components/common/Button';
import Input from '../../components/common/Input';
import Modal from '../../components/common/Modal';
import Spinner from '../../components/common/Spinner';

const competitionSchema = z.object({
  name: z.string().min(1, 'Название обязательно'),
  date: z.string().min(1, 'Дата обязательна'),
  registration_start: z.string().min(1, 'Обязательное поле'),
  registration_end: z.string().min(1, 'Обязательное поле'),
  variants_count: z.coerce.number().min(1, 'Минимум 1 вариант'),
  max_score: z.coerce.number().min(1, 'Должно быть положительным'),
  is_special: z.boolean().default(false),
  special_tours_count: z.coerce.number().min(1, 'Минимум 1 тур').optional(),
});

type CompetitionForm = z.infer<typeof competitionSchema>;
type SpecialTemplateKind = 'answer_blank' | 'a3_cover' | 'badge';
type RoomLayoutState = Record<string, { seatsPerTable: number; teamSeatsPerTable: number; seatMatrixColumns: number }>;
type TeamTableMergeState = Record<string, string>;

const Tooltip: React.FC<{ text: string; children: React.ReactNode }> = ({ text, children }) => {
  const [show, setShow] = React.useState(false);
  return (
    <span
      style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <span
          style={{
            position: 'absolute',
            bottom: 'calc(100% + 4px)',
            left: '50%',
            transform: 'translateX(-50%)',
            background: '#1f2937',
            color: '#fff',
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 11,
            whiteSpace: 'nowrap',
            zIndex: 1000,
            pointerEvents: 'none',
            boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
          }}
        >
          {text}
        </span>
      )}
    </span>
  );
};

const CompetitionsAdminPage: React.FC = () => {
  const navigate = useNavigate();
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Room management state
  const [pendingRooms, setPendingRooms] = useState<{ name: string; capacity: number }[]>([]);
  const [existingRooms, setExistingRooms] = useState<Room[]>([]);
  const [newRoomName, setNewRoomName] = useState('');
  const [newRoomCapacity, setNewRoomCapacity] = useState(30);
  const [roomsLoading, setRoomsLoading] = useState(false);

  // Registrations modal state
  const [regModalOpen, setRegModalOpen] = useState(false);
  const [regCompetition, setRegCompetition] = useState<Competition | null>(null);
  const [regItems, setRegItems] = useState<AdminRegistrationItem[]>([]);
  const [regLoading, setRegLoading] = useState(false);
  const [participants, setParticipants] = useState<{
    id: string;
    user_id: string;
    full_name: string;
    school: string;
    institution_location?: string | null;
    is_captain?: boolean;
  }[]>([]);
  const [participantSearch, setParticipantSearch] = useState('');
  const [registering, setRegistering] = useState(false);
  const [specialTourModes, setSpecialTourModes] = useState<string[]>([]);
  const [specialTourTasks, setSpecialTourTasks] = useState<string[]>([]);
  const [specialTourCaptainsTask, setSpecialTourCaptainsTask] = useState<boolean[]>([]);
  const [specialTourCaptainsTasks, setSpecialTourCaptainsTasks] = useState<string[]>([]);
  const [specialCaptainsRoomId, setSpecialCaptainsRoomId] = useState('');
  const [specialRoomLayouts, setSpecialRoomLayouts] = useState<RoomLayoutState>({});
  const [teamTableMergesTour3, setTeamTableMergesTour3] = useState<TeamTableMergeState>({});
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [admitAndDownloadLoading, setAdmitAndDownloadLoading] = useState(false);
  const [blanksTaskId, setBlanksTaskId] = useState<string | null>(null);
  const [blanksTaskState, setBlanksTaskState] = useState<string | null>(null);
  const [blanksTaskProgress, setBlanksTaskProgress] = useState<{ stage: string; current: number; total: number; participant: string } | null>(null);
  const [badgesDownloading, setBadgesDownloading] = useState(false);
  const [badgeTaskId, setBadgeTaskId] = useState<string | null>(null);
  const [badgeTaskState, setBadgeTaskState] = useState<string | null>(null);
  const [badgeTaskProgress, setBadgeTaskProgress] = useState<{ stage: string; current: number; total: number } | null>(null);
  const badgeTaskPollRef = React.useRef<ReturnType<typeof setInterval> | null>(null);
  const [teamTourForPrint, setTeamTourForPrint] = useState<number | null>(null);
  const [answerTemplateFile, setAnswerTemplateFile] = useState<File | null>(null);
  const [a3TemplateFile, setA3TemplateFile] = useState<File | null>(null);
  const [badgeTemplateFile, setBadgeTemplateFile] = useState<File | null>(null);
  const [badgePhotosZipFile, setBadgePhotosZipFile] = useState<File | null>(null);
  const [badgePhotosUploading, setBadgePhotosUploading] = useState(false);
  const [badgeFontsFile, setBadgeFontsFile] = useState<File | null>(null);
  const [badgeFontsUploading, setBadgeFontsUploading] = useState(false);
  const [templateUploadingKind, setTemplateUploadingKind] = useState<SpecialTemplateKind | null>(null);
  const [templateDownloadingKind, setTemplateDownloadingKind] = useState<SpecialTemplateKind | null>(null);
  const [templateDeletingKind, setTemplateDeletingKind] = useState<SpecialTemplateKind | null>(null);
  const [templateInfo, setTemplateInfo] = useState<Record<string, { filename: string; display_filename: string; modified_at?: string }>>({});

  // Delete / replace participant state
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [deleteConfirmName, setDeleteConfirmName] = useState<string>('');
  const [deletingReg, setDeletingReg] = useState(false);
  const [replaceRegId, setReplaceRegId] = useState<string | null>(null);
  const [replaceSearch, setReplaceSearch] = useState('');
  const [replacing, setReplacing] = useState(false);
  const [replaceResult, setReplaceResult] = useState<ReplaceParticipantResponse | null>(null);
  const [downloadingRegId, setDownloadingRegId] = useState<string | null>(null);
  const [lastAddedRegId, setLastAddedRegId] = useState<string | null>(null);

  // Edit participant fields
  const [editParticipantId, setEditParticipantId] = useState<string | null>(null);
  const [editInstLocation, setEditInstLocation] = useState('');
  const [editInstId, setEditInstId] = useState('');
  const [editInstSearch, setEditInstSearch] = useState('');
  const [instSearchResults, setInstSearchResults] = useState<{id: string; name: string; city?: string}[]>([]);
  const [savingParticipant, setSavingParticipant] = useState(false);

  // Per-participant photo upload
  const [photoUploadRegId, setPhotoUploadRegId] = useState<string | null>(null);
  const [photoUploadParticipantId, setPhotoUploadParticipantId] = useState<string | null>(null);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<CompetitionForm>({
    resolver: zodResolver(competitionSchema),
  });

  const isSpecialCompetition = watch('is_special');
  const specialToursCount = watch('special_tours_count');
  const hasIndividualCaptainsMode = specialTourModes.some((mode) => mode === 'individual_captains');
  const thirdTourIsTeamMode = specialTourModes[2] === 'team';
  const formTeamTourNumbers = specialTourModes
    .map((mode, index) => (mode === 'team' ? index + 1 : null))
    .filter((value): value is number => value !== null);
  const registrationTeamTourNumbers = regCompetition
    ? extractToursFromSettings(regCompetition)
      .filter((tour) => tour.mode === 'team')
      .map((tour) => tour.tourNumber)
    : [];

  useEffect(() => {
    if (!isSpecialCompetition) {
      setSpecialTourModes([]);
      setSpecialTourTasks([]);
      setSpecialTourCaptainsTask([]);
      setSpecialCaptainsRoomId('');
      setSpecialRoomLayouts({});
      setTeamTableMergesTour3({});
      return;
    }
    const count = Number(specialToursCount || 0);
    if (!count || count < 1) {
      setSpecialTourModes([]);
      setSpecialTourTasks([]);
      setSpecialTourCaptainsTask([]);
      return;
    }
    setSpecialTourModes((prev) => {
      const next = Array.from({ length: count }, (_, idx) => prev[idx] || 'individual');
      return next;
    });
    setSpecialTourTasks((prev) => {
      const next = Array.from({ length: count }, (_, idx) => prev[idx] || '1');
      return next;
    });
    setSpecialTourCaptainsTask((prev) => {
      const next = Array.from({ length: count }, (_, idx) => prev[idx] || false);
      return next;
    });
    setSpecialTourCaptainsTasks((prev) => {
      const next = Array.from({ length: count }, (_, idx) => prev[idx] || '');
      return next;
    });
  }, [isSpecialCompetition, specialToursCount]);

  useEffect(() => {
    loadCompetitions();
  }, []);

  const loadCompetitions = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<{ competitions: Competition[]; total: number }>('competitions');
      setCompetitions(data.competitions || []);
    } catch {
      setError('Не удалось загрузить олимпиады.');
    } finally {
      setLoading(false);
    }
  };

  const loadRooms = async (competitionId: string) => {
    setRoomsLoading(true);
    try {
      const { data } = await api.get<{ rooms: Room[] }>(`rooms/${competitionId}`);
      const rooms = data.rooms || [];
      setExistingRooms(rooms);
      setSpecialRoomLayouts((prev) => {
        const next: RoomLayoutState = {};
        rooms.forEach((room) => {
          const current = prev[room.id];
          next[room.id] = {
            seatsPerTable: parsePositiveInt(current?.seatsPerTable, 1),
            teamSeatsPerTable: parsePositiveInt(current?.teamSeatsPerTable, 2),
            seatMatrixColumns: parsePositiveInt(current?.seatMatrixColumns, 3),
          };
        });
        return next;
      });
      setTeamTableMergesTour3((prev) => {
        const next: TeamTableMergeState = {};
        rooms.forEach((room) => {
          next[room.id] = prev[room.id] || '';
        });
        return next;
      });
    } catch {
      setExistingRooms([]);
      setSpecialRoomLayouts({});
      setTeamTableMergesTour3({});
    } finally {
      setRoomsLoading(false);
    }
  };

  const parseTaskNumbersInput = (value: string): number[] => {
    const parsed = value
      .split(',')
      .map((token) => Number(token.trim()))
      .filter((token) => Number.isInteger(token) && token > 0);
    const unique = Array.from(new Set(parsed));
    return unique.length ? unique : [1];
  };

  function parsePositiveInt(value: unknown, fallback: number): number {
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
  }

  function parseTeamTableMergesInput(value: string): number[][] {
    const used = new Set<number>();
    return value
      .split(',')
      .map((group) =>
        group
          .split('+')
          .map((token) => Number(token.trim()))
          .filter((token) => Number.isInteger(token) && token > 0)
      )
      .map((group) => Array.from(new Set(group)))
      .filter((group) => group.length > 1)
      .map((group) => {
        const filtered = group.filter((tableNumber) => {
          if (used.has(tableNumber)) return false;
          used.add(tableNumber);
          return true;
        });
        return filtered;
      })
      .filter((group) => group.length > 1);
  }

  function formatTeamTableMerges(groups: unknown): string {
    if (!Array.isArray(groups)) return '';
    const normalized = groups
      .map((group) =>
        Array.isArray(group)
          ? group
            .map((n) => Number(n))
            .filter((n) => Number.isInteger(n) && n > 0)
          : []
      )
      .filter((group) => group.length > 1);
    return normalized.map((group) => group.join('+')).join(', ');
  }

  function extractToursFromSettings(comp: Competition): Array<{ tourNumber: number; mode: string; taskNumbers: number[]; captainsTask: boolean }> {
    const settings = comp.special_settings;
    if (!settings || typeof settings !== 'object') return [];

    const rawTours = (settings as { tours?: unknown }).tours;
    if (!Array.isArray(rawTours)) return [];

    return rawTours
      .map((item, index) => {
        if (!item || typeof item !== 'object') return null;
        const rawMode = (item as { mode?: unknown }).mode;
        const rawTaskNumbers = (item as { task_numbers?: unknown; tasks?: unknown }).task_numbers
          ?? (item as { task_numbers?: unknown; tasks?: unknown }).tasks;
        const mode = typeof rawMode === 'string' ? rawMode : 'individual';
        const taskNumbers = Array.isArray(rawTaskNumbers)
          ? rawTaskNumbers
            .map((n) => Number(n))
            .filter((n) => Number.isInteger(n) && n > 0)
          : [1];
        const rawTourNumber = (item as { tour_number?: unknown }).tour_number;
        const captainsTask = Boolean((item as { captains_task?: unknown }).captains_task);
        const rawCaptainsTaskNumbers = (item as { captains_task_numbers?: unknown }).captains_task_numbers;
        const captainsTaskNumbers = Array.isArray(rawCaptainsTaskNumbers)
          ? rawCaptainsTaskNumbers.map((n) => Number(n)).filter((n) => Number.isInteger(n) && n > 0)
          : [];
        return {
          tourNumber: parsePositiveInt(rawTourNumber, index + 1),
          mode,
          taskNumbers: taskNumbers.length ? Array.from(new Set(taskNumbers)) : [1],
          captainsTask,
          captainsTaskNumbers,
        };
      })
      .filter((item): item is { tourNumber: number; mode: string; taskNumbers: number[]; captainsTask: boolean; captainsTaskNumbers: number[] } => item !== null);
  }

  function extractRoomLayoutsFromSettings(comp: Competition): RoomLayoutState {
    const settings = comp.special_settings;
    if (!settings || typeof settings !== 'object') return {};

    const defaultSeatMatrixColumns = parsePositiveInt(
      (settings as { seat_matrix_columns?: unknown }).seat_matrix_columns,
      3
    );
    const rawRoomLayouts = (settings as { room_layouts?: unknown }).room_layouts;
    const rawTeamRoomLayouts = (settings as { team_room_layouts?: unknown }).team_room_layouts;

    const parsed: RoomLayoutState = {};
    if (rawRoomLayouts && typeof rawRoomLayouts === 'object') {
      Object.entries(rawRoomLayouts as Record<string, unknown>).forEach(([roomId, payload]) => {
        if (!payload || typeof payload !== 'object') return;
        const seatsPerTable = parsePositiveInt((payload as { seats_per_table?: unknown }).seats_per_table, 1);
        const seatMatrixColumns = parsePositiveInt(
          (payload as { seat_matrix_columns?: unknown }).seat_matrix_columns,
          defaultSeatMatrixColumns
        );
        parsed[roomId] = {
          seatsPerTable,
          teamSeatsPerTable: 2,
          seatMatrixColumns,
        };
      });
    }

    if (rawTeamRoomLayouts && typeof rawTeamRoomLayouts === 'object') {
      Object.entries(rawTeamRoomLayouts as Record<string, unknown>).forEach(([roomId, payload]) => {
        if (!payload || typeof payload !== 'object') return;
        const teamSeatsPerTable = parsePositiveInt((payload as { seats_per_table?: unknown }).seats_per_table, 2);
        parsed[roomId] = {
          seatsPerTable: parsed[roomId]?.seatsPerTable ?? 1,
          teamSeatsPerTable,
          seatMatrixColumns: parsed[roomId]?.seatMatrixColumns ?? defaultSeatMatrixColumns,
        };
      });
    }

    return parsed;
  }

  function extractTour3TableMergesFromSettings(comp: Competition): TeamTableMergeState {
    const settings = comp.special_settings;
    if (!settings || typeof settings !== 'object') return {};
    const raw = (settings as { team_table_merges?: unknown }).team_table_merges;
    if (!raw || typeof raw !== 'object') return {};

    const byTour = (raw as Record<string, unknown>)['3'];
    if (!byTour || typeof byTour !== 'object') return {};

    const result: TeamTableMergeState = {};
    Object.entries(byTour as Record<string, unknown>).forEach(([roomId, groups]) => {
      result[roomId] = formatTeamTableMerges(groups);
    });
    return result;
  }

  const openCreate = () => {
    setEditingId(null);
    reset({
      name: '',
      date: '',
      registration_start: '',
      registration_end: '',
      variants_count: 4,
      max_score: 100,
      is_special: false,
      special_tours_count: undefined,
    });
    setPendingRooms([]);
    setExistingRooms([]);
    setNewRoomName('');
    setNewRoomCapacity(30);
    setSpecialTourModes([]);
    setSpecialTourTasks([]);
    setSpecialTourCaptainsTask([]);
    setSpecialCaptainsRoomId('');
    setSpecialRoomLayouts({});
    setTeamTableMergesTour3({});
    setTeamTourForPrint(null);
    setImportFile(null);
    setAnswerTemplateFile(null);
    setA3TemplateFile(null);
    setModalOpen(true);
  };

  const openEdit = (comp: Competition) => {
    const toursFromSettings = extractToursFromSettings(comp);
    const toursCountFromSettings = toursFromSettings.length > 0 ? toursFromSettings.length : null;
    const effectiveToursCount = comp.special_tours_count ?? toursCountFromSettings ?? undefined;
    const fallbackModes = comp.special_tour_modes || [];
    const effectiveTourCount = Number(effectiveToursCount || fallbackModes.length || 0);
    const settings = (comp.special_settings && typeof comp.special_settings === 'object')
      ? (comp.special_settings as Record<string, unknown>)
      : {};
    const rawCaptainsRoomId = settings.captains_room_id;
    const parsedRoomLayouts = extractRoomLayoutsFromSettings(comp);
    const parsedTour3TableMerges = extractTour3TableMergesFromSettings(comp);

    setEditingId(comp.id);
    setValue('name', comp.name);
    setValue('date', comp.date.slice(0, 10));
    setValue('registration_start', comp.registration_start.slice(0, 16));
    setValue('registration_end', comp.registration_end.slice(0, 16));
    setValue('variants_count', comp.variants_count);
    setValue('max_score', comp.max_score);
    setValue('is_special', comp.is_special);
    setValue('special_tours_count', effectiveToursCount);
    setSpecialTourModes(
      Array.from({ length: effectiveTourCount }, (_, index) => {
        if (toursFromSettings[index]?.mode) return toursFromSettings[index].mode;
        if (fallbackModes[index]) return fallbackModes[index];
        return 'individual';
      })
    );
    setSpecialTourTasks(
      Array.from({ length: effectiveTourCount }, (_, index) => {
        const taskNumbers = toursFromSettings[index]?.taskNumbers || [1];
        return taskNumbers.join(', ');
      })
    );
    setSpecialTourCaptainsTask(
      Array.from({ length: effectiveTourCount }, (_, index) => {
        return toursFromSettings[index]?.captainsTask || false;
      })
    );
    setSpecialTourCaptainsTasks(
      Array.from({ length: effectiveTourCount }, (_, index) => {
        const ctn = toursFromSettings[index]?.captainsTaskNumbers;
        return ctn && ctn.length > 0 ? ctn.join(', ') : '';
      })
    );
    setSpecialCaptainsRoomId(typeof rawCaptainsRoomId === 'string' ? rawCaptainsRoomId : '');
    setSpecialRoomLayouts(parsedRoomLayouts);
    setTeamTableMergesTour3(parsedTour3TableMerges);
    setTeamTourForPrint(null);
    setImportFile(null);
    setAnswerTemplateFile(null);
    setA3TemplateFile(null);
    setPendingRooms([]);
    setNewRoomName('');
    setNewRoomCapacity(30);
    setModalOpen(true);
    loadRooms(comp.id);
  };

  const addPendingRoom = () => {
    const name = newRoomName.trim();
    if (!name) return;
    if (pendingRooms.some((r) => r.name === name)) {
      setError('Аудитория с таким названием уже добавлена');
      return;
    }
    setPendingRooms((prev) => [...prev, { name, capacity: newRoomCapacity }]);
    setNewRoomName('');
    setNewRoomCapacity(30);
  };

  const removePendingRoom = (index: number) => {
    setPendingRooms((prev) => prev.filter((_, i) => i !== index));
  };

  const addExistingRoom = async () => {
    if (!editingId) return;
    const name = newRoomName.trim();
    if (!name) return;
    if (existingRooms.some((r) => r.name === name)) {
      setError('Аудитория с таким названием уже существует');
      return;
    }
    try {
      await api.post(`rooms/${editingId}`, { name, capacity: newRoomCapacity });
      setNewRoomName('');
      setNewRoomCapacity(30);
      await loadRooms(editingId);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось добавить аудиторию.';
      setError(message);
    }
  };

  const deleteExistingRoom = async (roomId: string) => {
    if (!editingId) return;
    try {
      await api.delete(`rooms/room/${roomId}`);
      if (specialCaptainsRoomId === roomId) {
        setSpecialCaptainsRoomId('');
      }
      setSpecialRoomLayouts((prev) => {
        const next = { ...prev };
        delete next[roomId];
        return next;
      });
      setTeamTableMergesTour3((prev) => {
        const next = { ...prev };
        delete next[roomId];
        return next;
      });
      await loadRooms(editingId);
    } catch {
      setError('Не удалось удалить аудиторию.');
    }
  };

  const updateRoomLayout = (
    roomId: string,
    field: 'seatsPerTable' | 'teamSeatsPerTable' | 'seatMatrixColumns',
    value: number
  ) => {
    const fallbackByField = {
      seatsPerTable: 1,
      teamSeatsPerTable: 2,
      seatMatrixColumns: 3,
    } as const;
    setSpecialRoomLayouts((prev) => ({
      ...prev,
      [roomId]: {
        seatsPerTable: parsePositiveInt(prev[roomId]?.seatsPerTable, 1),
        teamSeatsPerTable: parsePositiveInt(prev[roomId]?.teamSeatsPerTable, 2),
        seatMatrixColumns: parsePositiveInt(prev[roomId]?.seatMatrixColumns, 3),
        [field]: parsePositiveInt(value, fallbackByField[field]),
      },
    }));
  };

  const onSubmit = async (data: CompetitionForm) => {
    setSaving(true);
    setError(null);
    try {
      const tours = specialTourModes.map((mode, index) => ({
        tour_number: index + 1,
        mode,
        task_numbers: parseTaskNumbersInput(specialTourTasks[index] || '1'),
        captains_task: specialTourCaptainsTask[index] || false,
        captains_task_numbers: specialTourCaptainsTask[index]
          ? parseTaskNumbersInput(specialTourCaptainsTasks[index] || '1')
          : [],
      }));
      const normalizedRoomLayouts = Object.fromEntries(
        Object.entries(specialRoomLayouts).map(([roomId, layout]) => [
          roomId,
          {
            seats_per_table: parsePositiveInt(layout.seatsPerTable, 1),
            seat_matrix_columns: parsePositiveInt(layout.seatMatrixColumns, 3),
          },
        ])
      );
      const normalizedTeamRoomLayouts = Object.fromEntries(
        Object.entries(specialRoomLayouts).map(([roomId, layout]) => [
          roomId,
          { seats_per_table: parsePositiveInt(layout.teamSeatsPerTable, 2) },
        ])
      );
      const normalizedTour3TableMerges = thirdTourIsTeamMode
        ? Object.fromEntries(
            Object.entries(teamTableMergesTour3)
              .map(([roomId, text]) => [roomId, parseTeamTableMergesInput(text)] as const)
              .filter(([, groups]) => groups.length > 0)
          )
        : {};

      const payload = {
        ...data,
        special_tour_modes: data.is_special ? specialTourModes : null,
        special_settings: data.is_special
          ? {
              import_supported_formats: ['json', 'csv', 'xlsx'],
              archive_mode: 'participant_folders',
              templates_format: 'word_docx',
              captains_room_id: hasIndividualCaptainsMode && specialCaptainsRoomId ? specialCaptainsRoomId : null,
              default_seats_per_table: 1,
              team_default_seats_per_table: 2,
              room_layouts: normalizedRoomLayouts,
              team_room_layouts: normalizedTeamRoomLayouts,
              team_table_merges: Object.keys(normalizedTour3TableMerges).length > 0
                ? { '3': normalizedTour3TableMerges }
                : {},
              tours,
            }
          : null,
      };

      if (editingId) {
        await api.put(`competitions/${editingId}`, payload);
      } else {
        const { data: newComp } = await api.post('competitions', payload);
        // Create rooms for the new competition
        for (const room of pendingRooms) {
          await api.post(`rooms/${newComp.id}`, { name: room.name, capacity: room.capacity });
        }
      }
      setModalOpen(false);
      reset();
      setEditingId(null);
      setPendingRooms([]);
      setExistingRooms([]);
      setSpecialTourModes([]);
      setSpecialTourTasks([]);
      setSpecialTourCaptainsTask([]);
      setSpecialCaptainsRoomId('');
      setSpecialRoomLayouts({});
      setTeamTableMergesTour3({});
      setTeamTourForPrint(null);
      setImportFile(null);
      setAnswerTemplateFile(null);
      setA3TemplateFile(null);
      setBadgeTemplateFile(null);
      setBadgePhotosZipFile(null);
      await loadCompetitions();
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось сохранить олимпиаду.';
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (id: string, action: string) => {
    try {
      await api.post(`competitions/${id}/${action}`);
      await loadCompetitions();
    } catch {
      setError('Не удалось обновить статус.');
    }
  };

  const openRegModal = async (comp: Competition) => {
    const teamTours = extractToursFromSettings(comp)
      .filter((tour) => tour.mode === 'team')
      .map((tour) => tour.tourNumber);

    setRegCompetition(comp);
    setTeamTourForPrint(teamTours.length > 0 ? teamTours[0] : null);
    setRegModalOpen(true);
    setRegLoading(true);
    setParticipantSearch('');
    setImportFile(null);
    setAnswerTemplateFile(null);
    setA3TemplateFile(null);
    setBadgeTemplateFile(null);
    setBadgePhotosZipFile(null);
    // Fetch template info
    api.get<{ templates: { kind: string; filename: string; display_filename?: string; modified_at?: string }[] }>('admin/special/templates')
      .then(({ data }) => {
        const info: Record<string, { filename: string; display_filename: string; modified_at?: string }> = {};
        for (const t of data.templates) {
          info[t.kind] = { filename: t.filename, display_filename: t.display_filename ?? 'Нет шаблона', modified_at: t.modified_at };
        }
        setTemplateInfo(info);
      })
      .catch(() => {});

    try {
      const [regRes, participantsRes] = await Promise.all([
        api.get<{ items: AdminRegistrationItem[]; total: number }>(`admin/registrations/${comp.id}`),
        api.get<{ participants: { id: string; user_id: string; full_name: string; school: string; institution_location?: string; is_captain?: boolean }[] }>('admin/participants'),
      ]);
      setRegItems(regRes.data.items || []);
      setParticipants(participantsRes.data.participants || []);
    } catch {
      try {
        const regRes = await api.get<{ items: AdminRegistrationItem[]; total: number }>(`admin/registrations/${comp.id}`);
        setRegItems(regRes.data.items || []);
      } catch {
        setError('Не удалось загрузить регистрации.');
      }
      setParticipants([]);
    } finally {
      setRegLoading(false);
    }
  };

  const handleAdminRegister = async (participantId: string) => {
    if (!regCompetition) return;
    setRegistering(true);
    setError(null);
    setLastAddedRegId(null);
    try {
      const res = await api.post<{ registration_id: string; entry_token: string }>('admin/registrations', {
        participant_id: participantId,
        competition_id: regCompetition.id,
      });
      setLastAddedRegId(res.data.registration_id);
      // Reload registrations
      const regRes = await api.get<{ items: AdminRegistrationItem[]; total: number }>(
        `admin/registrations/${regCompetition.id}`
      );
      setRegItems(regRes.data.items || []);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка регистрации.';
      setError(message);
    } finally {
      setRegistering(false);
    }
  };

  const handleDeleteRegistration = async () => {
    if (!deleteConfirmId || !regCompetition) return;
    setDeletingReg(true);
    setError(null);
    try {
      await api.delete(`admin/registrations/${deleteConfirmId}`);
      const regRes = await api.get<{ items: AdminRegistrationItem[]; total: number }>(
        `admin/registrations/${regCompetition.id}`
      );
      setRegItems(regRes.data.items || []);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка удаления регистрации.';
      setError(message);
    } finally {
      setDeletingReg(false);
      setDeleteConfirmId(null);
      setDeleteConfirmName('');
    }
  };

  const handleReplaceRegistration = async (newParticipantId: string) => {
    if (!replaceRegId || !regCompetition) return;
    setReplacing(true);
    setError(null);
    setReplaceResult(null);
    try {
      const res = await api.post<ReplaceParticipantResponse>(
        `admin/registrations/${replaceRegId}/replace`,
        { new_participant_id: newParticipantId }
      );
      setReplaceResult(res.data);
      const regRes = await api.get<{ items: AdminRegistrationItem[]; total: number }>(
        `admin/registrations/${regCompetition.id}`
      );
      setRegItems(regRes.data.items || []);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка замены участника.';
      setError(message);
    } finally {
      setReplacing(false);
      setReplaceRegId(null);
      setReplaceSearch('');
    }
  };

  const handleAdmitAndDownload = async (registrationId: string, participantName: string) => {
    setDownloadingRegId(registrationId);
    setError(null);
    setWarning(null);
    try {
      const response = await api.post(
        `admin/registrations/${registrationId}/admit-and-download`,
        {},
        { responseType: 'blob', timeout: 120000 }
      );
      const warnings = response.headers['x-warnings'] as string | undefined;
      if (warnings) setWarning(warnings);
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/zip' }));
      const link = document.createElement('a');
      link.href = url;
      const safe = participantName.replace(/[^a-zA-Zа-яА-ЯёЁ0-9_\- ]/g, '').trim() || registrationId;
      link.download = `${safe}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      // Reload registrations (participant may have been admitted)
      if (regCompetition) {
        const regRes = await api.get<{ items: AdminRegistrationItem[]; total: number }>(
          `admin/registrations/${regCompetition.id}`
        );
        setRegItems(regRes.data.items || []);
      }
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка генерации файлов.';
      setError(message);
    } finally {
      setDownloadingRegId(null);
    }
  };

  const searchInstitutions = async (q: string) => {
    if (!q.trim()) { setInstSearchResults([]); return; }
    try {
      const res = await api.get<{id: string; name: string; city?: string}[]>(`institutions/search?q=${encodeURIComponent(q)}&limit=10`);
      setInstSearchResults(res.data || []);
    } catch { setInstSearchResults([]); }
  };

  const handleSaveParticipantFields = async () => {
    if (!editParticipantId) return;
    setSavingParticipant(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (editInstLocation !== '') params.append('institution_location', editInstLocation);
      if (editInstId) params.append('institution_id', editInstId);
      await api.patch(`admin/participants/${editParticipantId}?${params.toString()}`);
      // Reload registrations to show updated info
      if (regCompetition) {
        const regRes = await api.get<{ items: AdminRegistrationItem[]; total: number }>(
          `admin/registrations/${regCompetition.id}`
        );
        setRegItems(regRes.data.items || []);
      }
      setEditParticipantId(null);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка сохранения.';
      setError(message);
    } finally {
      setSavingParticipant(false);
    }
  };

  const handleUploadParticipantPhoto = async () => {
    if (!photoUploadParticipantId || !photoFile) return;
    setUploadingPhoto(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', photoFile);
      await api.post(`admin/participants/${photoUploadParticipantId}/badge-photo`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPhotoUploadRegId(null);
      setPhotoUploadParticipantId(null);
      setPhotoFile(null);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Ошибка загрузки фото.';
      setError(message);
    } finally {
      setUploadingPhoto(false);
    }
  };

  const openAuthorizedPrintPage = async (endpoint: string) => {
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      setError('Браузер заблокировал всплывающее окно. Разрешите pop-up для печати.');
      return;
    }

    printWindow.document.write('<html><body style="font-family: sans-serif; padding: 16px;">Загрузка...</body></html>');
    printWindow.document.close();

    try {
      const response = await api.get<string>(endpoint, {
        responseType: 'text',
        headers: { Accept: 'text/html' },
        timeout: 60000,
      });
      printWindow.document.open();
      printWindow.document.write(response.data);
      printWindow.document.close();
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось открыть страницу печати.';
      try {
        printWindow.document.open();
        printWindow.document.write(`<html><body style="font-family: sans-serif; padding: 16px;"><h3>Ошибка</h3><p>${message}</p></body></html>`);
        printWindow.document.close();
      } catch {
        printWindow.close();
      }
      setError(message);
    }
  };

  const _stopBadgePoll = () => {
    if (badgeTaskPollRef.current) {
      clearInterval(badgeTaskPollRef.current);
      badgeTaskPollRef.current = null;
    }
  };

  const handleStartBadgeGeneration = async () => {
    if (!regCompetition) return;
    setError(null);
    setBadgeTaskId(null);
    setBadgeTaskState(null);
    setBadgeTaskProgress(null);
    setBadgesDownloading(true);
    try {
      const { data } = await api.post<{ task_id: string }>(
        `admin/registrations/${regCompetition.id}/badges-pdf/start`
      );
      const taskId = data.task_id;
      setBadgeTaskId(taskId);
      setBadgeTaskState('PENDING');

      // Poll for status every 5 seconds
      _stopBadgePoll();
      badgeTaskPollRef.current = setInterval(async () => {
        try {
          const { data: status } = await api.get<{
            state: string;
            status?: string;
            stage?: string;
            current?: number;
            total?: number;
            object_name?: string;
            message?: string;
          }>(`admin/badge-tasks/${taskId}/status`);

          setBadgeTaskState(status.state);
          if (status.state === 'PROGRESS') {
            setBadgeTaskProgress({
              stage: status.stage || '',
              current: status.current ?? 0,
              total: status.total ?? 0,
            });
          }
          if (status.state === 'SUCCESS' || status.state === 'FAILURE') {
            _stopBadgePoll();
            setBadgesDownloading(false);
            const innerFailed =
              status.state === 'FAILURE' ||
              (status.state === 'SUCCESS' && status.status === 'failed');
            if (innerFailed) {
              setBadgeTaskState('FAILURE');
              setError(`Генерация бейджей завершилась с ошибкой: ${status.message || 'неизвестно'}`);
            }
          }
        } catch {
          // polling errors are transient, keep polling
        }
      }, 5000);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось запустить генерацию бейджей.';
      setError(message);
      setBadgesDownloading(false);
    }
  };

  const handleDownloadBadgePdf = async () => {
    if (!badgeTaskId) return;
    try {
      const response = await api.get(`admin/badge-tasks/${badgeTaskId}/download`, {
        responseType: 'blob',
      });
      downloadBlob(new Blob([response.data], { type: 'application/pdf' }), `badges_${regCompetition?.id}.pdf`);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось скачать PDF.';
      setError(message);
    }
  };

  // Keep for backwards compat (not used by new UI)
  const handleDownloadBadges = handleStartBadgeGeneration;

  const handleOpenSeatingPlanPrint = async () => {
    if (!regCompetition) return;
    setError(null);
    await openAuthorizedPrintPage(`admin/competitions/${regCompetition.id}/seating-plan/print`);
  };

  const handleOpenTeamSeatingPlanPrint = async () => {
    if (!regCompetition || !teamTourForPrint) return;
    setError(null);
    const query = new URLSearchParams({ tour_number: String(teamTourForPrint) }).toString();
    await openAuthorizedPrintPage(`admin/competitions/${regCompetition.id}/seating-plan/print?${query}`);
  };

  const handleImportParticipants = async () => {
    if (!regCompetition || !importFile) return;
    setImporting(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', importFile);
      const { data } = await api.post(
        `admin/competitions/${regCompetition.id}/special/import-participants?register_to_competition=true`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );

      const regRes = await api.get<{ items: AdminRegistrationItem[]; total: number }>(
        `admin/registrations/${regCompetition.id}`
      );
      setRegItems(regRes.data.items || []);
      setImportFile(null);

      const imported = data?.registered_to_competition ?? 0;
      const errorsCount = Array.isArray(data?.errors) ? data.errors.length : 0;
      setError(null);
      alert(`Импорт завершен: зарегистрировано ${imported}, ошибок ${errorsCount}.`);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось импортировать участников.';
      setError(message);
    } finally {
      setImporting(false);
    }
  };

  const handleAdmitAllAndDownload = async () => {
    if (!regCompetition) return;
    setAdmitAndDownloadLoading(true);
    setBlanksTaskId(null);
    setBlanksTaskState(null);
    setBlanksTaskProgress(null);
    setError(null);
    try {
      const res = await api.post<{ task_id: string; admitted_now: number; admit_errors: unknown[] }>(
        `admin/competitions/${regCompetition.id}/special/admit-all-and-download`,
        {}
      );
      const taskId = res.data.task_id;
      setBlanksTaskId(taskId);
      setBlanksTaskState('PENDING');

      // Reload registrations (participants may have been admitted)
      const regRes = await api.get<{ items: AdminRegistrationItem[]; total: number }>(
        `admin/registrations/${regCompetition.id}`
      );
      setRegItems(regRes.data.items || []);

      // Poll for progress
      const poll = async () => {
        try {
          const status = await api.get<{
            state: string;
            stage?: string;
            current?: number;
            total?: number;
            participant?: string;
            added_files?: number;
            object_name?: string;
            errors?: string[];
            message?: string;
          }>(`admin/competitions/${regCompetition.id}/blanks-tasks/${taskId}/status`);

          setBlanksTaskState(status.data.state);

          if (status.data.state === 'PROGRESS') {
            setBlanksTaskProgress({
              stage: status.data.stage || '',
              current: status.data.current ?? 0,
              total: status.data.total ?? 0,
              participant: status.data.participant || '',
            });
            setTimeout(poll, 1500);
          } else if (status.data.state === 'SUCCESS') {
            setBlanksTaskProgress(null);
            setAdmitAndDownloadLoading(false);
            // Auto-download
            const dlRes = await api.get(
              `admin/competitions/${regCompetition.id}/blanks-tasks/${taskId}/download`,
              { responseType: 'blob' }
            );
            downloadBlob(new Blob([dlRes.data], { type: 'application/zip' }), `special_olympiad_${regCompetition.id}.zip`);
            if (status.data.errors && status.data.errors.length > 0) {
              setWarning(`Архив готов, но есть предупреждения: ${status.data.errors.slice(0, 3).join('; ')}`);
            }
          } else if (status.data.state === 'FAILURE') {
            setAdmitAndDownloadLoading(false);
            setError(`Ошибка генерации ZIP: ${status.data.message || 'неизвестная ошибка'}`);
          } else {
            // PENDING / STARTED
            setTimeout(poll, 2000);
          }
        } catch {
          setAdmitAndDownloadLoading(false);
          setError('Не удалось получить статус задачи генерации архива.');
        }
      };
      setTimeout(poll, 1500);
    } catch (err: unknown) {
      setAdmitAndDownloadLoading(false);
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось допустить участников и запустить генерацию архива.';
      setError(message);
    }
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  const handleDownloadTemplate = async (kind: SpecialTemplateKind) => {
    setTemplateDownloadingKind(kind);
    setError(null);
    try {
      const response = await api.get(`admin/special/templates/${kind}/download`, {
        responseType: 'blob',
      });
      const fallbackName = kind === 'answer_blank'
        ? 'special_answer_blank_template.docx'
        : kind === 'a3_cover'
          ? 'special_cover_a3_template.docx'
          : 'badge_template.docx';
      downloadBlob(new Blob([response.data]), fallbackName);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось скачать шаблон.';
      setError(message);
    } finally {
      setTemplateDownloadingKind(null);
    }
  };

  const handleUploadTemplate = async (kind: SpecialTemplateKind, file: File | null) => {
    if (!file) return;
    setTemplateUploadingKind(kind);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      await api.post(`admin/special/templates/${kind}/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (kind === 'answer_blank') {
        setAnswerTemplateFile(null);
      } else if (kind === 'a3_cover') {
        setA3TemplateFile(null);
      } else {
        setBadgeTemplateFile(null);
      }
      alert('Шаблон успешно обновлен.');
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось загрузить шаблон.';
      setError(message);
    } finally {
      setTemplateUploadingKind(null);
    }
  };

  const handleDeleteTemplate = async (kind: SpecialTemplateKind) => {
    if (!confirm('Сбросить шаблон на стандартный?')) return;
    setTemplateDeletingKind(kind);
    setError(null);
    try {
      await api.delete(`admin/special/templates/${kind}`);
      alert('Шаблон сброшен на стандартный.');
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось удалить шаблон.';
      setError(message);
    } finally {
      setTemplateDeletingKind(null);
    }
  };

  const handleUploadBadgePhotosZip = async () => {
    if (!badgePhotosZipFile) return;
    setBadgePhotosUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', badgePhotosZipFile);
      const { data } = await api.post('admin/special/templates/badge/photos/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setBadgePhotosZipFile(null);
      const imported = Number((data as { imported_files?: number; imported?: number })?.imported_files
        ?? (data as { imported_files?: number; imported?: number })?.imported
        ?? 0);
      alert(`Фотографии успешно загружены: ${imported}.`);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось загрузить ZIP с фотографиями.';
      setError(message);
    } finally {
      setBadgePhotosUploading(false);
    }
  };

  const handleUploadBadgeFonts = async () => {
    if (!badgeFontsFile) return;
    setBadgeFontsUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', badgeFontsFile);
      const { data } = await api.post('admin/special/templates/badge/fonts/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setBadgeFontsFile(null);
      const imported = Number((data as { imported_files?: number })?.imported_files ?? 0);
      alert(`Шрифты успешно загружены: ${imported}.`);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Не удалось загрузить шрифты.';
      setError(message);
    } finally {
      setBadgeFontsUploading(false);
    }
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

  const filteredParticipants = participants.filter((p) => {
    // Exclude already registered
    if (regItems.some((r) => r.participant_id === p.id)) return false;
    if (!participantSearch) return true;
    const search = participantSearch.toLowerCase();
    return (
      p.full_name.toLowerCase().includes(search) ||
      p.school.toLowerCase().includes(search) ||
      (p.institution_location || '').toLowerCase().includes(search)
    );
  });

  const getStatusLabel = (status: string): string => {
    const labels: Record<string, string> = {
      draft: 'Черновик',
      registration_open: 'Регистрация открыта',
      in_progress: 'Проходит',
      checking: 'Проверка',
      published: 'Опубликована',
    };
    return labels[status] || status;
  };

  const handleAddRoom = () => {
    if (editingId) {
      addExistingRoom();
    } else {
      addPendingRoom();
    }
  };

  const roomsList = editingId ? existingRooms : pendingRooms;

  if (loading) {
    return (
      <Layout>
        <Spinner />
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="flex-between mb-24">
        <h1>Олимпиады</h1>
        <Button onClick={openCreate}>Создать олимпиаду</Button>
      </div>

      {error && <div className="alert alert-error mb-16">{error}</div>}
      {warning && (
        <div
          className="mb-16"
          style={{
            background: '#fefce8',
            border: '1px solid #fde047',
            borderRadius: 8,
            padding: '10px 14px',
            color: '#854d0e',
            fontSize: 13,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
          }}
        >
          <span style={{ fontSize: 16, flexShrink: 0 }}>⚠</span>
          <span>{warning}</span>
          <button
            onClick={() => setWarning(null)}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#854d0e', fontSize: 14, padding: '0 2px', flexShrink: 0 }}
          >
            ✕
          </button>
        </div>
      )}

      <table className="table">
        <thead>
          <tr>
            <th>Название</th>
            <th>Дата</th>
            <th>Статус</th>
            <th>Тип</th>
            <th>Варианты</th>
            <th>Макс. балл</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {competitions.length === 0 ? (
            <tr>
              <td colSpan={7} className="text-center text-muted">
                Олимпиад пока нет.
              </td>
            </tr>
          ) : (
            competitions.map((comp) => (
              <tr key={comp.id}>
                <td>{comp.name}</td>
                <td>{new Date(comp.date).toLocaleDateString('ru-RU')}</td>
                <td>{getStatusLabel(comp.status)}</td>
                <td>{comp.is_special ? `Особая${comp.special_tours_count ? ` (${comp.special_tours_count} тур.)` : ''}` : 'Обычная'}</td>
                <td>{comp.variants_count}</td>
                <td>{comp.max_score}</td>
                <td>
                  <div className="flex gap-8 flex-wrap">
                    <Button
                      variant="secondary"
                      className="btn-sm"
                      onClick={() => openEdit(comp)}
                    >
                      Изменить
                    </Button>
                    <Button
                      variant="secondary"
                      className="btn-sm"
                      onClick={() => openRegModal(comp)}
                    >
                      Регистрации
                    </Button>
                    {comp.status === 'draft' && (
                      <Button
                        className="btn-sm"
                        onClick={() => handleStatusChange(comp.id, 'open-registration')}
                      >
                        Открыть рег.
                      </Button>
                    )}
                    {comp.status === 'registration_open' && (
                      <Button
                        variant="secondary"
                        className="btn-sm"
                        onClick={() => handleStatusChange(comp.id, 'start')}
                      >
                        Начать
                      </Button>
                    )}
                    {comp.status === 'in_progress' && (
                      <Button
                        variant="danger"
                        className="btn-sm"
                        onClick={() => handleStatusChange(comp.id, 'start-checking')}
                      >
                        Завершить
                      </Button>
                    )}
                    {comp.status === 'checking' && (
                      <Button
                        variant="primary"
                        className="btn-sm"
                        onClick={() => handleStatusChange(comp.id, 'publish')}
                      >
                        Опубликовать
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <Modal
        isOpen={modalOpen}
        onClose={() => {
          setModalOpen(false);
          reset();
          setEditingId(null);
          setPendingRooms([]);
          setExistingRooms([]);
          setSpecialTourModes([]);
          setSpecialTourTasks([]);
          setSpecialTourCaptainsTask([]);
          setSpecialCaptainsRoomId('');
          setSpecialRoomLayouts({});
          setTeamTableMergesTour3({});
          setTeamTourForPrint(null);
          setImportFile(null);
          setAnswerTemplateFile(null);
          setA3TemplateFile(null);
        }}
        title={editingId ? 'Редактировать олимпиаду' : 'Создать олимпиаду'}
      >
        <form onSubmit={handleSubmit(onSubmit)}>
          <Input
            label="Название"
            error={errors.name?.message}
            {...register('name')}
          />
          <Input
            label="Дата проведения"
            type="date"
            error={errors.date?.message}
            {...register('date')}
          />
          <Input
            label="Начало регистрации"
            type="datetime-local"
            error={errors.registration_start?.message}
            {...register('registration_start')}
          />
          <Input
            label="Конец регистрации"
            type="datetime-local"
            error={errors.registration_end?.message}
            {...register('registration_end')}
          />
          <Input
            label="Количество вариантов"
            type="number"
            min={1}
            error={errors.variants_count?.message}
            {...register('variants_count')}
          />
          <Input
            label="Максимальный балл"
            type="number"
            min={1}
            error={errors.max_score?.message}
            {...register('max_score')}
          />
          <div className="form-group">
            <label className="label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" {...register('is_special')} />
              Особая олимпиада
            </label>
          </div>
          {isSpecialCompetition && (
            <>
              <Input
                label="Количество туров"
                type="number"
                min={1}
                error={errors.special_tours_count?.message}
                {...register('special_tours_count')}
              />
              {specialTourModes.length > 0 && (
                <div className="form-group">
                  <label className="label">Режим каждого тура</label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {specialTourModes.map((mode, index) => (
                      <div
                        key={`tour-mode-${index}`}
                        style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr auto', gap: 8, alignItems: 'center' }}
                      >
                        <span className="text-muted">Тур {toRoman(index + 1)}</span>
                        <select
                          className="input"
                          value={mode}
                          onChange={(e) =>
                            setSpecialTourModes((prev) => prev.map((m, i) => (i === index ? e.target.value : m)))
                          }
                        >
                          <option value="individual">Индивидуальный</option>
                          <option value="individual_captains">Индивидуальный (капитаны)</option>
                          <option value="team">Командный</option>
                        </select>
                        <Input
                          label=""
                          placeholder="Задания: 1,2,3"
                          value={specialTourTasks[index] || ""}
                          onChange={(e) =>
                            setSpecialTourTasks((prev) => prev.map((tasks, i) => (i === index ? e.target.value : tasks)))
                          }
                        />
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, whiteSpace: 'nowrap', cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={specialTourCaptainsTask[index] || false}
                              onChange={(e) =>
                                setSpecialTourCaptainsTask((prev) => prev.map((v, i) => (i === index ? e.target.checked : v)))
                              }
                            />
                            Задания для капитанов
                          </label>
                          {specialTourCaptainsTask[index] && (
                            <input
                              className="input"
                              placeholder="Задания: 1,2"
                              value={specialTourCaptainsTasks[index] || ''}
                              onChange={(e) =>
                                setSpecialTourCaptainsTasks((prev) => prev.map((v, i) => (i === index ? e.target.value : v)))
                              }
                              style={{ fontSize: 12, padding: '4px 8px', minWidth: 100 }}
                            />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="text-muted" style={{ marginTop: 8, fontSize: 12 }}>
                    Для каждого тура укажите номера заданий через запятую, например: 1,2,3.
                  </p>
                </div>
              )}
              {hasIndividualCaptainsMode && (
                <div className="form-group">
                  <label className="label">Аудитория капитанов (для режима «индивидуальный, капитаны»)</label>
                  {editingId ? (
                    <select
                      className="input"
                      value={specialCaptainsRoomId}
                      onChange={(e) => setSpecialCaptainsRoomId(e.target.value)}
                    >
                      <option value="">Не выбрано</option>
                      {existingRooms.map((room) => (
                        <option key={room.id} value={room.id}>
                          {room.name} ({room.capacity} мест)
                        </option>
                      ))}
                    </select>
                  ) : (
                    <p className="text-muted" style={{ marginTop: 4, fontSize: 12 }}>
                      Настройте аудиторию капитанов после сохранения олимпиады и добавления аудиторий.
                    </p>
                  )}
                </div>
              )}
            </>
          )}

          {/* Rooms section */}
          <div style={{ marginTop: 16, marginBottom: 16 }}>
            <label className="label" style={{ marginBottom: 8, display: 'block' }}>Аудитории</label>

            {/* Add room form */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <div style={{ flex: 1 }}>
                <Input
                  label="Название"
                  value={newRoomName}
                  onChange={(e) => setNewRoomName(e.target.value)}
                />
              </div>
              <div style={{ width: 100 }}>
                <Input
                  label="Мест"
                  type="number"
                  min={1}
                  value={newRoomCapacity}
                  onChange={(e) => setNewRoomCapacity(Number(e.target.value))}
                />
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={handleAddRoom}
                style={{ marginBottom: 16 }}
              >
                Добавить
              </Button>
            </div>

            {/* Rooms list */}
            {roomsLoading ? (
              <p className="text-muted">Загрузка аудиторий...</p>
            ) : roomsList.length > 0 ? (
              <div
                style={{
                  border: '1px solid var(--glass-border, #e2e8f0)',
                  borderRadius: 8,
                  overflow: 'hidden',
                  marginTop: 4,
                }}
              >
                {roomsList.map((room, index) => (
                  <div
                    key={'id' in room ? (room as Room).id : index}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      borderBottom:
                        index < roomsList.length - 1
                          ? '1px solid var(--glass-border, #e2e8f0)'
                          : 'none',
                      background: index % 2 === 0 ? 'var(--glass-surface, #f8fafc)' : 'transparent',
                    }}
                  >
                    <span>
                      <strong>{index + 1}.</strong> {room.name}
                      <span className="text-muted" style={{ marginLeft: 8 }}>
                        ({room.capacity} мест)
                      </span>
                    </span>
                    <Button
                      type="button"
                      variant="danger"
                      className="btn-sm"
                      onClick={() =>
                        editingId
                          ? deleteExistingRoom((room as Room).id)
                          : removePendingRoom(index)
                      }
                    >
                      Удалить
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted" style={{ marginTop: 4, fontSize: 13 }}>
                Аудитории не добавлены
              </p>
            )}
          </div>

          {isSpecialCompetition && editingId && existingRooms.length > 0 && (
            <div style={{ marginBottom: 16, padding: 12, border: '1px solid var(--glass-border, #e2e8f0)', borderRadius: 8 }}>
              <h3 style={{ marginBottom: 8 }}>Конструктор рассадки по столам</h3>
              <p className="text-muted" style={{ marginBottom: 10, fontSize: 12 }}>
                Настройка применяется в схеме рассадки и печати. Для командного тура можно задать отдельную плотность мест.
              </p>
              {formTeamTourNumbers.length > 0 && (
                <p className="text-muted" style={{ marginBottom: 10, fontSize: 12 }}>
                  Командные туры: {formTeamTourNumbers.join(', ')}.
                </p>
              )}
              <div style={{ display: 'grid', gap: 8 }}>
                {existingRooms.map((room) => {
                  const layout = specialRoomLayouts[room.id] || { seatsPerTable: 1, teamSeatsPerTable: 2, seatMatrixColumns: 3 };
                  return (
                    <div
                      key={`layout-${room.id}`}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1.2fr 1fr 1fr 1fr',
                        gap: 8,
                        alignItems: 'end',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600 }}>{room.name}</div>
                        <div className="text-muted" style={{ fontSize: 12 }}>{room.capacity} мест</div>
                      </div>
                      <Input
                        label="Мест за столом"
                        type="number"
                        min={1}
                        value={layout.seatsPerTable}
                        onChange={(e) => updateRoomLayout(room.id, 'seatsPerTable', Number(e.target.value || 1))}
                      />
                      <Input
                        label="Командный режим"
                        type="number"
                        min={1}
                        value={layout.teamSeatsPerTable}
                        onChange={(e) => updateRoomLayout(room.id, 'teamSeatsPerTable', Number(e.target.value || 2))}
                      />
                      <Input
                        label="Колонок сетки"
                        type="number"
                        min={1}
                        value={layout.seatMatrixColumns}
                        onChange={(e) => updateRoomLayout(room.id, 'seatMatrixColumns', Number(e.target.value || 3))}
                      />
                      {thirdTourIsTeamMode && (
                        <div style={{ gridColumn: '1 / -1' }}>
                          <Input
                            label="Объединения столов (тур 3)"
                            placeholder="Например: 1+2,3+4+5"
                            value={teamTableMergesTour3[room.id] || ''}
                            onChange={(e) =>
                              setTeamTableMergesTour3((prev) => ({ ...prev, [room.id]: e.target.value }))
                            }
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              {thirdTourIsTeamMode && (
                <p className="text-muted" style={{ marginTop: 8, fontSize: 12 }}>
                  Объединения столов для тура 3: формат `1+2,3+4+5` (каждая группа столов через запятую).
                </p>
              )}
            </div>
          )}

          <Button type="submit" loading={saving} style={{ width: '100%' }}>
            {editingId ? 'Сохранить' : 'Создать'}
          </Button>
        </form>
      </Modal>

      {/* Registrations Modal */}
      <Modal
        isOpen={regModalOpen}
        onClose={() => {
          setRegModalOpen(false);
          setRegCompetition(null);
          setRegItems([]);
          setParticipants([]);
          setParticipantSearch('');
          setTeamTourForPrint(null);
          setImportFile(null);
          setAnswerTemplateFile(null);
          setA3TemplateFile(null);
          setBadgeTemplateFile(null);
          setBadgePhotosZipFile(null);
          _stopBadgePoll();
          setBadgeTaskId(null);
          setBadgeTaskState(null);
          setBadgeTaskProgress(null);
          setBadgesDownloading(false);
        }}
        title={`Регистрации — ${regCompetition?.name || ''}`}
      >
        {regLoading ? (
          <Spinner />
        ) : (
          <div>
            {/* Download badges button */}
            {regItems.length > 0 && (
              <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <Button
                  variant="secondary"
                  onClick={() => regCompetition && navigate(`/admin/badge-editor/${regCompetition.id}`)}
                >
                  Редактор бейджей
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => regCompetition && navigate(`/admin/competitions/${regCompetition.id}/staff`)}
                >
                  Сотрудники
                </Button>
                <Button
                  variant="secondary"
                  onClick={handleStartBadgeGeneration}
                  loading={badgesDownloading}
                  disabled={badgesDownloading}
                >
                  {badgesDownloading ? 'Генерация бейджей…' : 'Создать PDF бейджей'}
                </Button>
                {badgesDownloading && !badgeTaskProgress && (
                  <span style={{ fontSize: 13, color: 'var(--text-muted, #666)' }}>
                    В очереди…
                  </span>
                )}
                {badgesDownloading && badgeTaskProgress && (
                  <span style={{ fontSize: 13, color: 'var(--text-muted, #666)' }}>
                    {{
                      loading: 'Загрузка данных…',
                      generating: `Генерация DOCX: ${badgeTaskProgress.current} / ${badgeTaskProgress.total}`,
                      converting: `Конвертация PDF: ${badgeTaskProgress.current} / ${badgeTaskProgress.total}`,
                      assembling: 'Сборка страниц…',
                    }[badgeTaskProgress.stage] ?? badgeTaskProgress.stage}
                  </span>
                )}
                {badgeTaskState === 'SUCCESS' && badgeTaskId && (
                  <Button onClick={handleDownloadBadgePdf}>
                    Скачать PDF бейджей
                  </Button>
                )}
                <Button variant="secondary" onClick={handleOpenSeatingPlanPrint}>
                  Рассадка / печать
                </Button>
                {registrationTeamTourNumbers.length > 0 && (
                  <>
                    <select
                      className="input"
                      value={teamTourForPrint ?? registrationTeamTourNumbers[0]}
                      onChange={(e) => setTeamTourForPrint(Number(e.target.value))}
                      style={{ width: 180 }}
                    >
                      {registrationTeamTourNumbers.map((tourNumber) => (
                        <option key={`team-tour-${tourNumber}`} value={tourNumber}>
                          Командный тур {tourNumber}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="secondary"
                      onClick={handleOpenTeamSeatingPlanPrint}
                      disabled={!teamTourForPrint}
                    >
                      Печать командной схемы
                    </Button>
                  </>
                )}
              </div>
            )}

            {regCompetition?.is_special && (
              <div style={{ marginBottom: 16, padding: 12, border: '1px solid var(--glass-border, #e2e8f0)', borderRadius: 8 }}>
                <h3 style={{ marginBottom: 8 }}>Особая олимпиада</h3>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                  <input
                    type="file"
                    accept=".json,.csv,.xlsx"
                    onChange={(e) => setImportFile(e.target.files?.[0] || null)}
                    style={{ flex: 1, minWidth: 180 }}
                  />
                  <Button
                    variant="secondary"
                    onClick={handleImportParticipants}
                    loading={importing}
                    disabled={!importFile}
                  >
                    Импорт участников
                  </Button>
                  <Button
                    onClick={handleAdmitAllAndDownload}
                    loading={admitAndDownloadLoading}
                    disabled={admitAndDownloadLoading}
                  >
                    Допустить всех + ZIP
                  </Button>
                </div>
                {admitAndDownloadLoading && (
                  <div style={{ marginTop: 8, marginBottom: 12 }}>
                    {blanksTaskProgress && blanksTaskProgress.total > 0 ? (
                      <>
                        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 4 }}>
                          {blanksTaskProgress.stage === 'generating' && `Генерация бланков: участник ${blanksTaskProgress.current} из ${blanksTaskProgress.total}`}
                          {blanksTaskProgress.stage === 'team' && `Командные бланки: ${blanksTaskProgress.current} из ${blanksTaskProgress.total}`}
                          {blanksTaskProgress.stage === 'uploading' && 'Загрузка архива в хранилище...'}
                          {blanksTaskProgress.stage === 'loading' && 'Загрузка данных...'}
                          {!['generating','team','uploading','loading'].includes(blanksTaskProgress.stage) && 'Обработка...'}
                        </div>
                        {blanksTaskProgress.participant && (
                          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {blanksTaskProgress.participant}
                          </div>
                        )}
                        <div style={{ width: '100%', height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' }}>
                          <div
                            style={{
                              width: `${Math.round((blanksTaskProgress.current / blanksTaskProgress.total) * 100)}%`,
                              height: '100%',
                              background: 'linear-gradient(90deg, #3b82f6, #60a5fa)',
                              borderRadius: 3,
                              transition: 'width 0.4s ease',
                            }}
                          />
                        </div>
                        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 3 }}>
                          {Math.round((blanksTaskProgress.current / blanksTaskProgress.total) * 100)}%
                        </div>
                      </>
                    ) : (
                      <>
                        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 6 }}>
                          {blanksTaskState === 'PENDING' || blanksTaskState === 'STARTED'
                            ? 'Задача поставлена в очередь...'
                            : 'Генерация бланков для всех участников... Это может занять несколько минут.'}
                        </div>
                        <div style={{ width: '100%', height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' }}>
                          <div
                            style={{
                              width: '40%',
                              height: '100%',
                              background: 'linear-gradient(90deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%)',
                              borderRadius: 3,
                              animation: 'admitProgress 1.5s ease-in-out infinite',
                            }}
                          />
                        </div>
                        <style>{`
                          @keyframes admitProgress {
                            0% { margin-left: 0%; width: 40%; }
                            50% { margin-left: 60%; width: 40%; }
                            100% { margin-left: 0%; width: 40%; }
                          }
                        `}</style>
                      </>
                    )}
                  </div>
                )}
                <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
                  Форматы импорта: JSON/CSV/XLSX. Архив включает DOCX-бланки, A3-обложки и legacy PDF.
                </p>

                <div style={{ borderTop: '1px solid var(--glass-border, #e2e8f0)', paddingTop: 12 }}>
                  <h4 style={{ marginBottom: 8 }}>Word-шаблоны бланков</h4>
                <p className="text-muted" style={{ fontSize: 12, marginBottom: 8 }}>
                    Токены бланков: {'{{QR_IMAGE}}'}, {'{{TOUR_NUMBER}}'}, {'{{TASK_NUMBER}}'}, {'{{TOUR_MODE}}'}, {'{{TOUR_TASK}}'}.
                </p>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
                    <div>
                      <label className="label" style={{ marginBottom: 4, display: 'block' }}>
                        Шаблон бланка задания
                        <span style={{ fontWeight: 400, fontSize: 11, color: '#6b7280', marginLeft: 8 }}>
                          ({templateInfo.answer_blank?.display_filename ?? 'Нет шаблона'}{templateInfo.answer_blank?.modified_at ? `, обновлен: ${new Date(templateInfo.answer_blank.modified_at).toLocaleString('ru-RU')}` : ''})
                        </span>
                      </label>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        <input
                          type="file"
                          accept=".docx"
                          onChange={(e) => setAnswerTemplateFile(e.target.files?.[0] || null)}
                          style={{ flex: 1, minWidth: 200 }}
                        />
                        <Button
                          variant="secondary"
                          onClick={() => handleDownloadTemplate('answer_blank')}
                          loading={templateDownloadingKind === 'answer_blank'}
                        >
                          Скачать
                        </Button>
                        <Button
                          onClick={() => handleUploadTemplate('answer_blank', answerTemplateFile)}
                          loading={templateUploadingKind === 'answer_blank'}
                          disabled={!answerTemplateFile}
                        >
                          Загрузить
                        </Button>
                        <Button
                          variant="danger"
                          onClick={() => handleDeleteTemplate('answer_blank')}
                          loading={templateDeletingKind === 'answer_blank'}
                        >
                          Сбросить
                        </Button>
                      </div>
                    </div>

                    <div>
                      <label className="label" style={{ marginBottom: 4, display: 'block' }}>
                        Шаблон A3-обложки
                        <span style={{ fontWeight: 400, fontSize: 11, color: '#6b7280', marginLeft: 8 }}>
                          ({templateInfo.a3_cover?.display_filename ?? 'Нет шаблона'}{templateInfo.a3_cover?.modified_at ? `, обновлен: ${new Date(templateInfo.a3_cover.modified_at).toLocaleString('ru-RU')}` : ''})
                        </span>
                      </label>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        <input
                          type="file"
                          accept=".docx"
                          onChange={(e) => setA3TemplateFile(e.target.files?.[0] || null)}
                          style={{ flex: 1, minWidth: 200 }}
                        />
                        <Button
                          variant="secondary"
                          onClick={() => handleDownloadTemplate('a3_cover')}
                          loading={templateDownloadingKind === 'a3_cover'}
                        >
                          Скачать
                        </Button>
                        <Button
                          onClick={() => handleUploadTemplate('a3_cover', a3TemplateFile)}
                          loading={templateUploadingKind === 'a3_cover'}
                          disabled={!a3TemplateFile}
                        >
                          Загрузить
                        </Button>
                        <Button
                          variant="danger"
                          onClick={() => handleDeleteTemplate('a3_cover')}
                          loading={templateDeletingKind === 'a3_cover'}
                        >
                          Сбросить
                        </Button>
                      </div>
                    </div>

                    <div>
                      <label className="label" style={{ marginBottom: 4, display: 'block' }}>
                        Шаблон бейджа
                        <span style={{ fontWeight: 400, fontSize: 11, color: '#6b7280', marginLeft: 8 }}>
                          ({templateInfo.badge?.display_filename ?? 'Нет шаблона'}{templateInfo.badge?.modified_at ? `, обновлен: ${new Date(templateInfo.badge.modified_at).toLocaleString('ru-RU')}` : ''})
                        </span>
                      </label>
                      <p className="text-muted" style={{ fontSize: 12, marginBottom: 6 }}>
                        Токены бейджа: {'{{QR_IMAGE}}'}, {'{{FIRST_NAME}}'}, {'{{LAST_NAME}}'}, {'{{MIDDLE_NAME}}'}, {'{{ROLE}}'}, {'{{PHOTO}}'}.
                      </p>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        <input
                          type="file"
                          accept=".docx"
                          onChange={(e) => setBadgeTemplateFile(e.target.files?.[0] || null)}
                          style={{ flex: 1, minWidth: 200 }}
                        />
                        <Button
                          variant="secondary"
                          onClick={() => handleDownloadTemplate('badge')}
                          loading={templateDownloadingKind === 'badge'}
                        >
                          Скачать
                        </Button>
                        <Button
                          onClick={() => handleUploadTemplate('badge', badgeTemplateFile)}
                          loading={templateUploadingKind === 'badge'}
                          disabled={!badgeTemplateFile}
                        >
                          Загрузить
                        </Button>
                      </div>
                    </div>

                    <div>
                      <label className="label" style={{ marginBottom: 4, display: 'block' }}>Архив фото для бейджей</label>
                      <p className="text-muted" style={{ fontSize: 12, marginBottom: 6 }}>
                        Формат путей в ZIP: {'Город/Учреждение/Фамилия_Имя_Отчество.png'}.
                      </p>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        <input
                          type="file"
                          accept=".zip"
                          onChange={(e) => setBadgePhotosZipFile(e.target.files?.[0] || null)}
                          style={{ flex: 1, minWidth: 200 }}
                        />
                        <Button
                          onClick={handleUploadBadgePhotosZip}
                          loading={badgePhotosUploading}
                          disabled={!badgePhotosZipFile}
                        >
                          Загрузить ZIP
                        </Button>
                      </div>
                    </div>

                    <div>
                      <label className="label" style={{ marginBottom: 4, display: 'block' }}>Шрифты для бейджей (TTF/OTF)</label>
                      <p className="text-muted" style={{ fontSize: 12, marginBottom: 6 }}>
                        Загрузите TTF/OTF-файл или ZIP с несколькими шрифтами. LibreOffice использует их при конвертации DOCX → PDF, чтобы шрифты из шаблона (например, Magistral) отображались корректно.
                      </p>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        <input
                          type="file"
                          accept=".ttf,.otf,.zip"
                          onChange={(e) => setBadgeFontsFile(e.target.files?.[0] || null)}
                          style={{ flex: 1, minWidth: 200 }}
                        />
                        <Button
                          onClick={handleUploadBadgeFonts}
                          loading={badgeFontsUploading}
                          disabled={!badgeFontsFile}
                        >
                          Загрузить шрифты
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Delete confirmation */}
            {deleteConfirmId && (
              <div
                style={{
                  background: '#fef2f2',
                  border: '1px solid #fca5a5',
                  borderRadius: 8,
                  padding: 16,
                  marginBottom: 16,
                }}
              >
                <p style={{ margin: '0 0 12px', fontWeight: 600 }}>
                  Удалить участника «{deleteConfirmName}» из олимпиады?
                </p>
                <p style={{ margin: '0 0 12px', fontSize: 13, color: '#555' }}>
                  Все связанные данные (бланки, баллы) будут удалены безвозвратно.
                </p>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button
                    variant="secondary"
                    onClick={() => { setDeleteConfirmId(null); setDeleteConfirmName(''); }}
                  >
                    Отмена
                  </Button>
                  <Button
                    onClick={handleDeleteRegistration}
                    loading={deletingReg}
                    style={{ background: '#dc2626', borderColor: '#dc2626', color: 'white' }}
                  >
                    Удалить
                  </Button>
                </div>
              </div>
            )}

            {/* Replace participant panel */}
            {replaceRegId && (
              <div
                style={{
                  background: '#eff6ff',
                  border: '1px solid #93c5fd',
                  borderRadius: 8,
                  padding: 16,
                  marginBottom: 16,
                }}
              >
                <p style={{ margin: '0 0 8px', fontWeight: 600 }}>
                  Выберите нового участника для замены:
                </p>
                <input
                  type="text"
                  value={replaceSearch}
                  onChange={(e) => setReplaceSearch(e.target.value)}
                  placeholder="Поиск по ФИО или школе..."
                  style={{
                    width: '100%',
                    padding: '6px 10px',
                    borderRadius: 6,
                    border: '1px solid #d1d5db',
                    fontSize: 13,
                    marginBottom: 8,
                    boxSizing: 'border-box',
                  }}
                />
                <div style={{ maxHeight: 160, overflowY: 'auto', border: '1px solid #e5e7eb', borderRadius: 6 }}>
                  {participants
                    .filter((p) => {
                      const q = replaceSearch.toLowerCase();
                      return p.full_name.toLowerCase().includes(q) || p.school.toLowerCase().includes(q);
                    })
                    .slice(0, 15)
                    .map((p) => (
                      <div
                        key={p.id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '6px 10px',
                          borderBottom: '1px solid #f3f4f6',
                          fontSize: 13,
                        }}
                      >
                        <span>
                          <strong>{p.full_name}</strong>
                          <span style={{ marginLeft: 8, color: '#6b7280' }}>{p.school}</span>
                        </span>
                        <Button
                          className="btn-sm"
                          onClick={() => handleReplaceRegistration(p.id)}
                          loading={replacing}
                        >
                          Заменить
                        </Button>
                      </div>
                    ))}
                  {participants.filter((p) => {
                    const q = replaceSearch.toLowerCase();
                    return p.full_name.toLowerCase().includes(q) || p.school.toLowerCase().includes(q);
                  }).length === 0 && (
                    <p style={{ padding: 10, color: '#9ca3af', fontSize: 13, margin: 0 }}>Не найдено</p>
                  )}
                </div>
                <Button
                  variant="secondary"
                  onClick={() => { setReplaceRegId(null); setReplaceSearch(''); }}
                  style={{ marginTop: 8 }}
                >
                  Отмена
                </Button>
              </div>
            )}

            {/* Replace result banner */}
            {replaceResult && (
              <div
                style={{
                  background: '#f0fdf4',
                  border: '1px solid #86efac',
                  borderRadius: 8,
                  padding: 14,
                  marginBottom: 16,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, color: '#15803d', marginBottom: 4 }}>
                    Участник заменён
                  </div>
                  {replaceResult.seat_transferred ? (
                    <div style={{ fontSize: 13, color: '#166534' }}>
                      Место перенесено: <strong>{replaceResult.room_name}</strong>, место <strong>{replaceResult.seat_number}</strong>, вариант <strong>{replaceResult.variant_number}</strong>
                    </div>
                  ) : (
                    <div style={{ fontSize: 13, color: '#166534' }}>
                      Место будет назначено при допуске (↓)
                    </div>
                  )}
                  {replaceResult.warning && (
                    <div style={{ fontSize: 12, color: '#b45309', marginTop: 4 }}>
                      ⚠ {replaceResult.warning}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <Button
                    className="btn-sm"
                    onClick={() => handleAdmitAndDownload(replaceResult.new_registration_id, '')}
                    loading={downloadingRegId === replaceResult.new_registration_id}
                  >
                    ↓ Скачать бейдж и бланки
                  </Button>
                  <button
                    onClick={() => setReplaceResult(null)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', fontSize: 16 }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}

            {/* Edit participant fields panel */}
            {editParticipantId && (
              <div style={{ background: '#fafaf5', border: '1px solid #d1d5db', borderRadius: 8, padding: 16, marginBottom: 16 }}>
                <p style={{ margin: '0 0 8px', fontWeight: 600 }}>Редактировать поля участника:</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <label style={{ fontSize: 13 }}>Город / Филиал</label>
                  <input
                    type="text"
                    value={editInstLocation}
                    onChange={(e) => setEditInstLocation(e.target.value)}
                    placeholder="Например: Москва"
                    style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
                  />
                  <label style={{ fontSize: 13 }}>Учреждение (поиск по названию)</label>
                  <input
                    type="text"
                    value={editInstSearch}
                    onChange={(e) => { setEditInstSearch(e.target.value); searchInstitutions(e.target.value); }}
                    placeholder="Начните вводить название..."
                    style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
                  />
                  {instSearchResults.length > 0 && (
                    <div style={{ border: '1px solid #e5e7eb', borderRadius: 6, maxHeight: 120, overflowY: 'auto' }}>
                      {instSearchResults.map((inst) => (
                        <div
                          key={inst.id}
                          onClick={() => { setEditInstId(inst.id); setEditInstSearch(inst.name); setInstSearchResults([]); }}
                          style={{ padding: '6px 10px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid #f3f4f6', background: editInstId === inst.id ? '#eff6ff' : 'white' }}
                        >
                          {inst.name}{inst.city ? ` (${inst.city})` : ''}
                        </div>
                      ))}
                    </div>
                  )}
                  {editInstId && (
                    <div style={{ fontSize: 12, color: '#6b7280' }}>
                      Выбрано учреждение (ID: {editInstId.slice(0, 8)}…)
                      <button onClick={() => { setEditInstId(''); setEditInstSearch(''); }} style={{ marginLeft: 6, background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', fontSize: 12 }}>✕</button>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                  <Button variant="secondary" onClick={() => { setEditParticipantId(null); setEditInstId(''); setEditInstSearch(''); setEditInstLocation(''); }}>Отмена</Button>
                  <Button onClick={handleSaveParticipantFields} loading={savingParticipant}>Сохранить</Button>
                </div>
              </div>
            )}

            {/* Photo upload panel */}
            {photoUploadRegId && (
              <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: 16, marginBottom: 16 }}>
                <p style={{ margin: '0 0 8px', fontWeight: 600 }}>Загрузить фото для бейджа:</p>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => setPhotoFile(e.target.files?.[0] || null)}
                  style={{ fontSize: 13, marginBottom: 8, display: 'block' }}
                />
                {photoFile && <p style={{ margin: '0 0 8px', fontSize: 12, color: '#555' }}>{photoFile.name}</p>}
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button variant="secondary" onClick={() => { setPhotoUploadRegId(null); setPhotoUploadParticipantId(null); setPhotoFile(null); }}>Отмена</Button>
                  <Button onClick={handleUploadParticipantPhoto} loading={uploadingPhoto} disabled={!photoFile}>Загрузить</Button>
                </div>
              </div>
            )}

            {/* Registrations table */}
            {regItems.length > 0 ? (
              <div style={{ maxHeight: 340, overflowY: 'auto', marginBottom: 24 }}>
                <table className="table" style={{ fontSize: 13 }}>
                  <thead>
                    <tr>
                      <th>ФИО</th>
                      <th>Учебное заведение</th>
                      <th>Город/филиал</th>
                      <th>Капитан</th>
                      <th>Учреждение</th>
                      <th>Статус</th>
                      <th>Место</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {regItems.map((item) => (
                      <tr
                        key={item.registration_id}
                        style={
                          item.registration_id === lastAddedRegId ||
                          item.registration_id === replaceResult?.new_registration_id
                            ? { background: '#f0fdf4' }
                            : undefined
                        }
                      >
                        <td>{item.participant_name}</td>
                        <td>{item.participant_school}</td>
                        <td>{item.participant_institution_location || '—'}</td>
                        <td>{item.participant_is_captain ? 'Да' : 'Нет'}</td>
                        <td>{item.institution_name || '—'}</td>
                        <td>{getRegStatusLabel(item.status)}</td>
                        <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                          {item.seat_room_name
                            ? `${item.seat_room_name} / ${item.seat_number}`
                            : '—'}
                        </td>
                        <td style={{ whiteSpace: 'nowrap' }}>
                          <Tooltip text="Допустить и скачать бланки + бейдж">
                            <button
                              onClick={() => handleAdmitAndDownload(item.registration_id, item.participant_name)}
                              disabled={downloadingRegId === item.registration_id}
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: downloadingRegId === item.registration_id ? 'default' : 'pointer',
                                color: '#16a34a',
                                fontSize: 15,
                                padding: '2px 6px',
                                marginRight: 2,
                                opacity: downloadingRegId === item.registration_id ? 0.5 : 1,
                              }}
                            >
                              {downloadingRegId === item.registration_id ? '…' : '↓'}
                            </button>
                          </Tooltip>
                          <Tooltip text="Заменить участника">
                            <button
                              onClick={() => { setReplaceRegId(item.registration_id); setReplaceSearch(''); setDeleteConfirmId(null); }}
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                color: '#2563eb',
                                fontSize: 15,
                                padding: '2px 6px',
                                marginRight: 2,
                              }}
                            >
                              ⇄
                            </button>
                          </Tooltip>
                          <Tooltip text="Удалить регистрацию">
                            <button
                              onClick={() => {
                                setDeleteConfirmId(item.registration_id);
                                setDeleteConfirmName(item.participant_name);
                                setReplaceRegId(null);
                              }}
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                color: '#dc2626',
                                fontSize: 15,
                                padding: '2px 6px',
                              }}
                            >
                              ✕
                            </button>
                          </Tooltip>
                          <Tooltip text="Редактировать город/учреждение">
                            <button
                              onClick={() => {
                                setEditParticipantId(item.participant_id);
                                setEditInstLocation(item.participant_institution_location || '');
                                setEditInstId('');
                                setEditInstSearch(item.institution_name || '');
                                setInstSearchResults([]);
                                setDeleteConfirmId(null);
                                setReplaceRegId(null);
                                setPhotoUploadRegId(null);
                              }}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7c3aed', fontSize: 15, padding: '2px 6px' }}
                            >
                              ✎
                            </button>
                          </Tooltip>
                          <Tooltip text="Загрузить фото для бейджа">
                            <button
                              onClick={() => {
                                setPhotoUploadRegId(item.registration_id);
                                setPhotoUploadParticipantId(item.participant_id);
                                setPhotoFile(null);
                                setEditParticipantId(null);
                                setDeleteConfirmId(null);
                                setReplaceRegId(null);
                              }}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#0891b2', fontSize: 15, padding: '2px 6px' }}
                            >
                              ☷
                            </button>
                          </Tooltip>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted" style={{ marginBottom: 16 }}>Регистраций пока нет.</p>
            )}

            {/* Register new participant */}
            <h3 style={{ marginBottom: 8 }}>Зарегистрировать участника</h3>
            <Input
              label="Поиск участника"
              value={participantSearch}
              onChange={(e) => setParticipantSearch(e.target.value)}
              placeholder="Введите ФИО или школу..."
            />
            {participants.length > 0 && (
              <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid var(--glass-border, #e2e8f0)', borderRadius: 8, marginTop: 4 }}>
                {filteredParticipants.length === 0 ? (
                  <p className="text-muted" style={{ padding: 12 }}>Не найдено подходящих участников.</p>
                ) : (
                  filteredParticipants.slice(0, 20).map((p) => (
                    <div
                      key={p.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '8px 12px',
                        borderBottom: '1px solid var(--glass-border, #e2e8f0)',
                      }}
                    >
                      <span>
                        <strong>{p.full_name}</strong>
                        <span className="text-muted" style={{ marginLeft: 8, fontSize: 12 }}>
                          {p.school}
                        </span>
                      </span>
                      <Button
                        className="btn-sm"
                        onClick={() => handleAdminRegister(p.id)}
                        loading={registering}
                      >
                        Зарегистрировать
                      </Button>
                    </div>
                  ))
                )}
              </div>
            )}
            {participants.length === 0 && !regLoading && (
              <p className="text-muted" style={{ marginTop: 8, fontSize: 13 }}>
                Не удалось загрузить список участников.
              </p>
            )}
          </div>
        )}
      </Modal>
    </Layout>
  );
};

export default CompetitionsAdminPage;
