export interface UserSummary {
  id: number;
  name: string;
  is_admin: boolean;
  is_active: boolean;
}

export interface Me {
  id: number;
  name: string;
  email: string;
  is_admin: boolean;
  must_change_password: boolean;
}

export interface Group {
  id: number;
  name: string;
  manager_id: number;
  default_driver_id: number | null;
  is_archived: boolean;
}

export interface Membership {
  id: number;
  group_id: number;
  user_id: number;
  status: string;
}

export interface Invitation {
  id: number;
  group_id: number;
  group_name: string;
  invited_by_id: number;
}

export interface RecurringParticipationSummary {
  id: number;
  recurring_model_id: number;
  group_id: number;
  model_name: string;
}

export interface VehicleEnergy {
  energy_type: string;
  consumption_per_100km: number;
}

export interface Vehicle {
  id: number;
  owner_id: number;
  brand: string;
  model: string;
  seats: number;
  energies: VehicleEnergy[];
}

export interface Trip {
  id: number;
  group_id: number;
  recurring_model_id: number | null;
  date: string;
  time_of_day: string;
  origin: string;
  destination: string;
  driver_id: number;
  vehicle_id: number | null;
  status: "planned" | "completed" | "cancelled";
}

export interface TripParticipation {
  id: number;
  trip_id: number;
  user_id: number;
  role: "driver" | "passenger";
  status: "pending" | "accepted" | "refused" | "waitlisted";
  boarding_point: string | null;
}

export interface TripSegment {
  id: number;
  sequence: number;
  distance_km: number;
  is_detour: boolean;
  detour_for_user_id: number | null;
  occupant_ids: number[];
}

export interface RecurringModel {
  id: number;
  group_id: number;
  name: string;
  origin: string;
  destination: string;
  weekdays: number[];
  time_of_day: string;
  is_paused: boolean;
}

export interface LedgerIssue {
  code: string;
  message: string;
}

export interface Transfer {
  debtor_id: number;
  creditor_id: number;
  amount: string;
}

export interface Ledger {
  group_id: number;
  year: number;
  month: number;
  status: "open" | "closed";
  balances: Record<string, string>;
  transfers: Transfer[];
  concerned_user_ids: number[];
  issues: LedgerIssue[];
}

export interface Reimbursement {
  id: number;
  group_id: number;
  year: number;
  month: number;
  payer_id: number;
  payee_id: number;
  amount: number;
  status: "declared" | "confirmed";
}
