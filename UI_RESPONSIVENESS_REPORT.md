# UI RESPONSIVENESS & DESIGN SYSTEM REPORT
## HireNexa UI/UX & Product Design Team

---

### Layout Hierarchy & Breakpoint Specifications

#### 1. Header Navigation (3-Zone Flex Grid)
- **Desktop (>= 1200px)**:
  - Left Zone: HireNexa Brand Logo + Home, Find Jobs, Companies.
  - Center Zone: Freelance Gigs, HireNexa AI, AI Career (ACO), Career Resources, MCQ Prep.
  - Right Zone: Notifications indicator, Premium badge, Profile avatar dropdown, Post Job CTA.
  - Zero overlapping text, clean 12px-16px gap spacing.
- **Tablet / Mobile (< 1200px)**:
  - Header compresses gracefully; hamburger toggle invokes the offcanvas mobile navigation drawer.

#### 2. Search Bar & Dropdown Stacking
- **Problem Fixed**: Candidate preview cards previously clipped or covered the location autocomplete dropdown.
- **Engineered Solution**:
  - The autocomplete dropdown container is rendered via a portal attached directly to `document.body` with `position: fixed; z-index: 999999`.
  - Recalculates screen coordinates on window scroll and resize.
  - Guaranteed floating layer above all hero graphics and preview cards.

#### 3. Jobie 3x3 Cards Grid & List View Toggle
- **Desktop View**: 3-column CSS Grid (`grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))`).
- **Interactive List View**: Users can switch between 3x3 grid and full-width horizontal cards via the top toolbar toggle. Preference persists across sessions in `localStorage`.
- **Card Metrics**: 16px corner radius, soft border (`#edf0f7`), subtle shadow, and color-coded company monogram badges.
- **Mobile View**: Automatically collapses into a single-column stacked layout with full touch targets.
