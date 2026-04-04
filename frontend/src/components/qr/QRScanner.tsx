import { useEffect, useRef, useState, useCallback } from 'react';
import { Html5Qrcode } from 'html5-qrcode';

interface QRScannerProps {
  onScan: (data: string) => void;
  onError?: (err: string) => void;
}

const QRScanner: React.FC<QRScannerProps> = ({ onScan, onError }) => {
  const html5QrCodeRef = useRef<Html5Qrcode | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [cameras, setCameras] = useState<{ id: string; label: string }[]>([]);
  const [selectedCamera, setSelectedCamera] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const stoppingRef = useRef(false);

  const stopAndClearScanner = useCallback(async () => {
    const scanner = html5QrCodeRef.current;
    if (!scanner || stoppingRef.current) return;

    stoppingRef.current = true;
    try {
      try {
        await scanner.stop();
      } catch {
        // Ignore stop errors.
      }
      try {
        await scanner.clear();
      } catch {
        // Ignore clear errors.
      }
    } finally {
      html5QrCodeRef.current = null;
      setIsScanning(false);
      stoppingRef.current = false;
    }
  }, []);

  // Get available cameras
  useEffect(() => {
    Html5Qrcode.getCameras()
      .then((devices) => {
        if (devices && devices.length > 0) {
          setCameras(devices);
          // Prefer back camera
          const backCamera = devices.find(
            (d) => d.label.toLowerCase().includes('back') || d.label.toLowerCase().includes('rear')
          );
          setSelectedCamera(backCamera?.id || devices[0].id);
        } else {
          setError('Камеры не найдены');
        }
      })
      .catch((err) => {
        setError('Не удалось получить список камер');
        if (onError) onError(err.message);
      });
  }, [onError]);

  const startScanning = useCallback(async () => {
    if (!selectedCamera || isScanning) return;

    try {
      // Create new instance
      const html5QrCode = new Html5Qrcode('qr-reader-container');
      html5QrCodeRef.current = html5QrCode;

      await html5QrCode.start(
        selectedCamera,
        {
          fps: 10,
          qrbox: { width: 250, height: 250 },
          aspectRatio: 1.0,
        },
        (decodedText) => {
          // Stop scanning after successful read
          void stopAndClearScanner().then(() => {
            onScan(decodedText);
          });
        },
        () => {
          // Ignore errors - happens every frame without QR
        }
      );

      setIsScanning(true);
      setError(null);
    } catch (err) {
      const error = err as Error;
      setError(`Ошибка запуска камеры: ${error.message}`);
      if (onError) onError(error.message);
    }
  }, [selectedCamera, isScanning, onScan, onError, stopAndClearScanner]);

  const stopScanning = useCallback(async () => {
    if (html5QrCodeRef.current && isScanning) {
      await stopAndClearScanner();
    }
  }, [isScanning, stopAndClearScanner]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      void stopAndClearScanner();
    };
  }, [stopAndClearScanner]);

  // Auto-start when camera is selected
  useEffect(() => {
    if (selectedCamera && !isScanning && cameras.length > 0) {
      startScanning();
    }
  }, [selectedCamera, cameras.length]);

  const handleCameraChange = async (cameraId: string) => {
    await stopScanning();
    setSelectedCamera(cameraId);
  };

  return (
    <div className="qr-scanner-wrapper">
      <div className="qr-scanner-container">
        {/* Camera selector */}
        {cameras.length > 1 && (
          <div className="qr-scanner-header">
            <select
              value={selectedCamera}
              onChange={(e) => handleCameraChange(e.target.value)}
              className="qr-camera-select"
            >
              {cameras.map((camera) => (
                <option key={camera.id} value={camera.id}>
                  {camera.label || `Камера ${camera.id}`}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Video container */}
        <div id="qr-reader-container" className="qr-video-container" />

        {/* Error display */}
        {error && (
          <div className="qr-scanner-error">
            {error}
          </div>
        )}

        {/* Controls */}
        <div className="qr-scanner-controls">
          {!isScanning ? (
            <button onClick={startScanning} className="qr-btn qr-btn-primary">
              Запустить сканер
            </button>
          ) : (
            <button onClick={stopScanning} className="qr-btn qr-btn-secondary">
              Остановить
            </button>
          )}
        </div>
      </div>

      <p className="text-muted text-center" style={{ fontSize: 13 }}>
        Наведите камеру на QR-код участника
      </p>
    </div>
  );
};

export default QRScanner;
