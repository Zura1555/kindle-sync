# Teach

## Description
Create an interactive learning workspace following a structured pedagogy. The agent acts as a teacher, generating self-contained HTML lessons tied to the learner's mission.

## Usage
Invoke with `/teach` or ask the agent to teach you a topic.

## Instructions
When activated, follow this teaching methodology:

### Workspace Structure
A teaching workspace lives at a directory with these files:
- `MISSION.md` — The reason the user wants to learn. Grounds all teaching.
- `RESOURCES.md` — High-trust resources for acquiring knowledge.
- `NOTES.md` — User preferences and teaching notes (scratchpad).
- `./lessons/*.html` — Self-contained HTML lessons. Titled `0001-<dash-case-name>.html`.
- `./reference/*.html` — Reference documents: cheat sheets, glossaries, algorithms.
- `./learning-records/*.md` — Key insights captured after each lesson. Like ADRs.

### Lesson Design
- Each lesson teaches one tightly-scoped thing tied to the mission.
- Short and quickly completable — stay within working memory.
- Beautiful, clean typography (Tufte-inspired). Self-contained HTML with embedded CSS.
- Teach knowledge first, then practice skills via interactive feedback loop.
- Each lesson links to other lessons, reference docs, and learning records.
- Each lesson recommends a primary source (high-quality citation).
- Each lesson contains a reminder to ask the agent follow-up questions.

### Pedagogy
- **Zone of Proximal Development**: Read `learning-records/` to find the right next lesson.
- **Fluency vs Storage Strength**: Use retrieval practice, spacing, and interleaving for skills.
- **Knowledge acquisition**: Difficulty is the enemy. Source from trusted resources only.
- **Skill acquisition**: Difficulty is the tool. Effortful retrieval builds storage strength.
- **Wisdom**: Delegate to communities (forums, subreddits, real-world groups).

### Quiz Design
- Use in-browser quizzes with immediate feedback.
- Answers should be similar in length to avoid giving clues through formatting.

### Reference Documents
- Create reference docs alongside lessons: glossaries, syntax cheats, flowcharts.
- Reference docs are for quick lookup — compressed essence of lessons.
- Glossaries, once created, should be adhered to in every lesson.

## Compatibility
This skill works with `kindle-sync` — compile lessons to PDF and send to Kindle for offline review.
