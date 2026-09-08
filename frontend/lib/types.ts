export type Aspect = "clear" | "caution" | "danger";

export interface Environment {
  id: string;
  project_id: string;
  slug: string;
  name: string;
  aspect: Aspect;
  rank: number;
  variable_count: number;
  updated_at: string;
}

export interface Project {
  id: string;
  slug: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  environments: Environment[];
}

export interface Variable {
  id: string;
  environment_id: string;
  key: string;
  value: string;
  revealed: boolean;
  is_secret: boolean;
  note: string;
  version: number;
  length: number;
  created_at: string;
  updated_at: string;
}

export interface Revision {
  id: string;
  key: string;
  action: "created" | "updated" | "deleted" | "restored";
  actor: string;
  version: number;
  created_at: string;
}

export interface ActivityEvent {
  id: string;
  project_id: string | null;
  environment_id: string | null;
  actor: string;
  action: string;
  summary: string;
  alert: boolean;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface AccessToken {
  id: string;
  environment_id: string;
  name: string;
  prefix: string;
  last_used_at: string | null;
  pull_count: number;
  revoked_at: string | null;
  created_at: string;
  last_ip: string;
  last_version: string;
}

export interface Sighting {
  ip: string;
  user_agent: string;
  pull_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

/** A token, plus what whatever holds it is actually doing. */
export interface Consumer extends AccessToken {
  up_to_date: boolean;
  reading_now: boolean;
  reads_in_a_minute: number;
  sightings: Sighting[];
}

export interface IssuedToken extends AccessToken {
  token: string;
}

export interface EnvironmentStatus {
  environment_id: string;
  version: string;
  variable_count: number;
  connected_apps: number;
  /** Tokens that have read in the last ten minutes - things actually running. */
  consumers: number;
  up_to_date: number;
  /** Named consumers still on an older value. */
  waiting: string[];
}

export interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
  keys: string[];
}
