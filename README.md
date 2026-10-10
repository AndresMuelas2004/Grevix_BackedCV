# BackedCV

> Work in progress. Built solo during the Grevix AfterCode 24-hour hackathon (October 2026).

I'm building BackedCV. You paste a job posting, upload your CV, and it tells you if the job is worth applying to, what is likely to get you screened out, and how to tailor your CV to that posting without inventing anything.

## Why

People send dozens of applications blind and never find out why they were rejected. Most automatic rejections come from knockout questions (work permit, licenses, minimum years, location), not from keyword counts. But the popular tools give you an opaque keyword score, and plenty of AI resume writers happily add experience you don't have. I'm moving my career into AI and job hunting right now, so I'm user number one.

## How it works

- It reads the CV (PDF or DOCX) and shows the text the way screening software sees it.
- It splits the posting into requirements, flags the knockouts and the unrealistic ones, and links each requirement to the exact CV line that proves it, by keyword or by meaning.
- The score uses published weights, so every point has a reason.
- Each suggested rewrite is checked against real lines of the CV, and the ones with no backing can't be accepted.
- At the end an agent builds the new CV (DOCX and PDF) from the accepted edits only.

## Stack

Python, FastAPI, LangGraph, LangChain, OpenAI structured outputs, LangSmith and React.

## Not a new idea

Jobscan, Rezi and Teal already exist, and BackedCV is inspired by Jobscan's scan, optimize and build flow. What I haven't found is a tool that puts knockout detection, line-by-line evidence and a no-invention rule together.

## Transparency note

At registration I submitted a different idea (website URL to promo video). I dropped it before the event started, with no code written for it, and chose this problem instead. BackedCV is being built from scratch during these 24 hours.

## Status

Sections for setup, architecture, the Challenge Cards and the demo are added as the project is built. Decisions are recorded in [docs/decision-log.md](docs/decision-log.md).

## License

MIT
