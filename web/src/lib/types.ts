export type RenderStatus = "queued" | "processing" | "done" | "error";

export type Profile = {
  id: string;
  email: string | null;
  full_name: string | null;
  plan: string;
  monthly_render_limit: number;
};

export type Project = {
  id: string;
  user_id: string;
  name: string;
  reference_path: string | null;
  reference_analysis: ReferenceAnalysis | null;
  brand_board_id: string | null;
  created_at: string;
};

export type PlatformCaption = {
  caption?: string;
  title?: string;
  description?: string;
  hashtags?: string[];
  mentions?: string[];
};

export type SocialCaptions = {
  tiktok?: PlatformCaption;
  youtube?: PlatformCaption;
  instagram?: PlatformCaption;
};

export type RenderJob = {
  id: string;
  user_id: string;
  project_id: string | null;
  recording_path: string;
  reference_path: string | null;
  status: RenderStatus;
  progress: number;
  output_path: string | null;
  result: RenderResult | null;
  social_captions: SocialCaptions | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type ReferenceAnalysis = {
  media: { width: number; height: number; duration: number; has_audio: boolean };
  color_profile: { palette: { color: { hex: string }; weight: number }[]; primary: string | null };
  transitions: { timestamp: number; type: string }[];
  text_overlays: { start: number; end: number; zone: string }[];
  pacing: { cut_density_per_min: number; words_per_minute: number };
};

export type RenderResult = {
  width: number;
  height: number;
  fps: number;
  duration: number;
  encoder: string;
  used_hardware: boolean;
};

export type BrandBoard = {
  id: string;
  name: string;
  caption_primary: string | null;
  caption_outline: string | null;
};
