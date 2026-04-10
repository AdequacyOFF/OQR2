import { create } from 'zustand';

export interface CompetitionOption {
  id: string;
  name: string;
}

interface CompetitionState {
  selectedCompetitionId: string | null;
  selectedCompetitionName: string | null;
  setSelectedCompetition: (id: string, name: string) => void;
  clearSelectedCompetition: () => void;
  loadFromStorage: () => void;
}

const STORAGE_KEY_ID = 'selected_competition_id';
const STORAGE_KEY_NAME = 'selected_competition_name';

const useCompetitionStore = create<CompetitionState>((set) => ({
  selectedCompetitionId: null,
  selectedCompetitionName: null,

  setSelectedCompetition: (id: string, name: string) => {
    localStorage.setItem(STORAGE_KEY_ID, id);
    localStorage.setItem(STORAGE_KEY_NAME, name);
    set({ selectedCompetitionId: id, selectedCompetitionName: name });
  },

  clearSelectedCompetition: () => {
    localStorage.removeItem(STORAGE_KEY_ID);
    localStorage.removeItem(STORAGE_KEY_NAME);
    set({ selectedCompetitionId: null, selectedCompetitionName: null });
  },

  loadFromStorage: () => {
    const id = localStorage.getItem(STORAGE_KEY_ID);
    const name = localStorage.getItem(STORAGE_KEY_NAME);
    if (id && name) {
      set({ selectedCompetitionId: id, selectedCompetitionName: name });
    }
  },
}));

export default useCompetitionStore;
