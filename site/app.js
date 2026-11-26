const sidebar = document.querySelector('#sidebar');
const toggle = document.querySelector('#menu-toggle');
const backdrop = document.querySelector('#backdrop');
let frame = document.querySelector('#reader');

document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  frame.focus();
});

function setMenu(open) {
  sidebar.classList.toggle('open', open);
  toggle.setAttribute('aria-expanded', String(open));
  toggle.setAttribute('aria-label', open ? 'Close course menu' : 'Open course menu');
  backdrop.hidden = !open;
  if (open) sidebar.querySelector('[aria-current="page"]')?.focus();
}

toggle.addEventListener('click', () => setMenu(toggle.getAttribute('aria-expanded') !== 'true'));
backdrop.addEventListener('click', () => { setMenu(false); toggle.focus(); });
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
    setMenu(false);
    toggle.focus();
  }
});
matchMedia('(min-width: 761px)').addEventListener('change', () => setMenu(false));

async function init() {
  const response = await fetch('course.json');
  if (!response.ok) throw new Error('Course not available');
  const { courses } = await response.json();
  const courseSelect = document.querySelector('#course-select');
  const topicSelect = document.querySelector('#topic-select');
  courseSelect.replaceChildren(...courses.map(course => new Option(course.title, course.id)));
  courseSelect.disabled = false;
  const navigation = document.querySelector('#navigation');
  let course;
  let lessons;
  let unit;

  courseSelect.addEventListener('change', () => {
    const selected = courses.find(item => item.id === courseSelect.value);
    location.hash = encodeURIComponent(selected.pages[0].path);
  });
  topicSelect.addEventListener('change', () => {
    const first = lessons.find(page => page.topic === topicSelect.value);
    location.hash = encodeURIComponent(first.path);
  });

  function renderCourse(selected) {
    course = selected;
    unit = course.unit || 'Lessons';
    lessons = course.pages.filter(page => page.section === unit);
    const topics = [...new Set(lessons.map(page => page.topic))];
    courseSelect.value = course.id;
    document.querySelector('#course-title').textContent = course.title;
    document.querySelector('#breadcrumb-course').textContent = course.title;
    document.querySelector('#course-count').textContent = `${lessons.length} ${(lessons.length === 1 ? unit.slice(0, -1) : unit).toLowerCase()} · ${topics.length} ${topics.length === 1 ? 'topic' : 'topics'}`;
    topicSelect.replaceChildren(new Option('Choose a topic', ''), ...topics.map(topic => new Option(topic, topic)));
    topicSelect.options[0].disabled = true;
    document.querySelector('#topic-control').hidden = !topics.length;
    navigation.replaceChildren();
    let lastSection;
    let lastTopic;
    let lessonNumber = 0;
    for (const page of course.pages) {
      if (page.section !== lastSection) {
        const heading = document.createElement('h2');
        heading.textContent = page.section;
        navigation.append(heading);
        lastSection = page.section;
      }
      if (page.section === unit && page.topic !== lastTopic) {
        if (topics.length > 1 || page.topic !== 'General') {
          const heading = document.createElement('h3');
          heading.textContent = page.topic;
          navigation.append(heading);
        }
        lastTopic = page.topic;
      }
      const link = document.createElement('a');
      link.href = `#${encodeURIComponent(page.path)}`;
      const number = document.createElement('span');
      number.className = 'nav-number';
      number.textContent = page.section === unit ? String(++lessonNumber).padStart(2, '0') : '—';
      const title = document.createElement('span');
      title.textContent = page.title;
      link.append(number, title);
      navigation.append(link);
    }
    if (!lessons.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = `No ${unit.toLowerCase()} yet. Add numbered HTML files to ${unit.toLowerCase()}/ and rebuild.`;
      navigation.append(empty);
    }
  }

  function navigate() {
    const selected = courses.find(item => item.pages.some(page => `#${encodeURIComponent(page.path)}` === location.hash)) || courses[0];
    if (course !== selected) renderCourse(selected);
    const index = course.pages.findIndex(page => `#${encodeURIComponent(page.path)}` === location.hash);
    const current = index < 0 ? 0 : index;
    const page = course.pages[current];
    topicSelect.value = page.topic || '';
    document.title = `${page.title} · ${course.title}`;
    document.querySelector('#current-section').textContent = page.section === unit ? `${page.topic === 'General' ? '' : page.topic + ' · '}${unit.slice(0, -1)} ${lessons.indexOf(page) + 1}` : page.title;
    navigation.querySelectorAll('a').forEach(link => {
      if (link.hash === `#${encodeURIComponent(page.path)}`) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    // A fresh frame avoids adding iframe-only entries to the browser's Back history.
    const nextFrame = frame.cloneNode(false);
    nextFrame.title = page.title;
    nextFrame.src = page.path;
    nextFrame.hidden = false;
    frame.replaceWith(nextFrame);
    frame = nextFrame;
    document.querySelector('#notice').hidden = true;
    document.querySelector('#page-navigation').hidden = false;
    document.querySelector('#position').textContent = `${current + 1} / ${course.pages.length}`;
    for (const [id, neighbor] of [['previous', course.pages[current - 1]], ['next', course.pages[current + 1]]]) {
      const link = document.getElementById(id);
      link.hidden = !neighbor;
      if (neighbor) {
        link.href = `#${encodeURIComponent(neighbor.path)}`;
        link.querySelector('.page-title').textContent = neighbor.title;
      } else link.removeAttribute('href');
    }
    if (toggle.getAttribute('aria-expanded') === 'true') {
      setMenu(false);
      toggle.focus();
    }
  }
  window.addEventListener('hashchange', navigate);
  navigate();
}

init().catch(() => {
  document.querySelector('#notice').textContent = 'Unable to load this course. Refresh to try again. For local previews, build the site and serve the output over HTTP.';
});
