import axios from 'axios';

import {
  File as FileType,
  StorageStats,
  PaginatedResponse,
} from '../types/file';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

export const fileService = {
  async uploadFile(file: File, userId: string): Promise<FileType> {
    if (!userId || userId.trim() === '') {
      throw new Error('User ID is required');
    }

    const formData = new FormData();
    formData.append('file', file);

    console.log('Uploading to:', `${API_URL}/files/`);
    console.log('User ID:', userId.trim());
    console.log('File:', file.name, file.size, 'bytes');

    try {
      const response = await axios.post(`${API_URL}/files/`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          UserId: userId.trim(),
        },
        timeout: 30000, // 30 second timeout
      });
      console.log('Upload successful:', response.data);
      return response.data;
    } catch (error: any) {
      console.error('File upload error details:', {
        message: error.message,
        code: error.code,
        response: error.response?.data,
        status: error.response?.status,
        url: error.config?.url,
      });
      throw error;
    }
  },

  async getFiles(
    userId: string,
    filters?: {
      search?: string;
      file_type?: string;
      min_size?: number;
      max_size?: number;
      start_date?: string;
      end_date?: string;
      page?: number;
    }
  ): Promise<PaginatedResponse<FileType>> {
    if (!userId || userId.trim() === '') {
      return { count: 0, next: null, previous: null, results: [] };
    }

    try {
      const params = new URLSearchParams();

      if (filters) {
        if (filters.search) params.append('search', filters.search);
        if (filters.file_type) params.append('file_type', filters.file_type);
        if (filters.min_size !== undefined)
          params.append('min_size', filters.min_size.toString());
        if (filters.max_size !== undefined)
          params.append('max_size', filters.max_size.toString());
        if (filters.start_date) params.append('start_date', filters.start_date);
        if (filters.end_date) params.append('end_date', filters.end_date);
        if (filters.page) params.append('page', filters.page.toString());
      }

      const url = `${API_URL}/files/${params.toString() ? '?' + params.toString() : ''}`;

      const response = await axios.get(url, {
        headers: {
          UserId: userId.trim(),
        },
      });

      // Handle both paginated and non-paginated responses
      if (response.data.results) {
        return response.data;
      } else {
        // Legacy response format - convert to paginated format
        return {
          count: response.data.length,
          next: null,
          previous: null,
          results: response.data,
        };
      }
    } catch (error: any) {
      console.error('File list error:', error);
      throw error;
    }
  },

  async deleteFile(id: string, userId: string): Promise<void> {
    if (!userId || userId.trim() === '') {
      throw new Error('User ID is required');
    }

    try {
      await axios.delete(`${API_URL}/files/${id}/`, {
        headers: {
          UserId: userId.trim(),
        },
      });
    } catch (error: any) {
      console.error('File delete error:', error);
      throw error;
    }
  },

  async getFile(fileId: string, userId: string): Promise<FileType> {
    if (!userId || userId.trim() === '') {
      throw new Error('User ID is required');
    }

    try {
      const response = await axios.get(`${API_URL}/files/${fileId}/`, {
        headers: {
          UserId: userId.trim(),
        },
      });
      return response.data;
    } catch (error: any) {
      console.error('File get error:', error);
      throw error;
    }
  },

  async downloadFile(
    fileId: string,
    userId: string,
    filename: string
  ): Promise<void> {
    if (!userId || userId.trim() === '') {
      throw new Error('User ID is required');
    }

    try {
      const response = await axios.get(`${API_URL}/files/${fileId}/download/`, {
        headers: {
          UserId: userId.trim(),
        },
        responseType: 'blob',
      });

      // Create a blob URL and trigger download
      const blob = new Blob([response.data]);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download error:', error);
      throw new Error('Failed to download file');
    }
  },

  async getStorageStats(userId: string): Promise<StorageStats> {
    if (!userId || userId.trim() === '') {
      throw new Error('User ID is required');
    }

    try {
      const response = await axios.get(`${API_URL}/files/storage_stats/`, {
        headers: {
          UserId: userId.trim(),
        },
      });
      return response.data;
    } catch (error: any) {
      console.error('Storage stats error:', error);
      throw error;
    }
  },

  async getFileTypes(userId: string): Promise<string[]> {
    if (!userId || userId.trim() === '') {
      return [];
    }

    try {
      const response = await axios.get(`${API_URL}/files/file_types/`, {
        headers: {
          UserId: userId.trim(),
        },
      });
      return response.data;
    } catch (error: any) {
      console.error('File types error:', error);
      throw error;
    }
  },
};
