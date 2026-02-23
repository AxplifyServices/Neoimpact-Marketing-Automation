/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontSize: {
        'xs': ['0.6875rem', { lineHeight: '1rem' }],      // 11px
        'sm': ['0.75rem', { lineHeight: '1.25rem' }],     // 12px
        'base': ['0.875rem', { lineHeight: '1.5rem' }],   // 14px
        'lg': ['1rem', { lineHeight: '1.75rem' }],        // 16px
        'xl': ['1.125rem', { lineHeight: '1.75rem' }],    // 18px
        '2xl': ['1.25rem', { lineHeight: '1.75rem' }],    // 20px
        '3xl': ['1.5rem', { lineHeight: '2rem' }],        // 24px
        '4xl': ['1.875rem', { lineHeight: '2.25rem' }],   // 30px
      },
      spacing: {
        '1': '0.1875rem',  // 3px
        '2': '0.375rem',   // 6px
        '3': '0.5rem',     // 8px
        '4': '0.75rem',    // 12px
        '6': '1rem',       // 16px
        '8': '1.5rem',     // 24px
      },
      height: {
        '7': '1.75rem',   // 28px
        '8': '2rem',      // 32px
        '10': '2.5rem',   // 40px
      },
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        chart: {
          "1": "hsl(var(--chart-1))",
          "2": "hsl(var(--chart-2))",
          "3": "hsl(var(--chart-3))",
          "4": "hsl(var(--chart-4))",
          "5": "hsl(var(--chart-5))",
        },
      },
    },
  },
  plugins: [],
}
