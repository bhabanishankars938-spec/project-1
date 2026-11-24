# Developer notes

## Architecture
This starter keeps core recruitment models in one `recruitment` app to make the first build easier to understand. The account system is separate. As the project grows, services can be split into dedicated apps for resume parsing, AI matching, analytics and interviews.

## Current features
- Candidate/recruiter signup and login
- Custom role field
- Candidate and recruiter profiles
- Job posting and listing
- PDF/DOCX resume upload and text extraction
- Skill extraction from a configurable dictionary
- Exact skill overlap score
- Optional semantic similarity via Sentence Transformers
- Applications, status updates and interview scheduling
- Protected resume download view with ownership/application checks

## Known limitations to improve
- Semantic model loading is currently synchronous and may be slow on first use. Move it to Celery workers before production.
- File extension and size checks are not sufficient against malicious uploads. Add MIME inspection, malware scanning and private object storage.
- `DEBUG` defaults to True for local learning only.
- Add automated tests for views, permissions, uploads and interview workflows.
- Add pagination, email notifications, audit logs, profile completeness and consent/deletion workflows.
- The score uses textual similarity, not validated hiring outcomes. It must never be the sole basis for rejecting or ranking people.
