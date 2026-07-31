/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff', 100: '#e0e7ff', 200: '#c7d2fe', 300: '#a5b4fc',
          400: '#818cf8', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca',
          800: '#3730a3', 900: '#312e81',
        },
      },
      borderRadius: { card: '12px' },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,.04), 0 1px 6px rgba(0,0,0,.04)',
        'card-hover': '0 4px 12px rgba(0,0,0,.08), 0 12px 32px rgba(79,70,229,.10)',
      },
      fontFamily: {
        sans: ['Inter', 'Helvetica Neue', 'Helvetica', 'PingFang SC', 'Microsoft YaHei', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
  corePlugins: {
    preflight: false, // 避免与 Element Plus 样式冲突
  },
}
