# Babysitter UI

This directory contains the React front-end for the experiment manager.
It is bootstrapped with [Vite](https://vitejs.dev/) and uses Tailwind CSS for basic styling.

## Development

1. Install dependencies:
   ```bash
   npm install
   ```
2. Start the development server:
   ```bash
   npm run dev
   ```
   The application will be available at `http://localhost:5173` by default.

The UI displays a table of mock jobs with sortable columns. Clicking a row
navigates to a job detail page which fetches and displays the full
configuration for that job.
