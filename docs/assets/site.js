(function () {
  const GITHUB_REPO = 'https://github.com/kahinimehta/Quorum';

  /** Root on neurodiscover.github.io; /Quorum/ when served as a project Pages site. */
  function siteBase() {
    const parts = (window.location.pathname || '/').split('/').filter(Boolean);
    if (parts.length >= 2 && /^(quorum)$/i.test(parts[0])) {
      return '/' + parts[0] + '/';
    }
    return '/';
  }

  function href(path) {
    const base = siteBase();
    if (path.startsWith('http')) return path;
    const clean = path.replace(/^\//, '');
    return base === '/' ? clean : base + clean;
  }

  const NAV = [
    {
      title: 'Project',
      items: [
        { page: 'index', path: 'index.html', label: 'Overview' },
        { page: 'workflow', path: 'workflow.html', label: 'Workflow' },
        { page: 'decisions', path: 'decisions.html', label: 'Architecture' },
        { page: 'team', path: 'team.html', label: 'Team' },
      ],
    },
    {
      title: 'Developers',
      items: [
        { page: 'guides', path: 'guides.html', label: 'Guides & CLI' },
        { page: 'database', path: 'database.html', label: 'Database' },
        { page: 'api', path: 'api.html', label: 'API' },
      ],
    },
    {
      title: 'Application',
      items: [
        { page: 'dashboard', path: 'dashboard.html', label: 'Dashboard' },
        { page: 'github', path: GITHUB_REPO, label: 'Source on GitHub', external: true },
      ],
    },
  ];

  function renderSidebar(activePage) {
    const aside = document.getElementById('siteSidebar');
    if (!aside) return;

    const home = href('index.html');
    let html = '<div class="sidebar-brand">'
      + `<a href="${home}">NeuroDiscover AI</a>`
      + '<small>Quorum · Parkinson\'s discovery</small></div>';

    NAV.forEach(section => {
      html += `<div class="nav-section"><div class="nav-section-title">${section.title}</div><ul class="nav-list">`;
      section.items.forEach(item => {
        const url = href(item.path);
        const cls = [
          item.page === activePage ? 'active' : '',
          item.external ? 'external' : '',
        ].filter(Boolean).join(' ');
        const ext = item.external ? ' target="_blank" rel="noopener noreferrer"' : '';
        html += `<li><a class="${cls}" href="${url}"${ext}>${item.label}</a></li>`;
      });
      html += '</ul></div>';
    });

    html += '<div class="sidebar-footer">'
      + `<a href="${GITHUB_REPO}">Quorum repo</a> · `
      + '<a href="' + href('guides.html') + '#pages">GitHub Pages</a>'
      + '</div>';
    aside.innerHTML = html;
  }

  function initMobileNav() {
    const toggle = document.getElementById('navToggle');
    const sidebar = document.getElementById('siteSidebar');
    if (!toggle || !sidebar) return;
    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
    document.addEventListener('click', (e) => {
      if (!sidebar.classList.contains('open')) return;
      if (!sidebar.contains(e.target) && e.target !== toggle) {
        sidebar.classList.remove('open');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.getAttribute('data-page') || 'index';
    renderSidebar(page);
    initMobileNav();
  });
})();
