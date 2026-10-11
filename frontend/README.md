# BackedCV frontend

React + TypeScript screen for BackedCV: paste a job posting, add your CV, and see whether the job is worth applying to.

## Development

1. Start the backend on port 8000.
2. In this folder, run `npm install` (first time only) and then `npm run dev`.

The dev server proxies `/api` to `http://127.0.0.1:8000`.

## Build

`npm run build` writes `dist/`. FastAPI serves that folder at `/`.
