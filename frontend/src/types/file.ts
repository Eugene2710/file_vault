export interface File {
  id: string;
  original_filename: string;
  file_type: string;
  size: number;
  uploaded_at: string;
  file: string;
  user_id: string;
  file_hash: string;
  reference_count: number;
  is_reference: boolean;
  original_file: string | null;
}

export interface StorageStats {
  user_id: string;
  total_storage_used: number;
  original_storage_used: number;
  storage_savings: number;
  savings_percentage: number;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
