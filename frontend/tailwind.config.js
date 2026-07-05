/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cyber: {
          black: '#0a0a0f',
          dark: '#0d1117',
          darker: '#161b22',
          gray: '#21262d',
          border: '#30363d',
        },
        neon: {
          green: '#00ff88',
          cyan: '#00d4ff',
          purple: '#a855f7',
          red: '#ff4757',
          orange: '#ff9f43',
          yellow: '#ffd93d',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        display: ['Orbitron', 'JetBrains Mono', 'sans-serif'],
      },
      boxShadow: {
        'glow-green': '0 0 10px rgba(0, 255, 136, 0.5), 0 0 20px rgba(0, 255, 136, 0.3)',
        'glow-cyan': '0 0 10px rgba(0, 212, 255, 0.5), 0 0 20px rgba(0, 212, 255, 0.3)',
        'glow-purple': '0 0 10px rgba(168, 85, 247, 0.5), 0 0 20px rgba(168, 85, 247, 0.3)',
        'glow-red': '0 0 10px rgba(255, 71, 87, 0.5), 0 0 20px rgba(255, 71, 87, 0.3)',
      },
      animation: {
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
      },
      keyframes: {
        'glow-pulse': {
          '0%, 100%': { opacity: 1 },
          '50%': { opacity: 0.7 },
        },
      },
    },
  },
  plugins: [],
}
