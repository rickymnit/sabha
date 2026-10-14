# DRAFT FOR LEGAL REVIEW — NOT LEGAL ADVICE

## Questions for legal review: Sabha pilot in schools

| | |
| --- | --- |
| Status | Draft v0.1 (plan task P8.1) |
| Date | 14 October 2026 |
| Prepared by | Sabha product team, Schoollog [legal entity name] |
| For | [Lawyer name / firm] |
| Enclosed drafts | `parent-consent-form.md`, `staff-consent-and-notice.md`, `call-recording-notice.md` |

We are preparing an 8-week pilot of Sabha in [N] schools in India, covering classroom lessons and school
reception calls. We would like your advice under India's Digital Personal Data Protection Act, 2023, and any
other law you think is relevant, before anything is recorded. The enclosed drafts are our first attempt and are
not final.

Each group below starts with a short description of how the product works, then lists our questions. Question
numbers (A1, B2, ...) are referenced from the drafts. The descriptions reflect the product as designed for the
pilot; Schoollog will confirm before go-live that the running system matches them. Text in [square brackets] is
not yet known or decided.

---

### How Sabha works (summary)

- **Customers.** Each school is a separate customer account. One school's data is kept separate from every
  other school's.
- **What is recorded.** Classroom lessons: audio only, on a phone or small microphone near the teacher.
  Reception calls: recorded by the school's phone system [mechanism and vendor to be confirmed] and then uploaded.
- **Consent gate.** Every recording must be linked to a consent record held in Sabha. A consent record has a scope
  (a class or section for a school year, a staff member, or a call line), valid-from and valid-to dates, and a
  link to the signed document. A recording without a valid consent record is not processed.
- **Storage.** Files are uploaded directly to storage in AWS Mumbai (ap-south-1). The database is planned on
  MongoDB Atlas, Mumbai. Product rule: data stays in India unless an exception is explicitly approved.
