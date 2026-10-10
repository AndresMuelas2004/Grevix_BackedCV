# BackedCV

Paste a job posting and upload your CV. BackedCV tells you whether the job is worth applying to, what is likely to screen you out, and rebuilds your CV for that job without inventing anything.

> Work in progress. Built solo during the Grevix AfterCode 24-hour hackathon (October 2026).

## Not a new idea

CV-to-job-posting matchers already exist (Jobscan, Rezi, Teal and others). BackedCV is inspired by Jobscan's core flow: scan, optimize, build. What I focus on:

- **Knockout requirements first:** work authorization, licenses, minimum years or location are flagged as likely screening questions, not mixed into a percentage.
- **Every match has a receipt:** each requirement points to the exact CV line that supports it.
- **A score you can audit:** published weights; every point is explained.
- **No invented experience:** every suggested edit is checked against real CV lines, and unsupported edits cannot be accepted.

Each of these exists separately in other tools; I did not find one that combines them.

## Status

Sections for setup, architecture, the Challenge Cards and the demo are added as the project is built.

## License

MIT
