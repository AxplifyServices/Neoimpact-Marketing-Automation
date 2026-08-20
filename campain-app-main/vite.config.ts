import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/reactflow/')) return 'reactflow-vendor'
          if (id.includes('/elkjs/')) return 'elk-vendor'
          if (id.includes('/recharts/') || id.includes('/d3-')) return 'charts-vendor'
          if (id.includes('/xlsx/')) return 'xlsx-vendor'
          if (id.includes('/@tanstack/react-query/') || id.includes('/@tanstack/react-table/')) return 'tanstack-vendor'
          if (id.includes('/@radix-ui/')) return 'radix-vendor'
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/react-router')) return 'react-vendor'
          return undefined
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
})
