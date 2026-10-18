import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendOrigin = (env.VITE_BACKEND_ORIGIN || 'http://127.0.0.1:8000').replace(/\/$/, '');
  return {
    plugins: [react()],
    server: {
      host: true,
      proxy: {
        '/api': { target: backendOrigin, changeOrigin: true },
        '/ws': { target: backendOrigin.replace(/^http/, 'ws'), ws: true },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return;
            if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'framework';
            if (/node_modules\/(recharts|d3-[^/]+)\//.test(id)) return 'charts';
            if (id.includes('node_modules/lucide-react/')) return 'icons';
          },
        },
      },
    },
  };
});
