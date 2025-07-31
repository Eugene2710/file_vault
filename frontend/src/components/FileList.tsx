import {
  DocumentIcon,
  TrashIcon,
  ArrowDownTrayIcon,
  FunnelIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ChartBarIcon,
  ChevronLeftIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
} from '@heroicons/react/24/outline';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import React, { useState, useCallback } from 'react';

import { fileService } from '../services/fileService';
import { File as FileType, PaginatedResponse } from '../types/file';

interface FileListProps {
  userId: string;
}

export const FileList: React.FC<FileListProps> = ({ userId }) => {
  const queryClient = useQueryClient();
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [showFileTypes, setShowFileTypes] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [filters, setFilters] = useState({
    search: '',
    file_type: '',
    min_size: '',
    max_size: '',
    start_date: '',
    end_date: '',
  });
  
  const [appliedFilters, setAppliedFilters] = useState({
    search: '',
    file_type: '',
    min_size: '',
    max_size: '',
    start_date: '',
    end_date: '',
  });

  const getActiveFilters = useCallback((filterState: typeof filters) => {
    const activeFilters: any = {};
    if (filterState.search.trim()) activeFilters.search = filterState.search.trim();
    if (filterState.file_type.trim()) activeFilters.file_type = filterState.file_type.trim();
    if (filterState.min_size.trim()) activeFilters.min_size = parseInt(filterState.min_size);
    if (filterState.max_size.trim()) activeFilters.max_size = parseInt(filterState.max_size);
    
    if (filterState.start_date.trim()) {
      let dateStr = filterState.start_date.trim();
      // If only date is provided (no time), append 00:00
      if (dateStr.length === 10) {
        dateStr += 'T00:00';
      }
      activeFilters.start_date = new Date(dateStr).toISOString();
    }
    
    if (filterState.end_date.trim()) {
      let dateStr = filterState.end_date.trim();
      // If only date is provided (no time), append 00:00
      if (dateStr.length === 10) {
        dateStr += 'T00:00';
      }
      activeFilters.end_date = new Date(dateStr).toISOString();
    }
    
    return Object.keys(activeFilters).length > 0 ? activeFilters : undefined;
  }, []);

  const handleApplyFilters = () => {
    setAppliedFilters({ ...filters });
    setCurrentPage(1); // Reset to first page when filters change
  };

  // Query for fetching files with pagination
  const {
    data: paginatedData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['files', userId, getActiveFilters(appliedFilters), currentPage],
    queryFn: () => fileService.getFiles(userId, { 
      ...getActiveFilters(appliedFilters), 
      page: currentPage 
    }),
    enabled: !!userId,
  });

  const files = paginatedData?.results || [];
  const totalCount = paginatedData?.count || 0;
  const hasNext = !!paginatedData?.next;
  const hasPrevious = !!paginatedData?.previous;

  // Query for storage stats
  const {
    data: storageStats,
    isLoading: isLoadingStats,
    error: statsError,
  } = useQuery({
    queryKey: ['storageStats', userId],
    queryFn: () => fileService.getStorageStats(userId),
    enabled: !!userId,
  });

  // Query for file types
  const {
    data: fileTypes,
    isLoading: isLoadingFileTypes,
  } = useQuery({
    queryKey: ['fileTypes', userId],
    queryFn: () => fileService.getFileTypes(userId),
    enabled: !!userId,
  });

  // Mutation for deleting files
  const deleteMutation = useMutation({
    mutationFn: (id: string) => fileService.deleteFile(id, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['files'] });
      // Refresh all expanded file details
      queryClient.invalidateQueries({ queryKey: ['file'] });
      // Refresh storage stats
      queryClient.invalidateQueries({ queryKey: ['storageStats'] });
    },
  });

  // Mutation for downloading files
  const downloadMutation = useMutation({
    mutationFn: ({
      fileId,
      filename,
    }: {
      fileId: string;
      filename: string;
    }) => fileService.downloadFile(fileId, userId, filename),
  });

  const handleDelete = async (id: string) => {
    try {
      await deleteMutation.mutateAsync(id);
    } catch (err) {
      console.error('Delete error:', err);
    }
  };

  const handleDownload = async (fileId: string, filename: string) => {
    try {
      await downloadMutation.mutateAsync({ fileId, filename });
    } catch (err) {
      console.error('Download error:', err);
    }
  };

  // Pagination handlers
  const totalPages = Math.ceil(totalCount / 10); // 10 files per page
  
  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePreviousPage = () => {
    if (hasPrevious) {
      setCurrentPage(prev => Math.max(1, prev - 1));
    }
  };

  const handleNextPage = () => {
    if (hasNext) {
      setCurrentPage(prev => prev + 1);
    }
  };

  const toggleExpand = (fileId: string) => {
    setExpandedFiles(prev => {
      const newSet = new Set(prev);
      if (newSet.has(fileId)) {
        newSet.delete(fileId);
      } else {
        newSet.add(fileId);
      }
      return newSet;
    });
  };

  // Query for file details when expanded
  const useFileDetails = (fileId: string, isExpanded: boolean) => {
    return useQuery({
      queryKey: ['file', fileId],
      queryFn: () => fileService.getFile(fileId, userId),
      enabled: isExpanded && !!userId,
    });
  };

  const FileDetailsSection: React.FC<{ file: { id: string }, isExpanded: boolean }> = ({ file, isExpanded }) => {
    const { data: fileDetails, isLoading, error } = useFileDetails(file.id, isExpanded);

    if (!isExpanded) return null;

    if (isLoading) {
      return (
        <div className="mt-3 p-4 bg-gray-50 rounded-lg border">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
            <div className="space-y-2">
              <div className="h-3 bg-gray-200 rounded w-1/2"></div>
              <div className="h-3 bg-gray-200 rounded w-1/3"></div>
              <div className="h-3 bg-gray-200 rounded w-2/3"></div>
            </div>
          </div>
        </div>
      );
    }

    if (error) {
      return (
        <div className="mt-3 p-4 bg-red-50 rounded-lg border border-red-200">
          <p className="text-sm text-red-600">Failed to load file details</p>
        </div>
      );
    }

    if (!fileDetails) return null;

    return (
      <div className="mt-3 p-4 bg-gray-50 rounded-lg border">
        <h4 className="text-sm font-semibold text-gray-900 mb-3">File Details</h4>
        <div className="space-y-3 text-xs">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <span className="font-medium text-gray-700">ID:</span>
              <span className="ml-2 font-mono text-gray-600 break-all">{fileDetails.id}</span>
            </div>
            <div>
              <span className="font-medium text-gray-700">User ID:</span>
              <span className="ml-2 font-mono text-gray-600">{fileDetails.user_id}</span>
            </div>
            <div>
              <span className="font-medium text-gray-700">Original Filename:</span>
              <span className="ml-2 text-gray-600">{fileDetails.original_filename}</span>
            </div>
            <div>
              <span className="font-medium text-gray-700">File Type:</span>
              <span className="ml-2 text-gray-600">{fileDetails.file_type}</span>
            </div>
            <div>
              <span className="font-medium text-gray-700">Size:</span>
              <span className="ml-2 text-gray-600">{fileDetails.size} bytes ({(fileDetails.size / 1024).toFixed(2)} KB)</span>
            </div>
            <div>
              <span className="font-medium text-gray-700">Uploaded:</span>
              <span className="ml-2 text-gray-600">{new Date(fileDetails.uploaded_at).toLocaleString()}</span>
            </div>
            <div>
              <span className="font-medium text-gray-700">Reference Count:</span>
              <span className="ml-2 text-gray-600">{fileDetails.reference_count}</span>
            </div>
            <div>
              <span className="font-medium text-gray-700">Is Reference:</span>
              <span className="ml-2 text-gray-600">{fileDetails.is_reference ? 'Yes' : 'No'}</span>
            </div>
            <div className="md:col-span-2">
              <span className="font-medium text-gray-700">File Path:</span>
              <span className="ml-2 font-mono text-gray-600 break-all">{fileDetails.file}</span>
            </div>
            <div className="md:col-span-2">
              <span className="font-medium text-gray-700">Original File:</span>
              <span className="ml-2 font-mono text-gray-600">{fileDetails.original_file || 'None'}</span>
            </div>
          </div>
          <div className="pt-2 border-t border-gray-200">
            <div>
              <span className="font-medium text-gray-700">File Hash:</span>
              <span className="ml-2 font-mono text-xs text-gray-600 break-all">{fileDetails.file_hash}</span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-200 rounded w-1/4"></div>
          <div className="space-y-3">
            <div className="h-8 bg-gray-200 rounded"></div>
            <div className="h-8 bg-gray-200 rounded"></div>
            <div className="h-8 bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border-l-4 border-red-400 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-red-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700">
                Failed to load files. Please try again.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">
        Uploaded Files
      </h2>

      {/* Filters Section - Always Expanded */}
      <div className="mb-6">
        <div className="flex items-center mb-3">
          <FunnelIcon className="h-4 w-4 text-primary-600 mr-2" />
          <h3 className="text-sm font-medium text-gray-900">Filters</h3>
        </div>
        
        <div className="bg-gray-50 p-4 rounded-lg mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Search filename
              </label>
              <input
                type="text"
                value={filters.search}
                onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
                placeholder="Search by filename..."
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                File type
              </label>
              <select
                value={filters.file_type}
                onChange={(e) => setFilters(prev => ({ ...prev, file_type: e.target.value }))}
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                disabled={isLoadingFileTypes}
              >
                <option value="">All types</option>
                {fileTypes?.map((fileType) => (
                  <option key={fileType} value={fileType}>
                    {fileType}
                  </option>
                ))}
              </select>
              {isLoadingFileTypes && (
                <p className="text-xs text-gray-500 mt-1">Loading file types...</p>
              )}
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Min size (bytes)
              </label>
              <input
                type="number"
                value={filters.min_size}
                onChange={(e) => setFilters(prev => ({ ...prev, min_size: e.target.value }))}
                placeholder="0"
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Max size (bytes)
              </label>
              <input
                type="number"
                value={filters.max_size}
                onChange={(e) => setFilters(prev => ({ ...prev, max_size: e.target.value }))}
                placeholder="No limit"
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Start date
              </label>
              <input
                type="datetime-local"
                value={filters.start_date}
                onChange={(e) => setFilters(prev => ({ ...prev, start_date: e.target.value }))}
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                End date
              </label>
              <input
                type="datetime-local"
                value={filters.end_date}
                onChange={(e) => setFilters(prev => ({ ...prev, end_date: e.target.value }))}
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
          </div>
          
          <div className="mt-4 flex justify-end space-x-2">
            <button
              onClick={handleApplyFilters}
              className="px-3 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
              Apply filters
            </button>
            <button
              onClick={() => {
                const emptyFilters = {
                  search: '',
                  file_type: '',
                  min_size: '',
                  max_size: '',
                  start_date: '',
                  end_date: '',
                };
                setFilters(emptyFilters);
                setAppliedFilters(emptyFilters);
                setCurrentPage(1); // Reset to first page when clearing filters
              }}
              className="px-3 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
              Clear filters
            </button>
          </div>
        </div>
      </div>

      {!files || files.length === 0 ? (
        <div className="text-center py-12">
          <DocumentIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No files</h3>
          <p className="mt-1 text-sm text-gray-500">
            Get started by uploading a file
          </p>
        </div>
      ) : (
        <div className="mt-6 flow-root">
          <ul className="-my-5 divide-y divide-gray-200">
            {files.map((file) => {
              const isExpanded = expandedFiles.has(file.id);
              return (
                <li key={file.id} className="py-4">
                  <div className="flex items-center space-x-4">
                    <div className="flex-shrink-0">
                      <DocumentIcon className="h-8 w-8 text-gray-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {file.original_filename}
                      </p>
                      <p className="text-sm text-gray-500">
                        {file.file_type} • {(file.size / 1024).toFixed(2)} KB
                      </p>
                      <p className="text-sm text-gray-500">
                        Uploaded {new Date(file.uploaded_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={() => toggleExpand(file.id)}
                        className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                      >
                        {isExpanded ? (
                          <ChevronDownIcon className="h-4 w-4 mr-1" />
                        ) : (
                          <ChevronRightIcon className="h-4 w-4 mr-1" />
                        )}
                        Details
                      </button>
                      <button
                        onClick={() =>
                          handleDownload(file.id, file.original_filename)
                        }
                        disabled={downloadMutation.isPending}
                        className="inline-flex items-center px-3 py-2 border border-transparent shadow-sm text-sm leading-4 font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                      >
                        <ArrowDownTrayIcon className="h-4 w-4 mr-1" />
                        Download
                      </button>
                      <button
                        onClick={() => handleDelete(file.id)}
                        disabled={deleteMutation.isPending}
                        className="inline-flex items-center px-3 py-2 border border-transparent shadow-sm text-sm leading-4 font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                      >
                        <TrashIcon className="h-4 w-4 mr-1" />
                        Delete
                      </button>
                    </div>
                  </div>
                  <FileDetailsSection file={file} isExpanded={isExpanded} />
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Pagination Component - Always visible */}
      <div className="mt-6 flex items-center justify-between border-t border-gray-200 bg-white px-4 py-3 sm:px-6">
        <div className="flex flex-1 justify-between sm:hidden">
          <button
            onClick={handlePreviousPage}
            disabled={!hasPrevious}
            className={`relative inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium ${
              hasPrevious 
                ? 'text-gray-700 hover:bg-gray-50' 
                : 'text-gray-400 cursor-not-allowed'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            Previous
          </button>
          <button
            onClick={handleNextPage}
            disabled={!hasNext}
            className={`relative ml-3 inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium ${
              hasNext 
                ? 'text-gray-700 hover:bg-gray-50' 
                : 'text-gray-400 cursor-not-allowed'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            Next
          </button>
        </div>
        <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
          <div>
            <p className="text-sm text-gray-700">
              Showing{' '}
              <span className="font-medium">{totalCount > 0 ? Math.min((currentPage - 1) * 10 + 1, totalCount) : 0}</span>
              {' '}to{' '}
              <span className="font-medium">
                {Math.min(currentPage * 10, totalCount)}
              </span>
              {' '}of{' '}
              <span className="font-medium">{totalCount}</span> results
            </p>
          </div>
          <div>
            <nav className="isolate inline-flex -space-x-px rounded-md shadow-sm" aria-label="Pagination">
              <button
                onClick={() => handlePageChange(1)}
                disabled={currentPage === 1 || totalCount === 0}
                className={`relative inline-flex items-center rounded-l-md px-2 py-2 ring-1 ring-inset ring-gray-300 focus:z-20 focus:outline-offset-0 ${
                  currentPage === 1 || totalCount === 0
                    ? 'text-gray-300 cursor-not-allowed' 
                    : 'text-gray-400 hover:bg-gray-50'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                <span className="sr-only">First page</span>
                <ChevronDoubleLeftIcon className="h-5 w-5" aria-hidden="true" />
              </button>
              <button
                onClick={handlePreviousPage}
                disabled={!hasPrevious}
                className={`relative inline-flex items-center px-2 py-2 ring-1 ring-inset ring-gray-300 focus:z-20 focus:outline-offset-0 ${
                  hasPrevious
                    ? 'text-gray-400 hover:bg-gray-50' 
                    : 'text-gray-300 cursor-not-allowed'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                <span className="sr-only">Previous</span>
                <ChevronLeftIcon className="h-5 w-5" aria-hidden="true" />
              </button>
              
              {/* Page numbers - Always show at least page 1 */}
              {totalPages > 0 ? (
                Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 5) {
                    pageNum = i + 1;
                  } else if (currentPage <= 3) {
                    pageNum = i + 1;
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = currentPage - 2 + i;
                  }
                  
                  return (
                    <button
                      key={pageNum}
                      onClick={() => handlePageChange(pageNum)}
                      disabled={totalCount === 0}
                      className={`relative inline-flex items-center px-4 py-2 text-sm font-semibold ${
                        currentPage === pageNum
                          ? 'z-10 bg-primary-600 text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600'
                          : totalCount === 0
                          ? 'text-gray-300 ring-1 ring-inset ring-gray-300 cursor-not-allowed'
                          : 'text-gray-900 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0'
                      }`}
                    >
                      {pageNum}
                    </button>
                  );
                })
              ) : (
                <button
                  disabled
                  className="relative inline-flex items-center px-4 py-2 text-sm font-semibold text-gray-300 ring-1 ring-inset ring-gray-300 cursor-not-allowed"
                >
                  1
                </button>
              )}
              
              <button
                onClick={handleNextPage}
                disabled={!hasNext}
                className={`relative inline-flex items-center px-2 py-2 ring-1 ring-inset ring-gray-300 focus:z-20 focus:outline-offset-0 ${
                  hasNext
                    ? 'text-gray-400 hover:bg-gray-50' 
                    : 'text-gray-300 cursor-not-allowed'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                <span className="sr-only">Next</span>
                <ChevronRightIcon className="h-5 w-5" aria-hidden="true" />
              </button>
              <button
                onClick={() => handlePageChange(totalPages)}
                disabled={currentPage === totalPages || totalPages <= 1}
                className={`relative inline-flex items-center rounded-r-md px-2 py-2 ring-1 ring-inset ring-gray-300 focus:z-20 focus:outline-offset-0 ${
                  currentPage === totalPages || totalPages <= 1
                    ? 'text-gray-300 cursor-not-allowed' 
                    : 'text-gray-400 hover:bg-gray-50'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                <span className="sr-only">Last page</span>
                <ChevronDoubleRightIcon className="h-5 w-5" aria-hidden="true" />
              </button>
            </nav>
          </div>
        </div>
      </div>
      
      {/* Storage Stats Section */}
      <div className="mt-8 border-t border-gray-200 pt-6">
        <div className="flex items-center mb-4">
          <ChartBarIcon className="h-5 w-5 text-primary-600 mr-2" />
          <h3 className="text-lg font-semibold text-gray-900">Storage Statistics for {userId}</h3>
        </div>
        
        {isLoadingStats ? (
          <div className="bg-gray-50 rounded-lg p-6">
            <div className="animate-pulse space-y-4">
              <div className="h-4 bg-gray-200 rounded w-1/3"></div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="h-16 bg-gray-200 rounded"></div>
                <div className="h-16 bg-gray-200 rounded"></div>
                <div className="h-16 bg-gray-200 rounded"></div>
                <div className="h-16 bg-gray-200 rounded"></div>
              </div>
            </div>
          </div>
        ) : statsError ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-600">Failed to load storage statistics</p>
          </div>
        ) : storageStats ? (
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-6 border border-blue-200">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600">
                  {(storageStats.total_storage_used / 1024).toFixed(2)} KB
                </div>
                <div className="text-sm font-medium text-gray-700 mt-1">Actual Storage Used</div>
                <div className="text-xs text-gray-500 mt-1">
                  {storageStats.total_storage_used} bytes
                </div>
              </div>
              
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-600">
                  {(storageStats.original_storage_used / 1024).toFixed(2)} KB
                </div>
                <div className="text-sm font-medium text-gray-700 mt-1">Without Deduplication</div>
                <div className="text-xs text-gray-500 mt-1">
                  {storageStats.original_storage_used} bytes
                </div>
              </div>
              
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">
                  {(storageStats.storage_savings / 1024).toFixed(2)} KB
                </div>
                <div className="text-sm font-medium text-gray-700 mt-1">Storage Saved</div>
                <div className="text-xs text-gray-500 mt-1">
                  {storageStats.storage_savings} bytes
                </div>
              </div>
              
              <div className="text-center">
                <div className="text-2xl font-bold text-purple-600">
                  {storageStats.savings_percentage.toFixed(1)}%
                </div>
                <div className="text-sm font-medium text-gray-700 mt-1">Savings Percentage</div>
                <div className="text-xs text-gray-500 mt-1">
                  Deduplication efficiency
                </div>
              </div>
            </div>
            
            {storageStats.savings_percentage > 0 && (
              <div className="mt-4 p-3 bg-white rounded border border-blue-200">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Deduplication saved you:</span>
                  <span className="font-semibold text-green-600">
                    {(storageStats.storage_savings / 1024).toFixed(2)} KB ({storageStats.savings_percentage.toFixed(1)}% reduction)
                  </span>
                </div>
                <div className="mt-2">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-gradient-to-r from-green-400 to-green-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(storageStats.savings_percentage, 100)}%` }}
                    ></div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
};