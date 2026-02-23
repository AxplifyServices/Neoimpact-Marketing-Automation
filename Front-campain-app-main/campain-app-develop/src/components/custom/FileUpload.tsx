import React, { useRef, useState, useEffect } from 'react';
import { Upload, FileText, X, AlertCircle, Eye } from 'lucide-react';
import * as XLSX from 'xlsx';

interface FileUploadProps {
  onFileSelect: (file: File | null) => void;
  selectedFile: File | null;
  accept?: string;
  maxSize?: number;
  error?: string;
  disabled?: boolean;
}

interface PreviewData {
  headers: string[];
  rows: string[][];
  totalRows: number;
}

const ALLOWED_EXTENSIONS = ['.csv', '.xlsx'];
const ALLOWED_MIME_TYPES = [
  'text/csv',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
];
const DEFAULT_MAX_SIZE = 10 * 1024 * 1024; // 10MB

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
};

export const FileUpload: React.FC<FileUploadProps> = ({
  onFileSelect,
  selectedFile,
  accept = '.csv,.xlsx',
  maxSize = DEFAULT_MAX_SIZE,
  error,
  disabled = false,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const validateFile = (file: File): string | null => {
    // Validate file extension
    const extension = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      return 'Format non supporté. Utilisez CSV ou XLSX uniquement.';
    }

    // Validate MIME type
    if (!ALLOWED_MIME_TYPES.includes(file.type)) {
      return 'Type MIME invalide. Le fichier pourrait être corrompu.';
    }

    // Validate file size
    if (file.size === 0) {
      return 'Le fichier est vide.';
    }

    if (file.size > maxSize) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
      return `Fichier trop volumineux (${sizeMB} MB). Maximum: ${(maxSize / (1024 * 1024)).toFixed(0)} MB.`;
    }

    return null;
  };

  const parseFilePreview = async (file: File) => {
    setIsLoadingPreview(true);
    try {
      const arrayBuffer = await file.arrayBuffer();
      const workbook = XLSX.read(arrayBuffer, { type: 'array' });
      const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
      const jsonData = XLSX.utils.sheet_to_json(firstSheet, { header: 1 }) as string[][];

      if (jsonData.length === 0) {
        setPreviewData(null);
        return;
      }

      const headers = jsonData[0] || [];
      const dataRows = jsonData.slice(1, 6); // Show first 5 rows
      const totalRows = jsonData.length - 1; // Exclude header

      setPreviewData({
        headers: headers.map(h => String(h)),
        rows: dataRows.map(row => row.map(cell => String(cell || ''))),
        totalRows,
      });
    } catch (error) {
      console.error('Error parsing file:', error);
      setPreviewData(null);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  useEffect(() => {
    if (selectedFile) {
      parseFilePreview(selectedFile);
      setShowPreview(true);
    } else {
      setPreviewData(null);
      setShowPreview(false);
    }
  }, [selectedFile]);

  const handleFileChange = (file: File | null) => {
    if (!file) {
      onFileSelect(null);
      return;
    }

    const validationError = validateFile(file);
    if (validationError) {
      onFileSelect(null);
      return;
    }

    onFileSelect(file);
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    handleFileChange(file);
  };

  const handleClick = () => {
    if (!disabled) {
      fileInputRef.current?.click();
    }
  };

  const handleRemove = (event: React.MouseEvent) => {
    event.stopPropagation();
    onFileSelect(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragEnter = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (!disabled) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);

    if (disabled) return;

    const file = event.dataTransfer.files[0] || null;
    handleFileChange(file);
  };

  const hasError = !!error;

  return (
    <div className="w-full">
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleInputChange}
        className="hidden"
        disabled={disabled}
        aria-label="Sélectionner un fichier"
      />

      <div
        onClick={handleClick}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={`
          relative border-2 rounded-lg p-6 transition-all cursor-pointer
          ${disabled ? 'opacity-50 cursor-not-allowed bg-gray-50' : ''}
          ${hasError ? 'border-red-300 bg-red-50' : ''}
          ${!hasError && !selectedFile && !isDragging ? 'border-dashed border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50' : ''}
          ${!hasError && !selectedFile && isDragging ? 'border-solid border-blue-400 bg-blue-50' : ''}
          ${!hasError && selectedFile ? 'border-solid border-green-300 bg-green-50' : ''}
        `}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label={selectedFile ? 'Fichier sélectionné, cliquez pour changer' : 'Cliquez ou glissez-déposez un fichier'}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
            e.preventDefault();
            handleClick();
          }
        }}
      >
        {!selectedFile ? (
          <div className="flex flex-col items-center justify-center text-center">
            <div className={`mb-3 ${hasError ? 'text-red-500' : 'text-gray-400'}`}>
              {hasError ? (
                <AlertCircle className="w-12 h-12" />
              ) : (
                <Upload className="w-12 h-12" />
              )}
            </div>
            <p className="text-sm font-medium text-gray-700 mb-1">
              {isDragging ? 'Déposez le fichier ici' : 'Glissez-déposez un fichier ici'}
            </p>
            <p className="text-xs text-gray-500">ou cliquez pour parcourir</p>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <div className="text-green-600">
                <FileText className="w-8 h-8" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-gray-600">
                  {formatFileSize(selectedFile.size)}
                  {selectedFile.type && ` • ${selectedFile.type.split('/')[1]?.toUpperCase()}`}
                </p>
              </div>
            </div>
            <button
              onClick={handleRemove}
              disabled={disabled}
              className="ml-2 p-1 rounded-full hover:bg-red-100 text-gray-500 hover:text-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Supprimer le fichier"
              type="button"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        )}
      </div>

      {/* File Preview */}
      {selectedFile && showPreview && (
        <div className="mt-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Eye className="w-4 h-4 text-gray-600" />
              <span className="text-sm font-medium text-gray-700">Aperçu du fichier</span>
            </div>
            <button
              onClick={() => setShowPreview(!showPreview)}
              className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
              type="button"
            >
              {showPreview ? 'Masquer' : 'Afficher'}
            </button>
          </div>

          {isLoadingPreview ? (
            <div className="border rounded-lg p-4 text-center text-sm text-gray-500">
              Chargement de l'aperçu...
            </div>
          ) : previewData ? (
            <div className="border rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      {previewData.headers.map((header, idx) => (
                        <th key={idx} className="px-3 py-2 text-left text-xs font-semibold text-gray-700 border-b">
                          {header || `Colonne ${idx + 1}`}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="bg-white">
                    {previewData.rows.map((row, rowIdx) => (
                      <tr key={rowIdx} className="border-b last:border-b-0 hover:bg-gray-50">
                        {row.map((cell, cellIdx) => (
                          <td key={cellIdx} className="px-3 py-2 text-xs text-gray-600">
                            {cell || '-'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="bg-gray-50 px-3 py-2 text-xs text-gray-600 border-t">
                Affichage de {Math.min(5, previewData.rows.length)} sur {previewData.totalRows} ligne(s)
              </div>
            </div>
          ) : (
            <div className="border rounded-lg p-4 text-center text-sm text-gray-500">
              Impossible de charger l'aperçu
            </div>
          )}
        </div>
      )}

      {hasError && (
        <div className="mt-2 flex items-start gap-2 text-sm text-red-600">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <p>{error}</p>
        </div>
      )}
    </div>
  );
};
