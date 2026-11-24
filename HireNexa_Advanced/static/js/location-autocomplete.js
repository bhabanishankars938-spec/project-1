/**
 * HireNexa India Location Autocomplete Engine
 * Clean, Unified & Resilient Location Selection
 * Supports: Country -> State -> District -> City -> Area -> PIN Code autocomplete
 * Features:
 * - Single dropdown instance per input with clean lifecycle
 * - Instant debounce & request cancellation (AbortController)
 * - Zero repeated suggestions after selection
 * - Smooth keyboard navigation (Up / Down / Enter / Esc)
 * - Custom manual location text entry support
 * - Automatic positioning with fixed portal to avoid clipping/overflow
 */

(function () {
  'use strict';

  const POPULAR_LOCATIONS = [
    { type: 'mode', label: 'All India', value: 'All India', subtext: 'Pan India / Anywhere', badge: 'PAN INDIA' },
    { type: 'mode', label: 'Remote', value: 'Remote', subtext: 'Work from Anywhere (WFA)', badge: 'WORK MODE' },
    { type: 'mode', label: 'Hybrid', value: 'Hybrid', subtext: 'Flexible On-site & Remote', badge: 'WORK MODE' },
    { type: 'mode', label: 'On-site', value: 'On-site', subtext: 'In-office Presence', badge: 'WORK MODE' },
    { type: 'city', label: 'Bengaluru', value: 'Bengaluru', subtext: 'Karnataka · Tech Capital', badge: 'METRO' },
    { type: 'city', label: 'Hyderabad', value: 'Hyderabad', subtext: 'Telangana · Cyberabad', badge: 'METRO' },
    { type: 'city', label: 'Bhubaneswar', value: 'Bhubaneswar', subtext: 'Odisha · Emerging IT Hub', badge: 'TECH HUB' },
    { type: 'city', label: 'Pune', value: 'Pune', subtext: 'Maharashtra · IT & Auto', badge: 'TIER-1' },
    { type: 'city', label: 'Mumbai', value: 'Mumbai', subtext: 'Maharashtra · Financial Hub', badge: 'METRO' },
    { type: 'city', label: 'Delhi NCR', value: 'Delhi NCR', subtext: 'National Capital Region', badge: 'METRO' },
  ];

  function getBadgeColor(type) {
    switch (type) {
      case 'mode':
        return { bg: '#e0e7ff', color: '#4338ca', border: '#c7d2fe' };
      case 'pin_code':
        return { bg: '#fef3c7', color: '#b45309', border: '#fde68a' };
      case 'area':
        return { bg: '#e0f2fe', color: '#0369a1', border: '#bae6fd' };
      case 'city':
        return { bg: '#ecfdf5', color: '#047857', border: '#a7f3d0' };
      case 'district':
        return { bg: '#fae8ff', color: '#86198f', border: '#f5d0fe' };
      case 'state':
        return { bg: '#f1f5f9', color: '#334155', border: '#cbd5e1' };
      default:
        return { bg: '#f1f5f9', color: '#475569', border: '#e2e8f0' };
    }
  }

  function initLocationAutocomplete(input) {
    if (!input || input.__locationAutocompleteInit) return;
    input.__locationAutocompleteInit = true;

    // Create dropdown container attached to body portal
    const dropdown = document.createElement('div');
    dropdown.className = 'location-autocomplete-dropdown';
    dropdown.setAttribute('role', 'listbox');
    dropdown.style.cssText = `
      position: fixed;
      min-width: 340px;
      max-height: 340px;
      overflow-y: auto;
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      box-shadow: 0 16px 36px -4px rgba(15, 23, 42, 0.25), 0 0 0 1px rgba(15, 23, 42, 0.05);
      z-index: 999999;
      display: none;
      padding: 6px 0;
      font-family: inherit;
      overscroll-behavior: contain;
    `;

    document.body.appendChild(dropdown);

    let activeIndex = -1;
    let items = [];
    let debounceTimer = null;
    let abortController = null;
    let isSelecting = false;
    let lastQuery = '';

    function updateDropdownPosition() {
      if (dropdown.style.display === 'none') return;
      const rect = input.getBoundingClientRect();
      dropdown.style.position = 'fixed';
      dropdown.style.top = `${rect.bottom + 6}px`;
      dropdown.style.left = `${rect.left}px`;
      dropdown.style.width = `${Math.max(rect.width, 360)}px`;
      dropdown.style.zIndex = '999999';
    }

    const scrollHandler = () => updateDropdownPosition();
    window.addEventListener('scroll', scrollHandler, true);
    window.addEventListener('resize', scrollHandler);

    function closeDropdown() {
      dropdown.style.display = 'none';
      dropdown.innerHTML = '';
      items = [];
      activeIndex = -1;
      if (abortController) {
        abortController.abort();
        abortController = null;
      }
    }

    function renderItems(dataList, title, currentQuery) {
      dropdown.innerHTML = '';
      items = dataList || [];
      activeIndex = -1;

      const qClean = (currentQuery || '').trim();

      if (!items || items.length === 0) {
        dropdown.innerHTML = `
          ${qClean ? `
          <div style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; cursor: pointer; background: #f8fafc;" class="location-custom-pick" id="customLocationPick">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 16px;">📍</span>
              <div>
                <div style="font-size: 13px; font-weight: 600; color: #2563eb;">Use "${escapeHtml(qClean)}"</div>
                <div style="font-size: 11px; color: #64748b;">Accept manual custom location</div>
              </div>
            </div>
          </div>
          ` : ''}
          <div style="padding: 14px; font-size: 13px; color: #64748b; text-align: center;">
            No verified location record found.
            <div style="font-size: 11px; margin-top: 4px; color: #94a3b8;">
              Try searching by State, District, City, Area, or 6-digit PIN code (e.g. Bhubaneswar, Deogarh, Patia, 751024).
            </div>
          </div>
        `;
        const pickBtn = dropdown.querySelector('#customLocationPick');
        if (pickBtn && qClean) {
          pickBtn.addEventListener('click', (e) => {
            e.preventDefault();
            selectItem({ type: 'custom', value: qClean, label: qClean });
          });
        }
        dropdown.style.display = 'block';
        updateDropdownPosition();
        return;
      }

      if (title) {
        const header = document.createElement('div');
        header.style.cssText = `
          padding: 6px 14px 4px 14px;
          font-size: 11px;
          font-weight: 700;
          color: #94a3b8;
          letter-spacing: 0.05em;
          text-transform: uppercase;
        `;
        header.textContent = title;
        dropdown.appendChild(header);
      }

      // If user typed a custom query that isn't an exact match, allow custom pick as first option
      if (qClean && !items.some(i => (i.value || '').toLowerCase() === qClean.toLowerCase())) {
        const customRow = document.createElement('div');
        customRow.className = 'location-autocomplete-item custom-opt';
        customRow.style.cssText = `
          padding: 8px 14px;
          cursor: pointer;
          border-bottom: 1px dashed #cbd5e1;
          background: #f8fafc;
          display: flex;
          align-items: center;
          gap: 8px;
        `;
        customRow.innerHTML = `
          <span style="font-size: 14px;">📍</span>
          <div style="font-size: 12.5px; color: #2563eb; font-weight: 600;">Use "${escapeHtml(qClean)}" (Custom)</div>
        `;
        customRow.addEventListener('click', (e) => {
          e.preventDefault();
          selectItem({ type: 'custom', value: qClean, label: qClean });
        });
        dropdown.appendChild(customRow);
      }

      items.forEach((item, idx) => {
        const row = document.createElement('div');
        row.className = 'location-autocomplete-item';
        row.setAttribute('role', 'option');
        row.setAttribute('data-index', idx);
        row.style.cssText = `
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 14px;
          cursor: pointer;
          transition: background 0.12s ease;
          border-bottom: 1px solid rgba(226, 232, 240, 0.6);
        `;

        const badgeStyle = getBadgeColor(item.type);

        row.innerHTML = `
          <div style="display: flex; align-items: center; gap: 10px; overflow: hidden; flex: 1;">
            <span style="font-size: 15px;">📍</span>
            <div style="overflow: hidden;">
              <div style="font-size: 13px; font-weight: 600; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                ${escapeHtml(item.label || item.value)}
              </div>
              ${item.subtext ? `<div style="font-size: 11px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(item.subtext)}</div>` : ''}
            </div>
          </div>
          <span style="
            background: ${badgeStyle.bg};
            color: ${badgeStyle.color};
            border: 1px solid ${badgeStyle.border};
            font-size: 10px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 9999px;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            white-space: nowrap;
            margin-left: 8px;
          ">${escapeHtml(item.badge || item.type || 'LOCATION')}</span>
        `;

        row.addEventListener('mouseenter', () => {
          setActiveIndex(idx);
        });

        row.addEventListener('mousedown', (e) => {
          // Prevent blur from closing before click is registered
          e.preventDefault();
        });

        row.addEventListener('click', (e) => {
          e.preventDefault();
          selectItem(item);
        });

        dropdown.appendChild(row);
      });

      dropdown.style.display = 'block';
      updateDropdownPosition();
    }

    function setActiveIndex(idx) {
      const rows = dropdown.querySelectorAll('.location-autocomplete-item:not(.custom-opt)');
      rows.forEach((r, i) => {
        if (i === idx) {
          r.style.background = '#eff6ff';
          r.scrollIntoView({ block: 'nearest' });
        } else {
          r.style.background = 'transparent';
        }
      });
      activeIndex = idx;
    }

    function selectItem(item) {
      if (!item) return;
      isSelecting = true;

      const currentVal = input.value.trim();
      if (currentVal.includes(',')) {
        const parts = currentVal.split(',').map(s => s.trim());
        parts[parts.length - 1] = item.value;
        input.value = parts.join(', ');
      } else {
        input.value = item.value;
      }
      lastQuery = input.value;

      // Close dropdown immediately and do NOT re-trigger focus suggestions
      closeDropdown();

      // Trigger change and custom event
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.dispatchEvent(new CustomEvent('locationSelected', { detail: item, bubbles: true }));

      // Reset selecting guard after event cycle completes
      setTimeout(() => {
        isSelecting = false;
      }, 150);
    }

    function fetchSuggestions(query) {
      if (isSelecting) return;

      const cleanQuery = (query || '').trim();
      lastQuery = cleanQuery;

      if (abortController) {
        abortController.abort();
      }
      abortController = new AbortController();

      if (!cleanQuery) {
        renderItems(POPULAR_LOCATIONS, 'Popular Locations & Modes', cleanQuery);
        return;
      }

      fetch(`/api/locations/autocomplete/?q=${encodeURIComponent(cleanQuery)}`, {
        signal: abortController.signal
      })
        .then(res => {
          if (!res.ok) throw new Error('Network response not ok');
          return res.json();
        })
        .then(data => {
          if (isSelecting) return;
          if (data && data.results) {
            renderItems(data.results, `Matching Locations (${data.results.length})`, cleanQuery);
          } else {
            renderItems([], '', cleanQuery);
          }
        })
        .catch(err => {
          if (err.name !== 'AbortError') {
            renderItems([], '', cleanQuery);
          }
        });
    }

    // Input event with 200ms debounce
    input.addEventListener('input', function () {
      if (isSelecting) return;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        fetchSuggestions(this.value);
      }, 200);
    });

    // Focus event: Open only if not just selected and dropdown is currently closed
    input.addEventListener('focus', function () {
      if (isSelecting) return;
      if (dropdown.style.display === 'block') return;

      if (!this.value.trim()) {
        renderItems(POPULAR_LOCATIONS, 'Popular Locations & Modes', '');
      } else {
        fetchSuggestions(this.value);
      }
    });

    // Keyboard navigation
    input.addEventListener('keydown', function (e) {
      if (dropdown.style.display === 'none') {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          fetchSuggestions(this.value);
        }
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = activeIndex + 1 < items.length ? activeIndex + 1 : 0;
        setActiveIndex(next);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = activeIndex - 1 >= 0 ? activeIndex - 1 : items.length - 1;
        setActiveIndex(prev);
      } else if (e.key === 'Enter') {
        if (activeIndex >= 0 && activeIndex < items.length) {
          e.preventDefault();
          selectItem(items[activeIndex]);
        } else if (items.length > 0) {
          // Select first suggestion on Enter
          e.preventDefault();
          selectItem(items[0]);
        } else if (this.value.trim()) {
          // Accept custom typed text
          closeDropdown();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeDropdown();
      }
    });

    // Close on click outside
    document.addEventListener('click', function (e) {
      if (e.target !== input && !dropdown.contains(e.target)) {
        closeDropdown();
      }
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Global initializer
  window.initAllLocationAutocompletes = function () {
    const inputs = document.querySelectorAll('input[name="location"], input.location-autocomplete-input, input[name="preferred_locations_input"]');
    inputs.forEach(initLocationAutocomplete);
  };

  // Auto-run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.initAllLocationAutocompletes);
  } else {
    window.initAllLocationAutocompletes();
  }
})();
