/** @type {import('tailwindcss').Config} */
// 灰阶映射到 style.css 的 --tl-gray-* CSS 变量（RGB 三元组），
// 暗黑模式切换时自动翻转 —— 视图内使用 text-gray-* / bg-gray-* 等类无需再加 dark: 变体。
// white 不做映射：主色/渐变背景上的白字在暗色下应保持白色；容器底色请用 bg-surface。
const gray = (v) => `rgb(var(--tl-gray-${v}) / <alpha-value>)`

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        gray: {
          50: gray(50), 100: gray(100), 200: gray(200), 300: gray(300),
          400: gray(400), 500: gray(500), 600: gray(600), 700: gray(700),
          800: gray(800), 900: gray(900),
        },
        surface: gray(0),
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
