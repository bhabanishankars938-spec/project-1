# LOCATION SEARCH & HIERARCHY TEST REPORT
## HireNexa Location Intelligence Engine

---

### Verification Matrix: Search Queries & Results

| # | Test Query | Search Input Type | Expected Entity | Output Hierarchy Resolved | Status |
| :-: | :--- | :--- | :--- | :--- | :-: |
| 1 | `Deogarh` | Single Token | District / City | `Deogarh, Deogarh District, Odisha, India` | **PASS** |
| 2 | `Odisha Deogarh` | Multi-Word (State + Dist) | District | `Deogarh, Deogarh District, Odisha, India` | **PASS** |
| 3 | `Deogarh Odisha` | Reversed-Order (Dist + State) | District | `Deogarh, Deogarh District, Odisha, India` | **PASS** |
| 4 | `Deogarh, Odisha` | Comma Delimited | District / State | `Deogarh, Deogarh District, Odisha, India` | **PASS** |
| 5 | `Bhubaneswar` | Single Token | Tier-2 City | `Bhubaneswar, Khordha District, Odisha, India` | **PASS** |
| 6 | `Bhubaneswar Odisha` | City + State | City | `Bhubaneswar, Khordha District, Odisha, India` | **PASS** |
| 7 | `Odisha Bhubaneswar` | Reversed (State + City) | City | `Bhubaneswar, Khordha District, Odisha, India` | **PASS** |
| 8 | `Patia` | Area Token | Urban Area | `Patia, Bhubaneswar, Khordha District, Odisha` | **PASS** |
| 9 | `Bengaluru, Karnataka` | City + State | Metro City | `Bengaluru, Bengaluru Urban, Karnataka, India` | **PASS** |
| 10 | `560066` | 6-Digit PIN Code | PIN / Area | `560066 - Whitefield, Bengaluru, KA` | **PASS** |
| 11 | `768119` | 6-Digit PIN Code | PIN / Area | `768119 - Deogarh, Odisha` | **PASS** |
| 12 | `All India` | Mode Shortcut | Pan-India | `All India · Pan-India Open Roles` | **PASS** |
| 13 | `Remote` | Mode Shortcut | Work from Anywhere | `Remote · Work from Anywhere` | **PASS** |
| 14 | `Hybrid` | Mode Shortcut | Hybrid Office | `Hybrid · Flexible On-site & Remote` | **PASS** |

### Database Filtering Behavior
- Queries like `location=Odisha%20Deogarh` correctly match Job #3 (`IoT & Embedded Systems Engineer` located in Deogarh, Odisha).
- Multi-token comma queries like `location=Bengaluru,%20Bhubaneswar` correctly match both Bengaluru and Bhubaneswar jobs via dynamic OR filtering.
- Hierarchical breadcrumbs (`India > Odisha > Khordha > Bhubaneswar`) correctly parse deepest entity nodes.
