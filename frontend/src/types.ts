// Shared types and helpers for assessment flow

export type Side = 'front' | 'rear' | 'left' | 'right';

export const ALL_SIDES: Side[] = ['front', 'rear', 'left', 'right'];

export const SIDE_LABELS: Record<Side, string> = {
  front: 'Front',
  rear: 'Rear',
  left: 'Left',
  right: 'Right',
};

export type AssessmentStatus =
  | 'pending'
  | 'in_progress'
  | 'complete'
  | 'failed'
  | 'not_found';

export interface SideAssessment {
  pickup_image: string;
  return_image: string;
  annotated_return_image?: string;
  // Flexible container for backend metadata
  result?: {
    predictions?: any[];
    [key: string]: unknown;
  };
}

export type AssessmentResultMap = Partial<Record<Side, SideAssessment>> & {
  // allow unknown / future sides from backend as well
  [side: string]: SideAssessment | undefined;
};

export interface AssessmentResponse {
  status: AssessmentStatus;
  created_at: string | null;
  completed_at: string | null;
  results: AssessmentResultMap | null;
  summary: string | null;
  error: string | null;
}

export interface UploadResponse {
    upload_id: string;
}

export interface AssessmentDisplayResult {
  pickupUrl: string;
  resultUrl: string; // annotated_return_image if present, else return_image
}

export type ResultsState = Partial<Record<Side, AssessmentDisplayResult>>;