- **Speech processing.** The software removes silence (while keeping original timings), separates speakers, and
  labels them by role only: "Teacher" and "Student(s)", or "Receptionist" and "Caller". It never identifies
  individual students. Speech-to-text runs on servers Schoollog operates [location to be confirmed: AWS Mumbai or
  Schoollog's own server at (location)]. Audio is not sent to outside speech-to-text companies [to be confirmed].
- **Analysis.** Some measures are computed directly by software (for lessons: teacher and student talk share,
  number of questions, pace, silences, longest teacher monologue; for calls: call length, hold or silent gaps,
  caller talk share). An AI language model then rates the staff member against a rubric. Before any text goes to
  the AI provider, software masks phone numbers, Aadhaar-like and PAN-like numbers, emails, and student names from
  a configured list. Staff names are not masked by default. Every AI judgement must quote the transcript with
  timestamps; the software checks each quote exists, and judgements that fail this check are not shown.
- **Who sees what.** Staff see only their own reports and can dispute any score. Reviewers and managers see their
  section or unit. School administrators see everything for their school, including some measures marked
  "Internal" that have not yet passed quality checks. Parents and students have no access. Every playback, export
  and score change is logged.
- **Retention and erasure.** Audio is deleted automatically after 90 days by default (a per-school setting).
  Transcripts, scores and reports are currently kept with no end date set. An erasure function deletes data for a
  recording, a staff member or a whole school, and keeps a minimal record that the erasure happened.
- **Other services used to run the product.** [To be confirmed, with hosting region and what data each receives:
  error monitoring (Sentry), AI call tracing (Langfuse, which stores AI inputs and outputs), email notifications
  (Amazon SES).]

---

### A. Verifiable parental consent

**Context.** The school would give each parent the form in English and Hindi, [on paper, collected by the class
teacher / through the school's existing parent communication channel; to be decided]. One form per student per
school year. In Sabha, consent is recorded per class or section. Recording a lesson captures every student who
speaks, so a class can only be recorded if consent covers the class.

- **A1.** What would you consider an adequate mechanism for obtaining verifiable consent from a parent or lawful
  guardian? Is a signed paper form collected by the school enough, or is an identity check needed (for example
  matching against admission records, or a one-time code sent to the parent's registered mobile number)?
- **A2.** What record of the consent and of the identity check should the school keep, and for how long?
- **A3.** Do we need consent from every parent in a class before recording that class? If one parent says No,
  which options are acceptable: (a) do not record that class at all; (b) record only lessons where that student is
  absent; (c) [other]? We do not think seating a student away from the microphone is reliable.
- **A4.** Can consent be collected once per school year? Can it be included in annual or admission paperwork, or
  should it be a separate form?
- **A5.** For students aged 18 or over in senior classes, should we ask the student instead of the parent? Should
  younger students also be told about the recording, in age-appropriate words?
- **A6.** Is English and Hindi enough, or should the form be available in other languages that parents at a
  school use?
- **A7.** Is the content of the parent form adequate as a notice? What is missing, and which rights must be
  listed?

### B. Children's data obligations

**Context.** Staff are analysed, not students. There are no student-level scores, profiles or identification,
and no tracking or behavioural monitoring of children. However, students' voices and words are captured
incidentally. Transcripts stored in Sabha contain what students say, and may contain names spoken in class. Names
are masked before text goes to the AI provider; the mapping is kept on our servers so authorised staff see the
original wording. Some lesson measures are about the class as a group (for example the share of lesson time
students speak). Masking student names needs a list of names [how this list is obtained is to be confirmed, e.g.
a class list from the school]. Audio is deleted after 90 days; transcripts are kept longer [period not set].

- **B1.** Does the incidental capture of students' voices and words in lesson audio and transcripts count as
  processing children's personal data, even though we never identify which student is speaking?
- **B2.** Are there restrictions on processing children's data (for example on tracking, behavioural monitoring or
  targeted advertising) that apply here? Does our design, or do the class-level measures, raise any concern under
  them?
- **B3.** Are there exemptions or special conditions for educational institutions that might apply to this use?
  Would they change the consent approach?
- **B4.** If the school gives Schoollog a list of student names only so that they can be masked, does that create
  any further obligation?
- **B5.** Should student names also be masked in the transcripts stored in Sabha, not only in the text sent to the
  AI provider?
- **B6.** Should the parent form promise "no AI model training and no advertising"? If so, what commitments do we
  need from AI providers to make that promise?
- **B7.** Student counselling sessions are out of scope for the pilot. Please confirm they should not be recorded
  without a separate review.

### C. Roles of the school and Schoollog, and the contract between them

**Context.** The school decides to use Sabha, decides which lessons and calls are recorded, collects consent,
sets the audio retention period, reads reports and manages staff accounts. Schoollog provides and hosts the
software, chooses the cloud and AI providers, designs the default rubrics (agreed with each school), provides
technical support, and plans to use a sample of recordings to check transcript and scoring quality (see J).

- **C1.** Is the school the data fiduciary and Schoollog a data processor? Does any of Schoollog's own activity
  (choosing providers, designing rubrics, quality checking) make it a data fiduciary, alone or jointly, for some
  purposes? Which ones?
- **C2.** What contract is needed between the school and Schoollog, and what should it cover? For example:
  processing only on the school's instructions, confidentiality, security measures, use of other providers,
  data location, breach notice to the school (timeline and content), help with parents' and staff requests,
  deletion or return of data at the end, audit rights, liability.
- **C3.** How should other providers be disclosed and approved: AWS (Mumbai), MongoDB Atlas (Mumbai), the AI
  provider [not yet chosen], [error monitoring, AI call tracing, email: to be confirmed]? Does each school need to
  approve each one, and how are changes handled?
- **C4.** The phone system that records reception calls belongs to the school [vendor to be confirmed]. Does that
  vendor need any agreement with the school or with Schoollog?
- **C5.** Could either the school or Schoollog be treated as a significant data fiduciary? What would change?
- **C6.** Is a shorter pilot agreement acceptable for the 8-week pilot, or should the full contract be in place
  from the first recording?

### D. Retention periods

**Context.** Audio: deleted automatically after 90 days by default (per-school setting); after 30 days it moves to
a cheaper storage tier but is still stored. Playback copies are deleted with the audio. Transcripts, analyses,
scores, disputes and the access log: kept, no period set yet. Backups: continuous database backup [retention
window to be confirmed] and a nightly export to a separate backup store with file versioning [period to be
confirmed]. After an erasure, a minimal record of the erasure is kept. A fixed set of recordings may be kept for
quality evaluation (see J).

- **D1.** Is 90 days a reasonable default for audio, given that it contains children's voices? Should it be
  shorter?
- **D2.** What retention periods would you advise for transcripts, scores and reports, disputes, and the access
  log?
- **D3.** Is it acceptable that deleted data remains in backups until the backups expire, if that period is stated
  in the forms? What period would you consider reasonable?
- **D4.** Should anything be deleted when a student leaves the school, or when a staff member leaves employment?
- **D5.** At the end of the contract, what should happen to the school's data, and how fast?
- **D6.** Is there any other law that requires the school or Schoollog to keep any of these records for a minimum
  period?

### E. Cross-border transfer for AI processing

**Context.** Product rule: data stays in India unless an exception is explicitly approved. Audio and
speech-to-text stay in India [server location to be confirmed]. Only text transcripts (never audio) are sent to an
AI language model provider, after masking. Masking is automated and may miss items, for example names not on the
list, misspelled names, or numbers spoken as words. Staff names are not masked by default. The provider is not yet
chosen; we are comparing providers on India-region availability, data retention, whether they train on customer
data, and whether a data processing agreement is available. Some candidates may process data outside India. Some
providers may keep text temporarily (for example for caching or abuse monitoring). The AI call tracing tool stores
AI inputs and outputs [hosting region to be confirmed].

- **E1.** May masked transcripts be sent to an AI provider that processes them outside India? If so, on what
  conditions? Are there countries to which transfer is restricted, and how should we check this over time?
- **E2.** Is a masked transcript still personal data (it still contains what staff and students said, and staff
  names)? Would masking staff names too change your view?
- **E3.** If processing outside India is used, what must the parent and staff forms say? Is a separate consent
  needed?
- **E4.** What terms should we require from the AI provider: no training on our data, retention limits, deletion,
  processing location, its own sub-providers, breach notice, anything else?
- **E5.** Does temporary retention by the provider (caching, abuse monitoring) need to be handled or disclosed?
- **E6.** For children's data in particular, would you advise using only an India-region AI option even if it
  costs more?
- **E7.** Do the same questions apply to the supporting services (error monitoring, AI call tracing, email) if
  any of them is hosted outside India?

### F. Staff consent and use for appraisal

**Context.** Teachers, front-desk staff and possibly counsellors are recorded and receive rubric-based feedback.
Scores are produced mainly by automated analysis. A person reviews a report when the staff member disputes a
score or when the software flags a recording; not every report is reviewed by a person. If a dispute is accepted,
the human score is shown and the original automated score stays in the history. Administrators can see some
"Internal" measures that staff do not see. Whether reports will be used for appraisal is not decided.

- **F1.** For staff, is consent the right basis for this processing, or is another basis available in an
  employment setting? If consent, how do we make sure it is freely given, given the employer-employee
  relationship?
- **F2.** Can a school make recording a condition of the job? What should happen if a staff member says No or
  withdraws?
- **F3.** If reports are used for appraisal, pay, promotion or discipline, what extra notice, consent or
  safeguards would you advise? Is there concern about decisions based mainly on automated analysis? Should a
  person review every score that is used in such a decision?
- **F4.** Is the dispute process an adequate way for staff to correct their data? Is it acceptable to keep the
  original automated score in history after a dispute is accepted?
- **F5.** Should staff be able to see the "Internal" measures that administrators see about them?
- **F6.** Should staff always be told in advance when they are being recorded?
- **F7.** Are there other laws or rules (employment law, service rules for school staff, employment contracts)
  that we should check?

### G. Call recording notice

**Context.** A short spoken notice plays before an incoming reception call connects (see
`call-recording-notice.md`). Callers include parents, prospective parents, vendors and sometimes students. The
analysis is about the receptionist. The caller is not scored, but the call is given a category (for example
complaint, information or fee query) and the caller's share of talk time is measured. [Whether caller phone
numbers or other call details are imported with the recording is to be confirmed.] Consent in Sabha is recorded
per call line, not per call; there is currently no per-call "caller objected" marker.

- **G1.** Is a spoken notice before the call connects adequate for callers, or is their consent needed? If
  consent, does continuing the call after the notice count?
- **G2.** Must the notice mention automated or AI analysis, Schoollog, how long recordings are kept, or where to
  find a fuller privacy notice? Is the shorter variant (about 7 seconds) enough?
- **G3.** Which of the options for callers who object (listed in the call notice draft) are acceptable?
- **G4.** What should happen when the caller is a child?
- **G5.** For outgoing calls made by reception, is it enough for the receptionist to read the short notice at the
  start?
- **G6.** Are there telecom rules, or terms of the school's phone provider, about call recording that we should
  check?
- **G7.** Should call recordings and transcripts have a different retention period from lesson recordings?

### H. Grievance redressal and breach notification

**Context.** The forms name a grievance officer [at the school] and a Schoollog contact. Sabha logs every playback,
export and score change. Schoollog monitors the system and will have an incident runbook [to be written].

- **H1.** Who should be the grievance contact named in the forms: the school, Schoollog, or both? Are there
  requirements for that person (for example being based in India)?
- **H2.** What response time should we commit to for grievances and requests?
- **H3.** Does the school or Schoollog need to appoint a data protection officer?
- **H4.** If there is a data breach, who must notify the Data Protection Board and the affected people, how fast,
  and with what content? What should the contract require Schoollog to tell the school, and by when?
- **H5.** Because students are not identified, a breach of lesson recordings could not be linked to specific
  students. Should we plan to notify all parents of every affected class?
- **H6.** What records of grievances, requests and breaches should be kept, and for how long?

### I. Withdrawal of consent and erasure requests, including backups

**Context.** The erasure function deletes audio, intermediate files, transcripts, analyses, scores and disputes
for a recording, a staff member or a whole school, and keeps a minimal record that the erasure happened. Because
students are never identified, we cannot erase one student's voice from a lesson; a parent's withdrawal can only be
handled at class level (stop recording that class, and possibly delete that class's existing recordings). Erased
data remains in backups until they expire [period to be confirmed]. Text already sent to the AI provider is subject
to the provider's own retention. Dispute outcomes are also stored as calibration data for checking scoring
accuracy.

- **I1.** How quickly should withdrawal and erasure requests be acted on?
- **I2.** When a parent withdraws, is it acceptable that we cannot remove one child's voice? Which of the options
  in section 8 of the parent form is acceptable: (a) delete that class's earlier recordings on request, or (b) let
  them expire on the normal schedule?
- **I3.** Does withdrawal require deleting reports already produced from earlier recordings, or only stopping new
  processing?
- **I4.** Is deletion from live systems, with backups expiring after [N] days, acceptable? Must this be stated in
  the forms?
- **I5.** Is it acceptable to keep a minimal record of each erasure (what, when, by whom) and the access log?
- **I6.** Must data derived from erased records (for example calibration records from disputes, or aggregate
  quality figures) also be erased?
- **I7.** If a staff member asks for erasure but the school wants to keep records (for example if reports are used
  in appraisal), how should that be handled?
- **I8.** How should the identity of a person making a request be checked?

### J. Use of recordings to check quality

**Context.** To measure how accurate transcripts and scores are, Schoollog plans for human annotators to
transcribe and label speakers on a sample of recordings, and for human raters to score a sample against the rubric.
A fixed evaluation set of recordings and transcripts is kept unchanged so later versions of the software can be
compared against it, which may mean keeping some recordings longer than 90 days. Some recordings made before the
pilot may also be used. Annotators are asked to anonymise names in the transcripts they type. [Whether annotators
and raters are Schoollog employees or contractors, and where the annotation tool is hosted, is to be confirmed.]

- **J1.** Is quality checking a separate purpose that must be stated in the parent and staff forms (see the
  optional clause in the parent form, section 5)? Does it need its own consent?
- **J2.** Can recordings in the evaluation set be kept longer than 90 days? If so, for how long, and with what
  wording?
- **J3.** What agreements do annotators and raters need (confidentiality, data handling, location)?
- **J4.** What consent is needed for recordings made before the pilot, and would these drafts cover them?

### K. The enclosed drafts

- **K1.** Please review the three drafts and tell us what is missing, wrong or unclear.
- **K2.** Which documents need a signature, and which can be a notice only?
- **K3.** Do we also need a privacy notice in the Sabha app or on the school's website?
- **K4.** If a form changes after consent has been collected, must consent be collected again?
