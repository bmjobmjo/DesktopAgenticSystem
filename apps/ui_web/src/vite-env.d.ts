/// <reference types="vite/client" />

interface Window {
  __OASIS_RUNTIME_CONFIG__?: {
    apiBaseUrl?: string;
    apiPort?: number | string;
  };
}
