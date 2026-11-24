/**
 * HireNexa Enterprise Navigation, Palette & Interaction Engine
 * Features:
 *  - WCAG AA Keyboard Navigation (Arrows, Enter, Escape, Tab Trap)
 *  - Responsive Mobile Offcanvas Drawer
 *  - Ctrl+K Command Palette with Live Instant Search
 *  - Dark / Light / System Theme Engine
 *  - Robust Dropdown Management with Zero Layout Overflow
 */

(function() {
  'use strict';

  // ---------------------------------------------------------------------------
  // 1. THEME ENGINE (Runs immediately)
  // ---------------------------------------------------------------------------
  window.applyStoredTheme = function() {
    const saved = localStorage.getItem('hirenexa_theme') || 'system';
    if (saved === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else if (saved === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    } else {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    }
  };

  window.setThemeMode = function(mode) {
    localStorage.setItem('hirenexa_theme', mode);
    window.applyStoredTheme();

    // Update active state on any theme buttons
    document.querySelectorAll('.theme-select-card').forEach(card => {
      const input = card.querySelector('input[type="radio"]');
      if (input) {
        if (input.value === mode) {
          card.classList.add('selected');
          input.checked = true;
        } else {
          card.classList.remove('selected');
        }
      }
    });
  };

  // ---------------------------------------------------------------------------
  // 2. DROPDOWN CONTROLLER
  // ---------------------------------------------------------------------------
  const dropdownPairs = [
    { btnId: 'exploreDropdownBtn', menuId: 'exploreDropdownMenu' },
    { btnId: 'moreDropdownBtn', menuId: 'moreDropdownMenu' },
    { btnId: 'notifDropdownBtn', menuId: 'notifDropdownMenu' },
    { btnId: 'postDropdownBtn', menuId: 'postDropdownMenu' },
    { btnId: 'profileDropdownBtn', menuId: 'profileDropdownMenu' }
  ];

  window.closeAllDropdowns = function() {
    dropdownPairs.forEach(pair => {
      const btn = document.getElementById(pair.btnId);
      const menu = document.getElementById(pair.menuId);
      if (menu) menu.classList.remove('show');
      if (btn) btn.setAttribute('aria-expanded', 'false');
    });
  };

  function setupDropdowns() {
    dropdownPairs.forEach(pair => {
      const btn = document.getElementById(pair.btnId);
      const menu = document.getElementById(pair.menuId);
      if (!btn || !menu) return;

      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        const isOpen = menu.classList.contains('show');
        window.closeAllDropdowns();
        if (!isOpen) {
          menu.classList.add('show');
          btn.setAttribute('aria-expanded', 'true');
          // Focus first focusable item for accessibility
          const firstItem = menu.querySelector('a, button, input');
          if (firstItem) firstItem.focus();
        }
      });

      // Keyboard arrow navigation inside dropdown
      menu.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
          window.closeAllDropdowns();
          btn.focus();
          return;
        }

        const items = Array.from(menu.querySelectorAll('a, button:not([disabled])'));
        const currentIndex = items.indexOf(document.activeElement);

        if (e.key === 'ArrowDown') {
          e.preventDefault();
          const nextIndex = (currentIndex + 1) % items.length;
          items[nextIndex].focus();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          const prevIndex = (currentIndex - 1 + items.length) % items.length;
          items[prevIndex].focus();
        }
      });
    });

    // Close on outside click
    document.addEventListener('click', function(e) {
      if (!e.target.closest('.nav-dropdown-wrapper')) {
        window.closeAllDropdowns();
      }
    });

    // Close on Escape anywhere
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        window.closeAllDropdowns();
        closeMobileDrawer();
        closeCmdPalette();
      }
    });
  }

  // ---------------------------------------------------------------------------
  // 3. SWITCH PORTAL SUBMENU
  // ---------------------------------------------------------------------------
  window.togglePortalSubmenu = function(e) {
    if (e) e.stopPropagation();
    const container = document.getElementById('portalSubmenuContainer');
    const chevron = document.getElementById('portalSubmenuChevron');
    const toggleBtn = document.getElementById('portalSubmenuToggle');
    if (!container) return;

    if (container.style.display === 'none' || container.style.display === '') {
      container.style.display = 'block';
      if (chevron) chevron.style.transform = 'rotate(90deg)';
      if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'true');
    } else {
      container.style.display = 'none';
      if (chevron) chevron.style.transform = 'rotate(0deg)';
      if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'false');
    }
  };

  // ---------------------------------------------------------------------------
  // 4. MOBILE DRAWER CONTROLLER (<1024px)
  // ---------------------------------------------------------------------------
  window.openMobileDrawer = function() {
    window.closeAllDropdowns();
    const drawer = document.getElementById('mobileDrawer');
    const backdrop = document.getElementById('mobileDrawerBackdrop');
    const openBtn = document.getElementById('mobileDrawerOpenBtn');

    if (drawer && backdrop) {
      backdrop.style.display = 'block';
      setTimeout(() => drawer.classList.add('open'), 10);
      document.body.style.overflow = 'hidden';
      if (openBtn) openBtn.setAttribute('aria-expanded', 'true');

      // Focus first actionable link
      const firstFocus = drawer.querySelector('button, a');
      if (firstFocus) firstFocus.focus();
    }
  };

  window.closeMobileDrawer = function() {
    const drawer = document.getElementById('mobileDrawer');
    const backdrop = document.getElementById('mobileDrawerBackdrop');
    const openBtn = document.getElementById('mobileDrawerOpenBtn');

    if (drawer && backdrop) {
      drawer.classList.remove('open');
      setTimeout(() => { backdrop.style.display = 'none'; }, 250);
      document.body.style.overflow = '';
      if (openBtn) {
        openBtn.setAttribute('aria-expanded', 'false');
        openBtn.focus();
      }
    }
  };

  function setupMobileDrawer() {
    const openBtn = document.getElementById('mobileDrawerOpenBtn');
    const closeBtn = document.getElementById('mobileDrawerCloseBtn');
    if (openBtn) openBtn.addEventListener('click', window.openMobileDrawer);
    if (closeBtn) closeBtn.addEventListener('click', window.closeMobileDrawer);

    // Focus trap inside drawer
    const drawer = document.getElementById('mobileDrawer');
    if (drawer) {
      drawer.addEventListener('keydown', function(e) {
        if (e.key === 'Tab') {
          const focusable = drawer.querySelectorAll('a, button, input');
          if (focusable.length === 0) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];

          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // 5. COMMAND PALETTE (Ctrl+K)
  // ---------------------------------------------------------------------------
  const searchIndex = [
    // Primary Pages & Dashboards
    { title: 'Home', desc: 'Platform landing page & latest highlights', url: '/', category: 'Pages', icon: '🏠' },
    { title: 'Find Jobs', desc: 'Search active job vacancies with verified salaries', url: '/jobs/', category: 'Jobs', icon: '💼' },
    { title: 'Verified Companies', desc: 'Browse enterprise organizations & tech teams', url: '/companies/', category: 'Pages', icon: '🏢' },
    { title: 'Freelance Project Gigs', desc: 'Browse contract gigs & freelance briefs', url: '/projects/', category: 'Freelance', icon: '💻' },
    { title: 'HireNexa AI Intelligence Assistant', desc: 'Interactive LLM assistant for career & recruitment', url: '/ai/', category: 'AI Tools', icon: '⚡' },
    { title: 'AI Resume Analyzer', desc: 'Instant ATS scoring, keyword match & skill gaps', url: '/resume-analyzer/', category: 'AI Tools', icon: '✨' },
    { title: 'Career Resources', desc: 'Guides, interview questions & salary benchmarking', url: '/resources/', category: 'Resources', icon: '📚' },
    { title: 'News & Announcements', desc: 'Platform notices, recruitment bulletins', url: '/news/', category: 'News', icon: '📢' },
    
    // Dashboards & Portals
    { title: 'Platform Owner Control Center', desc: 'Admin governance, analytics, companies & users', url: '/owner/', category: 'Portals', icon: '🛡️' },
    { title: 'HR Recruiter Workspace', desc: 'Post vacancies, review applicants, schedule rounds', url: '/hr/', category: 'Portals', icon: '👥' },
    { title: 'Company Admin Dashboard', desc: 'Manage company branding, seats & active jobs', url: '/company/', category: 'Portals', icon: '🏢' },
    { title: 'Candidate Career Portal', desc: 'Job applications, interviews, saved jobs', url: '/candidate/', category: 'Portals', icon: '🎓' },
    { title: 'Freelancer Dashboard', desc: 'Active contracts, gig proposals, earnings', url: '/freelancer/', category: 'Portals', icon: '💻' },

    // Settings Navigation
    { title: 'Settings: My Profile', desc: 'Photo, headline, location, bio, portfolio URLs', url: '/settings/profile/', category: 'Settings', icon: '👤' },
    { title: 'Settings: Account & Email', desc: 'Username, email change with OTP, timezone, locale', url: '/settings/account/', category: 'Settings', icon: '⚙️' },
    { title: 'Settings: Security & 2FA', desc: 'Argon2id password, Two-Factor Auth, active sessions', url: '/settings/security/', category: 'Settings', icon: '🔒' },
    { title: 'Settings: Notifications Preferences', desc: 'Email digest cadence, in-app alerts, quiet hours', url: '/settings/notifications/', category: 'Settings', icon: '🔔' },
    { title: 'Settings: Theme & Appearance', desc: 'Light, dark, system theme, font scale, compact mode', url: '/settings/appearance/', category: 'Settings', icon: '🎨' },
    { title: 'Settings: Privacy & GDPR', desc: 'Search visibility, hide phone/email, GDPR export', url: '/settings/privacy/', category: 'Settings', icon: '🛡️' },
    { title: 'Settings: Platform Settings (Owner)', desc: 'SMTP diagnostics, RBAC matrix, feature toggles', url: '/settings/platform/', category: 'Settings', icon: '⚙️' },

    // Quick Actions
    { title: 'Action: Post New Job Vacancy', desc: 'Publish open requisition to talent pool', url: '/jobs/create/', category: 'Actions', icon: '➕' },
    { title: 'Action: Upload New Resume', desc: 'Upload verified PDF/DOCX for AI extraction', url: '/resumes/upload/', category: 'Actions', icon: '📄' },
    { title: 'Action: Post Platform Notice', desc: 'Broadcast bulletin across platform', url: '/news/create/', category: 'Actions', icon: '📢' },
    { title: 'Action: Switch to Dark Mode', desc: 'Activate obsidian dark theme immediately', action: 'theme_dark', category: 'Actions', icon: '🌙' },
    { title: 'Action: Switch to Light Mode', desc: 'Activate bright light theme', action: 'theme_light', category: 'Actions', icon: '☀️' }
  ];

  let activeResultIndex = 0;
  let currentFilteredList = [];

  window.openCmdPalette = function() {
    window.closeAllDropdowns();
    closeMobileDrawer();
    const backdrop = document.getElementById('cmdPaletteBackdrop');
    const input = document.getElementById('cmdPaletteInput');
    if (!backdrop || !input) return;

    backdrop.style.display = 'flex';
    input.value = '';
    renderPaletteResults(searchIndex);
    input.focus();
    document.body.style.overflow = 'hidden';
  };

  window.closeCmdPalette = function() {
    const backdrop = document.getElementById('cmdPaletteBackdrop');
    if (backdrop) {
      backdrop.style.display = 'none';
      document.body.style.overflow = '';
    }
  };

  function renderPaletteResults(items) {
    const container = document.getElementById('cmdPaletteResults');
    if (!container) return;
    currentFilteredList = items;
    activeResultIndex = 0;

    if (items.length === 0) {
      container.innerHTML = `
        <div class="cmd-no-results">
          <span style="font-size: 24px; display: block; margin-bottom: 8px;">🔍</span>
          <p>No matching commands or pages found. Try searching for "Jobs", "Profile", or "Security".</p>
        </div>
      `;
      return;
    }

    // Group by category
    const grouped = {};
    items.forEach((item, idx) => {
      if (!grouped[item.category]) grouped[item.category] = [];
      grouped[item.category].push({ item, idx });
    });

    let html = '';
    let globalIndex = 0;
    for (const [cat, list] of Object.entries(grouped)) {
      html += `<div class="cmd-cat-title">${cat}</div>`;
      list.forEach(({ item }) => {
        const isSelected = globalIndex === activeResultIndex ? 'selected' : '';
        html += `
          <div class="cmd-result-row ${isSelected}" data-index="${globalIndex}" onclick="selectPaletteItem(${globalIndex})">
            <span class="cmd-item-icon">${item.icon}</span>
            <div class="cmd-item-meta">
              <span class="cmd-item-title">${item.title}</span>
              <span class="cmd-item-desc">${item.desc}</span>
            </div>
            <span class="cmd-enter-hint">↵</span>
          </div>
        `;
        globalIndex++;
      });
    }

    container.innerHTML = html;
  }

  function filterPalette(query) {
    const q = query.toLowerCase().trim();
    if (!q) {
      renderPaletteResults(searchIndex);
      return;
    }

    const filtered = searchIndex.filter(item => {
      return item.title.toLowerCase().includes(q) ||
             item.desc.toLowerCase().includes(q) ||
             item.category.toLowerCase().includes(q);
    });

    renderPaletteResults(filtered);
  }

  window.selectPaletteItem = function(index) {
    if (index < 0 || index >= currentFilteredList.length) return;
    const target = currentFilteredList[index];
    closeCmdPalette();

    if (target.action === 'theme_dark') {
      window.setThemeMode('dark');
    } else if (target.action === 'theme_light') {
      window.setThemeMode('light');
    } else if (target.url) {
      window.location.href = target.url;
    }
  };

  function updatePaletteActiveHighlight() {
    const rows = document.querySelectorAll('.cmd-result-row');
    rows.forEach((row, i) => {
      if (i === activeResultIndex) {
        row.classList.add('selected');
        row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } else {
        row.classList.remove('selected');
      }
    });
  }

  function setupCommandPalette() {
    const trigger = document.getElementById('cmdPaletteTriggerBtn');
    if (trigger) trigger.addEventListener('click', window.openCmdPalette);

    // Global keyboard listener for Ctrl+K / Cmd+K
    document.addEventListener('keydown', function(e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const backdrop = document.getElementById('cmdPaletteBackdrop');
        if (backdrop && backdrop.style.display !== 'none') {
          closeCmdPalette();
        } else {
          window.openCmdPalette();
        }
      }
    });

    const input = document.getElementById('cmdPaletteInput');
    if (input) {
      input.addEventListener('input', function() {
        filterPalette(this.value);
      });

      input.addEventListener('keydown', function(e) {
        if (currentFilteredList.length === 0) return;

        if (e.key === 'ArrowDown') {
          e.preventDefault();
          activeResultIndex = (activeResultIndex + 1) % currentFilteredList.length;
          updatePaletteActiveHighlight();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          activeResultIndex = (activeResultIndex - 1 + currentFilteredList.length) % currentFilteredList.length;
          updatePaletteActiveHighlight();
        } else if (e.key === 'Enter') {
          e.preventDefault();
          window.selectPaletteItem(activeResultIndex);
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // 6. NOTIFICATION BELL DYNAMIC MANAGER & MARK ALL READ
  // ---------------------------------------------------------------------------
  window.markAllNotificationsRead = function(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const btn = document.getElementById('markAllReadBtn');
    if (btn) {
      btn.innerText = 'Marking...';
      btn.disabled = true;
    }

    function getCsrfToken() {
      const match = document.cookie.match(/csrftoken=([^;]+)/);
      return match ? match[1] : '';
    }

    fetch('/notifications/mark-all-read/', {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCsrfToken()
      }
    })
    .then(res => res.json())
    .then(data => {
      const badge = document.getElementById('notifCountBadge');
      if (badge) {
        badge.innerText = '0';
        badge.style.display = 'none';
      }
      const pill = document.getElementById('notifCountPill');
      if (pill) pill.innerText = '0 new';

      document.querySelectorAll('.notif-row.unread').forEach(row => {
        row.classList.remove('unread');
      });
      document.querySelectorAll('.notif-dot.active').forEach(dot => {
        dot.classList.remove('active');
      });

      if (btn) {
        btn.innerText = '✓ All read';
        btn.style.opacity = '0.6';
      }
    })
    .catch(() => {
      // Fallback
      window.location.href = '/notifications/mark-all-read/';
    });
  };

  // ---------------------------------------------------------------------------
  // 7. INTEGRATED HEADER SEARCH BAR & INSTANT SUGGESTIONS
  // ---------------------------------------------------------------------------
  function setupHeaderSearch() {
    const input = document.getElementById('headerSearchInput');
    const form = document.getElementById('headerSearchForm');
    const clearBtn = document.getElementById('headerSearchClearBtn');
    const suggestionsBox = document.getElementById('headerSearchSuggestions');
    if (!input || !form) return;

    const suggestionsIndex = [
      { label: 'Full Stack Developer', sub: 'MCA / IT Engineering track', type: 'job', url: '/jobs/?q=Full+Stack+Developer' },
      { label: 'Python & Django Backend Architect', sub: 'Active company hiring', type: 'job', url: '/jobs/?q=Python' },
      { label: 'React & Frontend Engineer', sub: 'Remote & Hybrid roles', type: 'job', url: '/jobs/?q=React' },
      { label: 'HR Manager & Talent Acquisition', sub: 'MBA Management track', type: 'job', url: '/jobs/?q=HR+Manager' },
      { label: 'Data Scientist & ML Specialist', sub: 'Predictive intelligence & AI', type: 'job', url: '/jobs/?q=Data+Scientist' },
      { label: 'Cloud & DevOps Engineer', sub: 'AWS, Docker & CI/CD', type: 'job', url: '/jobs/?q=Cloud' },
      { label: 'IoT & Embedded Systems Engineer', sub: 'Deogarh, Odisha office', type: 'job', url: '/jobs/?q=IoT' },
      { label: 'Find Jobs Portal', sub: 'Explore all verified company openings', type: 'page', url: '/jobs/' },
      { label: 'Verified Companies', sub: 'Browse enterprise tech organizations', type: 'page', url: '/companies/' },
      { label: 'HireNexa AI Intelligence Assistant', sub: 'Interactive career co-pilot', type: 'tool', url: '/ai/' },
      { label: 'MCQ & Entrance Exam Preparation', sub: 'NIMCET, OJEE, CAT 16-question mocks', type: 'tool', url: '/entrance-prep/' },
      { label: 'Freelance Project Gigs', sub: 'Contract briefs & proposals', type: 'page', url: '/projects/' },
      { label: 'Career Resources & Interview Prep', sub: 'DSA guides & cheat sheets', type: 'page', url: '/resources/' }
    ];

    let activeSuggestionIndex = -1;
    let filteredSuggestions = [];

    function renderSuggestions(val) {
      if (!suggestionsBox) return;
      const q = val.trim().toLowerCase();
      if (!q) {
        suggestionsBox.style.display = 'none';
        return;
      }

      filteredSuggestions = suggestionsIndex.filter(item => 
        item.label.toLowerCase().includes(q) || item.sub.toLowerCase().includes(q)
      );

      if (filteredSuggestions.length === 0) {
        suggestionsBox.innerHTML = `
          <div class="header-suggestion-empty">
            <span style="font-size: 18px; display: block; margin-bottom: 4px;">🔍</span>
            <strong>No quick suggestions for "${escapeHTML(val)}"</strong>
            <p style="margin: 4px 0 0 0; font-size: 11.5px; color: #64748b;">Press <kbd style="background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-weight: 700; border: 1px solid #cbd5e1;">Enter</kbd> to search all jobs & company posts.</p>
          </div>
        `;
        suggestionsBox.style.display = 'block';
        return;
      }

      let html = '';
      filteredSuggestions.slice(0, 6).forEach((item, idx) => {
        const typeBadge = item.type === 'job' ? '💼 Job' : (item.type === 'tool' ? '⚡ Tool' : '📄 Page');
        html += `
          <a href="${item.url}" class="header-suggestion-item" data-idx="${idx}">
            <div class="suggestion-icon-wrap">${item.type === 'job' ? '💼' : (item.type === 'tool' ? '✨' : '🌐')}</div>
            <div class="suggestion-text-wrap">
              <div class="suggestion-title">${escapeHTML(item.label)}</div>
              <div class="suggestion-sub">${escapeHTML(item.sub)}</div>
            </div>
            <span class="suggestion-type-badge">${typeBadge}</span>
          </a>
        `;
      });
      suggestionsBox.innerHTML = html;
      suggestionsBox.style.display = 'block';
      activeSuggestionIndex = -1;
    }

    input.addEventListener('input', function() {
      if (this.value.trim().length > 0) {
        if (clearBtn) clearBtn.style.display = 'flex';
      } else {
        if (clearBtn) clearBtn.style.display = 'none';
      }
      renderSuggestions(this.value);
    });

    input.addEventListener('focus', function() {
      if (this.value.trim().length > 0) {
        renderSuggestions(this.value);
      }
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        input.value = '';
        clearBtn.style.display = 'none';
        if (suggestionsBox) suggestionsBox.style.display = 'none';
        input.focus();
      });
    }

    // Keyboard navigation inside header search input
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        if (suggestionsBox) suggestionsBox.style.display = 'none';
        return;
      }

      const items = suggestionsBox ? suggestionsBox.querySelectorAll('.header-suggestion-item') : [];
      if (!items.length) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeSuggestionIndex = (activeSuggestionIndex + 1) % items.length;
        items.forEach((it, i) => it.classList.toggle('active', i === activeSuggestionIndex));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeSuggestionIndex = (activeSuggestionIndex - 1 + items.length) % items.length;
        items.forEach((it, i) => it.classList.toggle('active', i === activeSuggestionIndex));
      } else if (e.key === 'Enter') {
        if (activeSuggestionIndex >= 0 && filteredSuggestions[activeSuggestionIndex]) {
          e.preventDefault();
          window.location.href = filteredSuggestions[activeSuggestionIndex].url;
        }
      }
    });

    // Close on outside click
    document.addEventListener('click', function(e) {
      if (!e.target.closest('#headerSearchContainer')) {
        if (suggestionsBox) suggestionsBox.style.display = 'none';
      }
    });
  }

  function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }

  // ---------------------------------------------------------------------------
  // 8. UNIVERSAL COPY (CTRL+C / CLIPBOARD HELPER)
  // ---------------------------------------------------------------------------
  window.copyToClipboard = function(text, btnElement) {
    if (!text) return;
    
    function showFeedback(btn) {
      if (!btn) return;
      const originalHTML = btn.innerHTML;
      btn.innerHTML = '<span>✓</span> Copied!';
      btn.classList.add('copy-success');
      setTimeout(() => {
        btn.innerHTML = originalHTML;
        btn.classList.remove('copy-success');
      }, 2000);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        showFeedback(btnElement);
      }).catch(() => {
        fallbackCopy(text, btnElement);
      });
    } else {
      fallbackCopy(text, btnElement);
    }
  };

  function fallbackCopy(text, btn) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-9999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<span>✓</span> Copied!';
        setTimeout(() => { btn.innerHTML = orig; }, 2000);
      }
    } catch (e) {}
    document.body.removeChild(textArea);
  }

  // Global listener for elements with data-copy
  document.addEventListener('click', function(e) {
    const copyBtn = e.target.closest('[data-copy]');
    if (copyBtn) {
      const copyVal = copyBtn.getAttribute('data-copy');
      window.copyToClipboard(copyVal, copyBtn);
    }
  });

  // ---------------------------------------------------------------------------
  // 9. INITIALIZATION
  // ---------------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', function() {
    window.applyStoredTheme();
    setupDropdowns();
    setupMobileDrawer();
    setupCommandPalette();
    setupHeaderSearch();
  });

})();
