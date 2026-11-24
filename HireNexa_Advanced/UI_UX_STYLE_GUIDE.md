# HireNexa Enterprise UI/UX Design System & Style Guide

## Design Tokens, Typography, Layout Rules, Zero-Navbar Overlap & Responsive Breakpoints

---

## 1. Design Philosophy & Aesthetic Foundation

HireNexa adheres to a **Clean Enterprise SaaS** design aesthetic:
- **Clarity over Clutter**: Dense, high-utility data representation without visual cognitive overload.
- **Deterministic Hierarchy**: High-contrast typography paired with functional semantic colors.
- **Zero-Glitch Responsive Reliability**: Strict container boundaries that prevent content overlap across ultra-wide monitors, laptops, tablets, and mobile devices.

---

## 2. Design Tokens & Color Palette

The platform's visual foundation is defined in CSS variables (`static/css/style.css`):

### Core Brand Colors
| Token | Hex Value | Semantic Usage |
|---|---|---|
| `--hn-primary` | `#2563eb` (Blue-600) | Primary call-to-actions, brand identity, active states |
| `--hn-primary-hover` | `#1d4ed8` (Blue-700) | Button hover states, link hover highlights |
| `--hn-primary-subtle`| `rgba(37, 99, 235, 0.08)` | Active tab backgrounds, badge fills |
| `--hn-secondary` | `#475569` (Slate-600) | Secondary action triggers, secondary navigation |
| `--hn-accent` | `#0ea5e9` (Sky-500) | Highlights, metric accents, progress indicators |

### Feedback & Status Tokens
| Token | Hex Value | Meaning |
|---|---|---|
| `--hn-success` | `#10b981` (Emerald-500) | Positive marks (+1.00), passed exams, approved stages |
| `--hn-danger` | `#ef4444` (Red-500) | Negative marks (-0.25), exam lockouts, cancellations |
| `--hn-warning` | `#f59e0b` (Amber-500) | Timer warnings (<3 min), pending reviews |
| `--hn-info` | `#3b82f6` (Blue-500) | Informational callouts, concept notes |

### Neutral Backgrounds & Surfaces
| Surface Token | Hex Value | Purpose |
|---|---|---|
| `--hn-bg-body` | `#f8fafc` (Slate-50) | Global page background |
| `--hn-surface-card` | `#ffffff` (Pure White) | Card containers, modals, table rows |
| `--hn-surface-elevated`| `#ffffff` | Floating dropdowns, popovers, tooltips |
| `--hn-border-subtle` | `#e2e8f0` (Slate-200) | Card borders, dividers, table grid lines |
| `--hn-border-focus` | `#93c5fd` (Blue-300) | Active input focus ring outline |

---

## 3. Typography System

- **Primary Font Family**: `'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- **Monospace Code/Data**: `'JetBrains Mono', 'Fira Code', Menlo, Consolas, monospace`

| Element | Size | Weight | Line Height | Tracking |
|---|---|---|---|---|
| **Display H1** | 2.25rem (36px) | 800 (ExtraBold) | 1.2 | -0.025em |
| **Page Title H2** | 1.75rem (28px) | 700 (Bold) | 1.25 | -0.02em |
| **Section Header H3** | 1.25rem (20px) | 600 (SemiBold) | 1.35 | -0.01em |
| **Card Header H4** | 1.05rem (16.8px) | 600 (SemiBold) | 1.4 | 0 |
| **Body Standard** | 0.9375rem (15px) | 400 (Regular) | 1.5 | 0 |
| **Body Small / Meta** | 0.8125rem (13px) | 500 (Medium) | 1.4 | +0.01em |
| **Badge / Label** | 0.75rem (12px) | 600 (SemiBold) | 1.0 | +0.02em |

---

## 4. Zero-Navbar Overlap Specification

A critical defect in legacy web applications is fixed navigation bars overlapping top-level page headings or primary CTA buttons. HireNexa eliminates this via a strict architectural rule:

### A. Layout Padding Enforcement
```css
/* Fixed Navigation Header */
.hirenexa-navbar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 72px;
    z-index: 1030;
    background: #ffffff;
    border-bottom: 1px solid var(--hn-border-subtle);
}

/* Global Content Body Spacer */
body {
    padding-top: 72px; /* Exactly matches navbar height */
}

@media (max-width: 991.98px) {
    .hirenexa-navbar {
        height: 64px;
    }
    body {
        padding-top: 64px;
    }
}
```

### B. Responsive Viewport Breakpoints & Label Shortening
To prevent text clipping or horizontal wrap in the navbar before reaching mobile drawer width:

1. **Large Desktops (≥1400px)**:
   - Full textual labels visible (`Job Search`, `Companies`, `Gigs`, `HireNexa AI`, `Career Assistant`, `Exams`, `Resources`).
2. **Standard Desktops (1100px - 1399px)**:
   - Navigation links adaptively compress spacing and shorten long labels (`Career Assistant` -> `Career AI`).
3. **Tablets & Small Desktops (768px - 1099px)**:
   - Secondary items hide from main row; primary items persist.
4. **Mobile Devices (<768px)**:
   - Full horizontal navigation collapses into the **Mobile Offcanvas Drawer** (`#mobileNavigationOffcanvas`).
   - Mobile hamburger button activates a smooth slide-in menu with high-contrast persona login gateways.

---

## 5. Standard Component Specifications

### A. Computer-Based Testing (CBT) Interface
- **Fixed Sticky Timer**: Top right corner, monospaced digits, changing from neutral to Amber at <5 min, and flashing Red at <1 min.
- **Question Palette**: 16 numbered circular tokens showing status:
  - Grey: Unvisited
  - Red: Visited but Unanswered
  - Green: Answered
  - Purple: Marked for Review
- **Origin & Question Type Badges**:
  - `Authentic PYQ`: Purple pill (`badge-pyq`)
  - `Expert Curated`: Emerald pill (`badge-curated`)
  - `AI Practice`: Sky pill (`badge-practice`)

### B. Virtual Video Interview Studio (`templates/recruitment/interview_room.html`)
- **Stage Layout**: 16:9 responsive video viewport with dark backdrop (`#0f172a`).
- **Control Bar**: Centered floating pill with Mic, Camera, Screen Share, and Leave Meeting buttons.
- **Recruiter Evaluation Sidebar**: Embedded real-time candidate resume viewer and 5-metric scoring form.
