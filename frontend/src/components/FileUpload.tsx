import { CloudArrowUpIcon, CheckCircleIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';

import { fileService } from '../services/fileService';
import { File as FileType } from '../types/file';

interface FileUploadProps {
  onUploadSuccess: () => void;
  userId: string;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  onUploadSuccess,
  userId,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<FileType | null>(null);
  const queryClient = useQueryClient();

  const uploadMutation = useMutation({
    mutationFn: (file: File) => fileService.uploadFile(file, userId),
    onSuccess: (data: FileType) => {
      // Invalidate and refetch files query
      queryClient.invalidateQueries({ queryKey: ['files'] });
      // Refresh all expanded file details
      queryClient.invalidateQueries({ queryKey: ['file'] });
      // Refresh storage stats
      queryClient.invalidateQueries({ queryKey: ['storageStats'] });
      setSelectedFile(null);
      setUploadedFile(data);
      onUploadSuccess();
    },
    onError: (error: any) => {
      console.error('Upload error:', error);
      
      // Build detailed error message for UI
      let errorMessage = 'Upload failed:\n\n';
      
      if (error.response) {
        // Server responded with error status
        errorMessage += `Status: ${error.response.status}\n`;
        errorMessage += `URL: ${error.config?.url}\n`;
        if (error.response.data?.error) {
          errorMessage += `Server Error: ${error.response.data.error}\n`;
        } else if (error.response.data) {
          errorMessage += `Server Response: ${JSON.stringify(error.response.data, null, 2)}\n`;
        }
      } else if (error.request) {
        // Request was made but no response received (network error)
        errorMessage += `Network Error: No response from server\n`;
        errorMessage += `URL: ${error.config?.url}\n`;
        errorMessage += `Timeout: ${error.config?.timeout}ms\n`;
        if (error.code) {
          errorMessage += `Error Code: ${error.code}\n`;
        }
        errorMessage += '\nPossible causes:\n';
        errorMessage += '• Backend server is not running\n';
        errorMessage += '• Wrong API URL in environment\n';
        errorMessage += '• Network connectivity issues\n';
        errorMessage += '• Firewall blocking the request\n';
      } else {
        // Something else happened
        errorMessage += `Error: ${error.message}\n`;
      }
      
      if (error.message) {
        errorMessage += `\nOriginal Error: ${error.message}`;
      }
      
      setError(errorMessage);
    },
  });

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files[0]) {
      setSelectedFile(event.target.files[0]);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please select a file');
      return;
    }

    if (!userId || userId.trim() === '') {
      setError('Please enter a User ID');
      return;
    }

    try {
      setError(null);
      await uploadMutation.mutateAsync(selectedFile);
    } catch (err) {
      // Error handling is done in onError callback
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center mb-4">
        <CloudArrowUpIcon className="h-6 w-6 text-primary-600 mr-2" />
        <h2 className="text-xl font-semibold text-gray-900">Upload File</h2>
      </div>
      <div className="mt-4 space-y-4">
        <div className="flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-lg">
          <div className="space-y-1 text-center">
            <div className="flex text-sm text-gray-600">
              <label
                htmlFor="file-upload"
                className="relative cursor-pointer bg-white rounded-md font-medium text-primary-600 hover:text-primary-500 focus-within:outline-none focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-primary-500"
              >
                <span>Upload a file</span>
                <input
                  id="file-upload"
                  name="file-upload"
                  type="file"
                  className="sr-only"
                  onChange={handleFileSelect}
                  disabled={uploadMutation.isPending}
                />
              </label>
              <p className="pl-1">or drag and drop</p>
            </div>
            <p className="text-xs text-gray-500">Any file up to 10MB</p>
          </div>
        </div>
        {selectedFile && (
          <div className="text-sm text-gray-600">
            Selected: {selectedFile.name}
          </div>
        )}
        {error && (
          <div className="text-sm text-red-600 bg-red-50 p-4 rounded border border-red-200">
            <div className="font-semibold mb-2">Error Details:</div>
            <pre className="whitespace-pre-wrap font-mono text-xs">{error}</pre>
          </div>
        )}
        
        {uploadedFile && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="flex items-center mb-3">
              <CheckCircleIcon className="h-5 w-5 text-green-500 mr-2" />
              <h3 className="text-sm font-semibold text-green-800">Upload Successful!</h3>
              <button
                onClick={() => setUploadedFile(null)}
                className="ml-auto text-green-500 hover:text-green-700"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-2 text-xs">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>
                  <span className="font-medium text-gray-700">ID:</span>
                  <span className="ml-2 font-mono text-gray-600">{uploadedFile.id}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">User ID:</span>
                  <span className="ml-2 font-mono text-gray-600">{uploadedFile.user_id}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">Filename:</span>
                  <span className="ml-2 text-gray-600">{uploadedFile.original_filename}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">File Type:</span>
                  <span className="ml-2 text-gray-600">{uploadedFile.file_type}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">Size:</span>
                  <span className="ml-2 text-gray-600">{uploadedFile.size} bytes ({(uploadedFile.size / 1024).toFixed(2)} KB)</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">Uploaded:</span>
                  <span className="ml-2 text-gray-600">{new Date(uploadedFile.uploaded_at).toLocaleString()}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">File Path:</span>
                  <span className="ml-2 font-mono text-gray-600 break-all">{uploadedFile.file}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">Reference Count:</span>
                  <span className="ml-2 text-gray-600">{uploadedFile.reference_count}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">Is Reference:</span>
                  <span className="ml-2 text-gray-600">{uploadedFile.is_reference ? 'Yes' : 'No'}</span>
                </div>
                <div>
                  <span className="font-medium text-gray-700">Original File:</span>
                  <span className="ml-2 font-mono text-gray-600">{uploadedFile.original_file || 'None'}</span>
                </div>
              </div>
              <div className="mt-3 pt-2 border-t border-green-200">
                <div>
                  <span className="font-medium text-gray-700">File Hash:</span>
                  <span className="ml-2 font-mono text-xs text-gray-600 break-all">{uploadedFile.file_hash}</span>
                </div>
              </div>
            </div>
          </div>
        )}
        <button
          onClick={handleUpload}
          disabled={!selectedFile || uploadMutation.isPending}
          className={`w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white ${
            !selectedFile || uploadMutation.isPending
              ? 'bg-gray-300 cursor-not-allowed'
              : 'bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500'
          }`}
        >
          {uploadMutation.isPending ? (
            <>
              <svg
                className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                ></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
              Uploading...
            </>
          ) : (
            'Upload'
          )}
        </button>
      </div>
    </div>
  );
};