export type HandoffStatus =
  | 'connecting'
  | 'active'
  | 'waiting_agent'
  | 'revoked'
  | 'resuming'
  | 'still_blocked'
  | 'completed'
  | 'expired'
  | 'error';

export interface HandoffSession {
  handoff_session_id?: string;
  sync_job_id?: string;
  data_source_id?: string;
  profile_key?: string;
  reason?: string;
  agent_id?: string;
  status?: string;
  expires_at?: string;
  controller_id?: string;
}

export interface HandoffFrame {
  frame_id: number;
  mime: string;
  width: number;
  height: number;
  data: string;
}

export interface HandoffInputEvent {
  kind:
    | 'mouse_down'
    | 'mouse_move'
    | 'mouse_up'
    | 'click'
    | 'wheel'
    | 'key_down'
    | 'key_up'
    | 'text';
  x?: number;
  y?: number;
  button?: 'left' | 'middle' | 'right';
  delta_x?: number;
  delta_y?: number;
  key?: string;
  text?: string;
}
