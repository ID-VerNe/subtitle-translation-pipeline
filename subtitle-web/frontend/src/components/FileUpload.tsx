import { useState, useCallback, useRef } from 'react';

interface FileUploadProps {
  onFileSelected: (file: File) => void;
  selectedFile: File | null;
  disabled?: boolean;
}

export default function FileUpload({ onFileSelected, selectedFile, disabled }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }, [disabled]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;

    const file = e.dataTransfer.files[0];
    if (file && /\.(mkv|srt|ass)$/i.test(file.name)) {
      onFileSelected(file);
    }
  }, [disabled, onFileSelected]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileSelected(file);
    }
  }, [onFileSelected]);

  const handleClick = () => {
    if (!disabled) inputRef.current?.click();
  };

  return (
    <div
      onClick={handleClick}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className="card cursor-pointer transition-all duration-200"
      style={{
        border: isDragging ? '2px solid #0071e3' : '2px dashed transparent',
        opacity: disabled ? 0.6 : 1,
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".mkv,.srt,.ass"
        onChange={handleFileChange}
        className="hidden"
      />

      <div className="flex flex-col items-center justify-center py-12">
        {selectedFile ? (
          <>
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center mb-6"
              style={{ backgroundColor: 'rgba(0, 113, 227, 0.1)' }}
            >
              <span style={{ fontSize: '32px' }}>📄</span>
            </div>
            <p
              className="text-center font-semibold mb-2"
              style={{
                fontSize: '17px',
                lineHeight: '1.29',
                letterSpacing: '-0.224px',
                color: '#1d1d1f'
              }}
            >
              {selectedFile.name}
            </p>
            <p
              className="text-center mb-4"
              style={{
                fontSize: '14px',
                lineHeight: '1.43',
                letterSpacing: '-0.224px',
                color: 'rgba(0, 0, 0, 0.48)'
              }}
            >
              {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
            </p>
            {!disabled && (
              <p
                className="text-center"
                style={{
                  fontSize: '14px',
                  lineHeight: '1.43',
                  letterSpacing: '-0.224px',
                  color: '#0066cc'
                }}
              >
                Click to change file
              </p>
            )}
          </>
        ) : (
          <>
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center mb-6"
              style={{ backgroundColor: 'rgba(0, 113, 227, 0.1)' }}
            >
              <span style={{ fontSize: '32px' }}>📤</span>
            </div>
            <p
              className="text-center font-semibold mb-2"
              style={{
                fontSize: '17px',
                lineHeight: '1.29',
                letterSpacing: '-0.224px',
                color: '#1d1d1f'
              }}
            >
              Drop subtitle file here
            </p>
            <p
              className="text-center"
              style={{
                fontSize: '14px',
                lineHeight: '1.43',
                letterSpacing: '-0.224px',
                color: 'rgba(0, 0, 0, 0.48)'
              }}
            >
              or click to browse • MKV, SRT, ASS supported
            </p>
          </>
        )}
      </div>
    </div>
  );
}
