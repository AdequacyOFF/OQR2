export type UserRole = 'participant' | 'admitter' | 'scanner' | 'admin' | 'invigilator';

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  role: UserRole;
}

export interface UserInfo {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
}

export interface ParticipantProfile {
  id: string;
  user_id: string;
  full_name: string;
  school: string;
  grade: number | null;
  institution_id: string | null;
  institution_location: string | null;
  is_captain: boolean;
  dob: string | null;
  created_at: string;
  updated_at: string;
}

export interface Competition {
  id: string;
  name: string;
  date: string;
  registration_start: string;
  registration_end: string;
  variants_count: number;
  max_score: number;
  is_special: boolean;
  special_tours_count: number | null;
  special_tour_modes: string[] | null;
  special_settings: Record<string, unknown> | null;
  status: string;
  created_by: string;
  created_at: string;
}

export interface Registration {
  id: string;
  participant_id: string;
  competition_id: string;
  status: string;
  created_at: string;
  entry_token?: string;
  attempt_id?: string;
  variant_number?: number;
  final_score?: number | null;
}

export interface ScanItem {
  id: string;
  attempt_id: string | null;
  answer_sheet_id: string | null;
  file_path: string;
  ocr_score: number | null;
  ocr_confidence: number | null;
  ocr_raw_text: string | null;
  verified_by: string | null;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
}

export interface ResultEntry {
  rank: number;
  participant_name: string;
  school: string;
  grade: number | null;
  score: number;
  max_score: number;
}

export interface AuditLogEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  user_id: string | null;
  ip_address: string | null;
  details: Record<string, unknown>;
  timestamp: string;
}

export interface Institution {
  id: string;
  name: string;
  short_name: string | null;
  city: string | null;
}

export interface Room {
  id: string;
  competition_id: string;
  name: string;
  capacity: number;
}

export interface SeatAssignment {
  id: string;
  registration_id: string;
  room_id: string;
  seat_number: number;
  variant_number: number;
}

export interface Document {
  id: string;
  file_path: string;
  file_type: string;
  created_at: string;
}

export interface ParticipantEvent {
  id: string;
  attempt_id: string;
  event_type: string;
  timestamp: string;
  recorded_by: string;
}

export interface AnswerSheet {
  id: string;
  attempt_id: string;
  sheet_token_hash: string;
  kind: 'primary' | 'extra';
  pdf_file_path: string | null;
  created_at: string;
}

export interface AdminRegistrationItem {
  registration_id: string;
  participant_id: string;
  participant_name: string;
  participant_school: string;
  participant_institution_location: string | null;
  participant_is_captain: boolean;
  institution_name: string | null;
  entry_token: string | null;
  status: string;
  seat_room_name: string | null;
  seat_number: number | null;
  variant_number: number | null;
}

export interface ReplaceParticipantResponse {
  new_registration_id: string;
  entry_token: string;
  seat_transferred: boolean;
  room_name: string | null;
  seat_number: number | null;
  variant_number: number | null;
  warning: string | null;
}

export interface ScoringProgressTour {
  tour_number: number;
  task_scores: Record<string, number> | null;
  tour_total: number | null;
}

export interface ScoringProgressItem {
  registration_id: string;
  participant_id: string;
  participant_name: string;
  participant_school: string;
  variant_number: number | null;
  attempt_id: string | null;
  attempt_status: string | null;
  tours: ScoringProgressTour[];
  score_total: number | null;
}

export interface TourTimeItem {
  tour_number: number;
  started_at: string | null;
  finished_at: string | null;
  duration_minutes: number | null;
}

export interface ScoringProgressResponse {
  competition_id: string;
  competition_name: string;
  is_special: boolean;
  tours_count: number;
  items: ScoringProgressItem[];
  total: number;
  tour_times: TourTimeItem[];
}

