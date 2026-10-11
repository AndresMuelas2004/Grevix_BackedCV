# Real-world feedback (Challenge Card 2)

Where I shared BackedCV, what people said, and what I changed because of it. Every quote here is real and comes with a screenshot in [screenshots/](screenshots/). Names and profile photos are blurred unless the person agreed to be named.

## Where I shared it

All on 2026-10-11 (Madrid time), with the live demo at [backedcv.onrender.com](https://backedcv.onrender.com) and the same three questions: would you trust the verdict, which part helps and which is noise, and what would stop you from using it on a real application.

| Where | Link | Proof |
|---|---|---|
| LinkedIn, mentioning GREVIX, with the 2-minute demo video | [post](https://www.linkedin.com/feed/update/urn:li:activity:7515057764193263616/) | [01-linkedin-post.png](screenshots/01-linkedin-post.png) |
| X, mentioning @Grevixofficial, with the video | [post](https://x.com/Andresmuel74552/status/2109301122103971871) | [02-x-post.png](screenshots/02-x-post.png) |
| Reddit, r/LangChain | [post](https://www.reddit.com/r/LangChain/comments/1x39r2p/i_built_a_langgraph_app_that_reads_a_job_posting/) | [03-reddit-langchain.png](screenshots/03-reddit-langchain.png) |
| Reddit, r/hackathon | [post](https://www.reddit.com/r/hackathon/comments/1x39u1b/my_24hour_hackathon_project_backedcv_which_tells/) | [04-reddit-hackathon.png](screenshots/04-reddit-hackathon.png) |
| The GREVIX AfterCode participants' WhatsApp group, at 17:12 | (private group) | [05-whatsapp-group.png](screenshots/05-whatsapp-group.png) (other members' names and numbers blurred) |
| A public feedback form in this repository | [form](https://github.com/AndresMuelas2004/Grevix_BackedCV/issues/new?template=feedback.yml) | |

Reddit's automatic filters removed both Reddit posts within minutes, because the account is new. I asked the moderators to review them. The r/hackathon moderator approved the post at 17:15; my own edit to tidy its wording triggered the filter again, and I asked for a second review.

Before asking for feedback, I gave it: I tried seven other participants' projects (as a user and by reading their code) and left honest notes on four LinkedIn posts, two GitHub issues ([ClariBite](https://github.com/tanishkaai92-design/Grevix_ClariBite/issues/1), [TRACE](https://github.com/NebulaScript-codeX/Grevix_Trace-system/issues/1)) and one feedback form. Security problems I noticed were kept out of public comments.

## What people said

Three people answered within the first hour, all GREVIX AfterCode participants who tried the live demo.

**A. A participant, by WhatsApp direct message (17:36)** ([06-feedback-whatsapp-dm.png](screenshots/06-feedback-whatsapp-dm.png); name, number and the CV they tried are blurred):

> Hey, andres. i saw your project the "BackedCV" and the output is kinda confusing. i tried a random resume and a job posting and it was way too overwhelming
>
> also, you should improve the landing page ui

**B. Another participant, in a comment on my LinkedIn post (about 17:40)** ([07-feedback-linkedin-comment.png](screenshots/07-feedback-linkedin-comment.png); name and photo blurred):

> Really sharp take on ATS screening! Focusing on hidden disqualifiers (visa sponsorship, tech recency) and strictly refusing to invent experience is a huge differentiator over generic keyword matchers.
>
> Three quick thoughts on your questions:
> 1. Verdict Trust: Binary reasons backed by direct side-by-side quotes (job snippet vs. CV line) make the verdict indisputable.
> 2. Signal vs Noise: Clearly separate "Hard Dealbreakers" (legal/visa bans) from "Soft Preferences" so applicants don't self-reject from flexible roles.
> 3. Adoption Barrier: Multi-column PDFs can distort dates; a quick preview showing how employment timelines were parsed would eliminate doubt on recency checks.

**C. A third participant, by WhatsApp direct message (17:52)** ([08-feedback-whatsapp-dm2.png](screenshots/08-feedback-whatsapp-dm2.png); name and number blurred):

> Just gonna through your website its giving reviews a bit too lengthy i would highly recommend that change the ai and make it as it returns in short manner

A and C say the same thing in different words: the report is too much to take in. B says what would make it trustworthy. I took A and C as the main problem and B as the shape of the fix.

## What I changed

Before building anything I drew the new report as a clickable mockup and approved it. Each change below names the comment it answers.

| Before | After |
|---|---|
| [The old report](screenshots/09-before-report.png): everything at once, 8,262 pixels tall on a laptop screen | [The new report](screenshots/10-after-report.png): 2,984 pixels, the verdict and the questions first, the details folded ([on a phone](screenshots/13-after-report-phone.png)) |
| [The old first screen](screenshots/11-before-landing.png): two boxes and a button | [The new first screen](screenshots/12-after-landing.png): an example report plays before you upload anything |

Both reports are for the same sample (a Platform Engineer posting with a buried no-sponsorship sentence, and a CV in Valencia).

1. **The report goes from simple to complex** (A: "way too overwhelming"; C: "a bit too lengthy"). The top now holds only the verdict in one sentence and one number. Right under it come the yes/no questions that can change the verdict, and "Improve my CV" stays locked until they are answered. Then a numbered list, "What to fix, most important first", with one line per problem and the detail behind "See why". What already works comes after that, and everything else (all requirements, the exact-word score, how the score is worked out, the CV as a parser reads it) is folded into "Details".
2. **Deal-breakers apart from preferences** (B, point 2). The list has three tiers with text labels, not just colours: "Could rule you out", "Serious gap", "Worth improving". Only a legal ban (work permit, security clearance, professional license) gives "Likely screened out" on its own. A missing language or degree caps the verdict at "Long shot", and a nice-to-have is never shown as a deal-breaker.
3. **The posting's sentence next to your CV line** (B, point 1). Every item opens to "The job says" beside "Your CV says", plus one thing to do.
4. **How we read your dates** (B, point 3). A table shows each job's dates as read and the time counted. A missing month says "month unknown" and is never guessed, and a date glued to a city name by a PDF ("Bilbao, SpainApr 2026") is now read correctly.
5. **Short texts** (C). Every explanation the app writes is one plain sentence of about 20 words, without internal IDs.
6. **The first screen shows the result** (A: "you should improve the landing page ui"). Before anyone uploads anything, a short example of the report plays at the top of the page.

Once the changes were live, I answered the LinkedIn comment with what had changed because of it.

Beyond these comments I also had an AI test the app. That is not real-world feedback and I don't count it for this card, but it found real bugs, which I fixed: a blank line in the posting could move the score from 55 to 72, a missing "2+ years" counted as a small partial, the same question was asked twice, a 2023 degree was marked "aging", and some suggestions only stuffed posting words into a line.

## What I did not change, and why

- **I didn't cut the evidence, I folded it.** C asked for shorter output, and B said the side-by-side quotes are what make a verdict trustworthy. Deleting the detail would answer one comment by breaking the other, so it moved down, behind "See why" and "Details".
- **I didn't switch to a bigger AI model.** C suggested changing the AI. The texts are shorter because of the prompts and the layout. Every call still uses the cheap model, to stay inside the event's API budget.
- **No Spanish interface yet.** The AI-run test asked for it when the CV and posting are in Spanish. The analysis reads Spanish input, but translating and re-testing every screen didn't fit in the time left.
