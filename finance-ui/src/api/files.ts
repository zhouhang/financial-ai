/**
 * File upload and preview API
 */
import apiClient from './client';

export interface FileUploadResponse {
  filename: string;
  path: string;
  size: number;
  sheets: string[];
}

export interface FileUploadListResponse {
  uploaded_files: FileUploadResponse[];
}

export interface FilePreviewResponse {
  filename: string;
  sheets: {
    name: string;
    headers: string[];
    rows: string[][];
    total_rows: number;
    total_columns: number;
  }[];
}

export const fileApi = {
  /**
   * Upload files
   */
  uploadFiles: async (files: File[]): Promise<FileUploadListResponse> => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    const response = await apiClient.post<FileUploadListResponse>(
      '/files/upload',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },

  /**
   * Get file preview
   */
  getFilePreview: async (filePath: string, maxRows: number = 100): Promise<FilePreviewResponse> => {
    const response = await apiClient.get<FilePreviewResponse>('/files/preview', {
      params: { file_path: filePath, max_rows: maxRows },
    });
    return response.data;
  },
};
