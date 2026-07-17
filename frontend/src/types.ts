export interface CameraStatus {
  id: string;
  name: string;
  serial: string;
  location: string;
  online: boolean;
  battery_percent: number;
  sd_remaining_minutes: number;
  temperature_c: number;
  recording: boolean;
  recording_seconds: number;
  mode: string;
  timecode_synced_at: string | null;
  last_seen_at: string;
}

export interface CommandResult {
  camera_id: string;
  success: boolean;
  message: string;
  status: CameraStatus | null;
}

export interface BatchCommandResponse {
  success_count: number;
  failure_count: number;
  results: CommandResult[];
}

