# GeoHire Location Intelligence & Address Verification Documentation

## Enterprise Geographic Data Architecture, Indian Address Hierarchy & Corporate Location Verification

---

## 1. System Overview

**GeoHire** is HireNexa's proprietary location intelligence engine designed specifically for the Indian employment and recruitment ecosystem. It provides:
1. **Granular Geographic Hierarchy**: Accurate classification from national level down to postal PIN codes.
2. **Sub-millisecond Location Autocomplete**: High-speed prefix querying for cities, states, districts, and job hubs.
3. **Dual Corporate Physical Verification**: Rigorous separation of a company's **Registered Corporate Headquarters** from its **Branch / Regional Operating Offices**.
4. **Interactive Navigation & Map Verification**: Direct integration with Google Maps and turn-by-turn navigation URLs to eliminate fraudulent and phantom office postings.

---

## 2. Indian Geographic Data Model & Hierarchy

The database models location data using a structured 6-tier hierarchy:

```
[Country: India]
       │
       ▼
[State / Union Territory] (e.g., Odisha, Karnataka, Maharashtra)
       │
       ▼
[District / Revenue Division] (e.g., Khordha, Bengaluru Urban, Mumbai Suburban)
       │
       ▼
[City / Municipal Corporation] (e.g., Bhubaneswar, Bengaluru, Mumbai)
       │
       ▼
[Locality / Tech Hub / SEZ] (e.g., Infocity / Patia, Electronic City, BKC)
       │
       ▼
[Postal Index Number (PIN Code)] (e.g., 751024, 560100, 400051)
```

### Database Schema Representation

In `recruitment/models.py`:
- `Country`: ISO 3166-1 alpha-2 code (`IN`), name, currency, telephone prefix (`+91`).
- `State`: State/UT name, standard state code, capital city reference.
- `District`: District name, state foreign key.
- `City`: City/municipality name, district/state foreign keys, Tier classification (`Tier-1`, `Tier-2`, `Tier-3`), latitude/longitude coordinates.
- `Locality`: Neighborhood / commercial zone / tech park, city foreign key.
- `PinCode`: 6-digit postal code, delivery post office, division, circle.

---

## 3. High-Performance Location Autocomplete API

The platform provides a low-latency endpoint for location search and job filtering:

- **Endpoint**: `GET /api/v1/locations/autocomplete/`
- **Query Parameter**: `?q=<search_term>`
- **Response Format**:
```json
{
  "query": "Bhuban",
  "results": [
    {
      "id": 104,
      "name": "Bhubaneswar",
      "district": "Khordha",
      "state": "Odisha",
      "tier": "Tier-2",
      "full_display": "Bhubaneswar, Khordha, Odisha, India",
      "pincode_prefixes": ["751001", "751024"]
    }
  ]
}
```

### Algorithmic Optimization
- **Prefix Indexing**: Database indexes on `name__istartswith` ensure queries complete in <15 ms.
- **Debounced Frontend Handling**: Client inputs debounce at 250ms to minimize backend database load.

---

## 4. Dual Corporate Office Verification Architecture

To prevent fraudulent job listings and phantom company setups, HireNexa enforces strict physical office verification.

### Fields on `Organization` Model (`recruitment/models.py`)

| Field Name | Type | Purpose |
|---|---|---|
| `registered_office_address` | `TextField` (blank=True) | Statutory registered corporate headquarters as listed on Ministry of Corporate Affairs (MCA) / RoC filing |
| `branch_office_address` | `TextField` (blank=True) | Operational branch, interview center, or local development facility address |
| `map_url` | `URLField` (blank=True) | Verified Google Maps link for the primary office location |
| `directions_url` | `URLField` (blank=True) | Google Maps turn-by-turn navigation link destination |
| `headquarters` | `CharField` (max_length=255) | High-level city/state descriptor (e.g., "Bhubaneswar, India") |

### Dynamic Model Properties

```python
@property
def effective_registered_address(self):
    """Returns statutory registered headquarters or falls back to general address."""
    return self.registered_office_address or self.address or self.headquarters or "Registered address on file"

@property
def effective_branch_address(self):
    """Returns branch operating office address if configured."""
    return self.branch_office_address or "Branch office details available upon request"

@property
def google_maps_url(self):
    """Returns verified Google Maps link or auto-generates query URL from address."""
    if self.map_url:
        return self.map_url
    query = quote_plus(f"{self.name} {self.effective_registered_address}")
    return f"https://www.google.com/maps/search/?api=1&query={query}"

@property
def directions_link(self):
    """Returns verified navigation URL or auto-generates turn-by-turn directions link."""
    if self.directions_url:
        return self.directions_url
    destination = quote_plus(self.effective_registered_address)
    return f"https://www.google.com/maps/dir/?api=1&destination={destination}"
```

---

## 5. User Interface & Company Trust Integration

The physical office data is surfaced on the public **Company Trust & Verification** page (`/companies/<slug>/trust/` rendered via `templates/recruitment/company_trust.html`):

### UI Highlights
1. **Registered Headquarters Card**:
   - Displays RoC registered address with an "MCA Verified" badge.
   - One-click button to open Google Maps pin.
2. **Branch / Operational Office Card**:
   - Displays physical interview and workspace location.
   - One-click button for **Get Directions** opening mobile navigation apps directly.
3. **Geo-Verification Trust Score**:
   - Companies with both verified registered HQ and branch coordinates receive an elevated **Trust Badge (Tier-A Verified)**.
