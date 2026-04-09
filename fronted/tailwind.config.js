/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'vtuber-bg': '#f0f5ff',
        'vtuber-secondary': '#e8efff',
        'vtuber-accent': '#4a90e2',
        'vtuber-accent-light': '#7db9ff',
        'vtuber-accent-dark': '#2563eb',
        'vtuber-cyan': '#38bdf8',
        'vtuber-purple': '#818cf8',
        'vtuber-light': '#a8c4e8',
        'vtuber-dark': '#3b82f6',
        'vtuber-text': '#1e3a5f',
        'vtuber-text-secondary': '#4a6aa8',
        'vtuber-text-muted': '#8a9ab0',
        'vtuber-border': '#93c5fd',
      },
      fontFamily: {
        sans: ['Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        'xs': '12px',
        'sm': '14px',
        'base': '16px',
        'lg': '18px',
        'xl': '24px',
        '2xl': '32px',
      },
      borderRadius: {
        'lg': '20px',
        'md': '12px',
        'sm': '8px',
      },
      boxShadow: {
        'glow-blue': '0 0 20px rgba(59, 130, 246, 0.4), 0 0 40px rgba(147, 197, 253, 0.2)',
        'glow-blue-intense': '0 0 30px rgba(59, 130, 246, 0.6), 0 0 60px rgba(147, 197, 253, 0.3)',
        'glass': 'inset 0 1px 3px rgba(255, 255, 255, 0.9), 0 4px 20px rgba(59, 130, 246, 0.15)',
        'glass-hover': 'inset 0 1px 3px rgba(255, 255, 255, 0.9), 0 8px 30px rgba(59, 130, 246, 0.25)',
      },
      animation: {
        'slide-in-right': 'slideInRight 0.3s ease-out',
        'marquee': 'marquee 20s linear infinite',
        'blink': 'blink 1s step-end infinite',
        'gentle-sway': 'gentleSway 4s ease-in-out infinite',
        'fade-in': 'fadeIn 0.5s ease-out',
        'float': 'float 6s ease-in-out infinite',
        'pulse-glow': 'pulseGlow 3s ease-in-out infinite',
        'shimmer': 'shimmer 3s linear infinite',
        'border-flow': 'borderFlow 4s linear infinite',
        'float-particle': 'floatParticle 8s ease-in-out infinite',
        'bounce-soft': 'bounceSoft 2s ease-in-out infinite',
        'scale-in': 'scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'gradient-shift': 'gradientShift 8s ease infinite',
      },
      keyframes: {
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        marquee: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
        gentleSway: {
          '0%, 100%': { transform: 'rotate(-2deg)' },
          '50%': { transform: 'rotate(2deg)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        pulseGlow: {
          '0%, 100%': { 
            boxShadow: '0 0 20px rgba(59, 130, 246, 0.3)',
          },
          '50%': { 
            boxShadow: '0 0 40px rgba(59, 130, 246, 0.6), 0 0 60px rgba(147, 197, 253, 0.3)',
          },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition: '200% center' },
        },
        borderFlow: {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
        floatParticle: {
          '0%, 100%': { 
            transform: 'translateY(0) translateX(0) scale(1)',
            opacity: '0',
          },
          '10%': { opacity: '0.8' },
          '90%': { opacity: '0.8' },
          '100%': { 
            transform: 'translateY(-100vh) translateX(50px) scale(0.5)',
            opacity: '0',
          },
        },
        bounceSoft: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-5px)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.9)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        gradientShift: {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'shimmer-gradient': 'linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)',
      },
    },
  },
  plugins: [],
}
