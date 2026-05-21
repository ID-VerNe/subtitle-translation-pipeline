/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        airbnb: {
          rausch: '#ff385c',
          'deep-rausch': '#e00b41',
          'near-black': '#222222',
          'secondary-gray': '#6a6a6a',
          'border-gray': '#dddddd',
          'light-surface': '#f7f7f7',
          white: '#ffffff',
        },
      },
      fontFamily: {
        sans: [
          'Circular',
          '-apple-system',
          'BlinkMacSystemFont',
          'Roboto',
          '"Helvetica Neue"',
          'sans-serif',
        ],
      },
      fontSize: {
        'display': ['28px', { lineHeight: '1.43', fontWeight: '700' }],
        'card-title': ['22px', { lineHeight: '1.18', letterSpacing: '-0.44px', fontWeight: '600' }],
        'feature': ['20px', { lineHeight: '1.20', letterSpacing: '-0.18px', fontWeight: '600' }],
        'ui': ['16px', { lineHeight: '1.25', fontWeight: '500' }],
        'body': ['14px', { lineHeight: '1.43', fontWeight: '400' }],
        'caption': ['13px', { lineHeight: '1.23', fontWeight: '400' }],
        'micro': ['12px', { lineHeight: '1.33', fontWeight: '600' }],
      },
      borderRadius: {
        'btn': '8px',
        'card': '20px',
        'pill': '32px',
        'badge': '14px',
        'circle': '50%',
      },
      boxShadow: {
        'card': 'rgba(0, 0, 0, 0.02) 0px 0px 0px 1px, rgba(0, 0, 0, 0.04) 0px 2px 6px, rgba(0, 0, 0, 0.1) 0px 4px 8px',
        'hover': 'rgba(0, 0, 0, 0.08) 0px 4px 12px',
      },
      spacing: {
        '8': '8px',
        '16': '16px',
        '24': '24px',
        '32': '32px',
        '48': '48px',
        '64': '64px',
      },
    },
  },
  plugins: [],
}

