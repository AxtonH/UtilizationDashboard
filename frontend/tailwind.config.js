/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["../backend/templates/**/*.html", "../backend/static/js/**/*.js"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Inter'", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [require("@tailwindcss/forms"), require("@tailwindcss/typography")],
};
