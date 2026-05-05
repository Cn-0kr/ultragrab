/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#10B5A2',
          dark: '#0B8F80',
          soft: '#DFF7F2',
        },
        accent: {
          DEFAULT: '#FFD23F',
          dark: '#E6B800',
        },
        ink: {
          DEFAULT: '#0F172A',
          soft: '#334155',
          mute: '#64748B',
        },
        cream: '#FFF9EF',
      },
      fontFamily: {
        display: ['"Archivo Black"', 'system-ui', 'sans-serif'],
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        sticker: '6px 6px 0 0 rgba(15,23,42,1)',
        'sticker-sm': '3px 3px 0 0 rgba(15,23,42,1)',
      },
      borderRadius: {
        card: '28px',
      },
    },
  },
  plugins: [],
}
