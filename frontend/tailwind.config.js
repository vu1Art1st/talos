/** @type {import('tailwindcss').Config} */
// 灰阶映射到 style.css 的 --tl-gray-* CSS 变量（RGB 三元组），
// 暗黑模式切换时自动翻转 —— 视图内使用 text-gray-* / bg-gray-* 等类无需再加 dark: 变体。
// white 不做映射：主色背景上的白字在暗色下应保持白色；容器底色请用 bg-surface。
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
          50: '#ecfdf5', 100: '#d1fae5', 200: '#a7f3d0', 300: '#6ee7b7',
          400: '#34d399', 500: '#10b981', 600: '#059669', 700: '#047857',
          800: '#065f46', 900: '#064e3b',
        },
        accent: {
          50: '#f0f9ff', 100: '#e0f2fe', 200: '#bae6fd', 300: '#7dd3fc',
          400: '#38bdf8', 500: '#0ea5e9', 600: '#0284c7', 700: '#0369a1',
          800: '#075985', 900: '#0c4a6e',
        },
      },
      fontSize: {
        // 语义字号阶梯（基准 13.5px，见 style.css body）：
        // text-2xs 11 / text-xs 12 / text-sm 13.5（默认正文）/ text-base 14 /
        // text-lg 16 / text-xl 18 / text-2xl 26（统计卡大数）
        '2xs': ['11px', { lineHeight: '16px' }],
        xs: ['12px', { lineHeight: '18px' }],
        sm: ['13.5px', { lineHeight: '20px' }],
        base: ['14px', { lineHeight: '21px' }],
        lg: ['16px', { lineHeight: '24px' }],
        xl: ['18px', { lineHeight: '26px' }],
        '2xl': ['26px', { lineHeight: '32px' }],
      },
      borderRadius: {
        card: '10px',
        control: '7px',
        overlay: '12px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 23, 20, .04)',
        pop: '0 16px 48px rgba(15, 23, 20, .16)',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'PingFang SC',
          'Microsoft YaHei UI', 'Microsoft YaHei', 'sans-serif'],
        mono: ['ui-monospace', 'Cascadia Code', 'JetBrains Mono', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
  corePlugins: {
    preflight: false, // 避免与 Element Plus 样式冲突
  },
}
