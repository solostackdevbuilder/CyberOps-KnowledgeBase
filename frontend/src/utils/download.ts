/**
 * Utility functions for downloading files
 */

/**
 * Download a blob as a file
 * @param blob - The blob to download
 * @param filename - The filename for the download
 */
export const downloadBlob = (blob: Blob, filename: string): void => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

/**
 * Download CSV content as a file
 * @param csvContent - The CSV content string
 * @param filename - The filename for the download
 */
export const downloadCSV = (csvContent: string, filename: string): void => {
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, filename);
};





