export interface CameraStatus {
  id: string;
  name: string;
  serial: string;
  location: string;
  online: boolean;
  battery_percent: number | null;
  sd_remaining_minutes: number | null;
  sd_remaining_gb: number | null;
  latency_ms: number | null;
  overheating: boolean | null;
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

export interface RecordingConfig {
  resolution: "1080P" | "4K" | "5.3K_8_7" | null;
  fps: 24 | 25 | 30 | 50 | 60 | null;
  lens: "wide" | "linear" | "hyperview" | null;
  bit_depth: 8 | 10 | null;
  color: "natural" | "flat" | "vibrant" | null;
  high_bitrate: boolean | null;
  stabilization: "off" | "high" | "auto_boost" | null;
  hindsight: boolean | null;
  shutter_speed: 0 | 120 | 240 | 480 | null;
  iso: 100 | 200 | 400 | 800 | 1600 | null;
}

export interface DiscoverCameraInput {
  profile_label: string;
}

export interface DiscoveryResponse {
  discovered_count: number;
  cameras: CameraStatus[];
}

export type TaskEventType = "start" | "end";

export interface TaskEvent {
  id: string;
  task_id: string;
  task_name: string;
  event: TaskEventType;
  utc_at: string;
  created_at: string;
  countdown_seconds: number;
}

export interface TaskEventListResponse {
  server_utc: string;
  events: TaskEvent[];
}

export interface CreateTaskEventInput {
  task_id?: string;
  task_name: string;
  event: TaskEventType;
  countdown_seconds: number;
}

export interface CollectedFile {
  camera_id: string;
  camera_name: string;
  remote_path: string;
  local_path: string;
  size_bytes: number;
}

export interface CaptureSession {
  id: string;
  status: "recording" | "collecting" | "collected" | "processing" | "complete" | "partial" | "collection_failed" | "process_failed" | "cancelled";
  started_at: string;
  stopped_at: string | null;
  camera_ids: string[];
  camera_names: Record<string, string>;
  baseline_media: Record<string, string[]>;
  files_total: number;
  files_completed: number;
  bytes_total: number;
  bytes_downloaded: number;
  collected_files: CollectedFile[];
  ego_files: Array<{
    stream: "left" | "right";
    local_path: string;
    original_name: string;
    size_bytes: number;
  }>;
  timesync_ready: boolean;
  task_count: number;
  clips_total: number;
  clips_completed: number;
  grids_total: number;
  grids_completed: number;
  errors: string[];
}

export interface SyncValidationCameraResult {
  camera_id: string;
  camera_name: string;
  decoded_frames: number;
  compared_frames: number;
  offset_frames: number | null;
  jitter_frames: number | null;
}

export interface SyncValidationReport {
  session_id: string;
  reference_camera_id: string;
  reference_camera_name: string;
  target_fps: number;
  results: SyncValidationCameraResult[];
}
