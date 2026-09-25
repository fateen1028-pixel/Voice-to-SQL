/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { 50:'#f0f4ff',100:'#e0e8ff',200:'#c7d6fe',300:'#a3b8fd',400:'#7f9bfe',500:'#5c7bfe',600:'#4161fd',700:'#354ce5',800:'#3045b8',900:'#2d3e8f' },
        surface: { 50:'#fafaf9',100:'#f5f5f4',200:'#e7e5e4',300:'#d6d3d1',400:'#a8a29e',500:'#78716c',600:'#57534e',700:'#44403c',800:'#292524',900:'#1c1917' }
      }
    },
  },
  plugins: [],
};
