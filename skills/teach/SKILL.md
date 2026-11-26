---
name: teach
description: Teaches any topic by building a learning workspace of short, interactive HTML lessons, reference docs, and learning records tied to the learner's mission. Use when the user asks to learn, study, or be taught a topic, or invokes /teach.
---

# Teach

## Description
Create an interactive learning workspace following a structured pedagogy. The agent acts as a teacher, generating self-contained HTML lessons tied to the learner's mission.

## Usage
Invoke with `/teach` or ask the agent to teach you a topic.

## Instructions
When activated, follow this teaching methodology:

### Workspace Structure
A teaching workspace lives at a directory with these files:
- `MISSION.md` — The reason the user wants to learn. Grounds all teaching. Its first line is `# Mission: <Topic>`; kindle-sync uses `<Topic>` as the book title.
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
- Put the answers in the markup, not only in JavaScript: kindle-sync strips scripts, prints the options as a lettered list, and moves the answers to an answer key at the end of the chapter. Mark the correct button with `data-correct` and give every button a `data-explain` with its feedback:

```html
<div class="quiz-block">
  <h3>Check Your Understanding</h3>
  <div class="q">Q1: Question text?</div>
  <div class="options">
    <button class="opt" data-explain="No. Why this is wrong.">Option one</button>
    <button class="opt" data-correct data-explain="Correct! Why this is right.">Option two</button>
  </div>
  <div class="feedback"></div>
</div>
<script>
document.querySelectorAll('.quiz-block .options').forEach(opts => {
  const btns = [...opts.querySelectorAll('button.opt')];
  const fb = opts.nextElementSibling;
  btns.forEach(b => b.addEventListener('click', () => {
    const ok = b.hasAttribute('data-correct');
    btns.forEach(x => { x.disabled = true; if (x.hasAttribute('data-correct')) x.classList.add('correct'); });
    if (!ok) b.classList.add('incorrect');
    fb.textContent = b.dataset.explain || (ok ? 'Correct!' : 'Not quite.');
    fb.className = 'feedback show ' + (ok ? 'correct' : 'incorrect');
  }));
});
</script>
```

### Reference Documents
- Create reference docs alongside lessons: glossaries, syntax cheats, flowcharts.
- Reference docs are for quick lookup — compressed essence of lessons.
- Glossaries, once created, should be adhered to in every lesson.

## Compatibility
This skill works with `kindle-sync` — compile lessons into a Kindle book and send it to a Kindle for offline review. For long-form reading written chapter by chapter, use the `book` skill instead.
