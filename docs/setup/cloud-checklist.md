# Cloud setup checklist

Plan task 0.5. For a person to work through by hand in the cloud consoles; nothing here is automated. Terraform
(plan task 1.3) takes over the AWS parts later, so keep the names you choose here.

Rules that apply throughout (from `CLAUDE.md`):

- **Data stays in India** (golden rule 12). Every resource that stores or processes customer data goes in AWS
  `ap-south-1` (Mumbai) or Atlas AWS Mumbai. Anything that would put data elsewhere needs an explicit decision
  first; this list marks those places.
- **Secrets only in environment variables or a secret store** (golden rule 11). Never paste a key, password or
  connection string into the repo, a ticket or chat. Record names and IDs here, never secrets.

Record as you go (no secrets):

| Item | Value |
| --- | --- |
| AWS account ID (staging) | |
| AWS account ID (production) | |
| S3 buckets (staging): audio / artefacts / backups | |
| S3 buckets (production): audio / artefacts / backups | |
| App IAM role ARN (staging / production) | |
| Atlas organisation / project | |
| Atlas cluster name (staging / production) | |
| GitHub organisation / repository | |
| Sentry organisation / project | |
| SES sending domain | |

---

## 1. AWS account

- [ ] Create the AWS account with a shared team mailbox (not a personal email) as the root user.
- [ ] Turn on MFA for the root user. Store the root credentials offline; do not use root day to day.
- [ ] Decide on account structure. Recommended: AWS Organizations with separate **staging** and **production**
      accounts, so a mistake in staging cannot touch production data.
- [ ] Set up IAM Identity Center for people (named users, MFA required). No long-lived access keys for humans.
- [ ] In each account, set the console default region to **Asia Pacific (Mumbai) `ap-south-1`**.
- [ ] Optional guard: a Service Control Policy that denies actions outside `ap-south-1` (exempt global services
      such as IAM, Organizations, Budgets and billing).
- [ ] Turn on CloudTrail (all regions, logs to a bucket in `ap-south-1`).

## 2. Billing alerts

Set the amounts from the approved pilot budget; this checklist deliberately does not suggest figures.

- [ ] AWS Budgets: one monthly cost budget per account, with email alerts at 50%, 80% and 100% of actual spend
      and at 100% of forecast spend, sent to the team mailbox.
- [ ] Turn on AWS Cost Anomaly Detection with an email subscription.
- [ ] MongoDB Atlas: billing alerts for the organisation (see section 5).
- [ ] Note who reviews the bill each month: ______

## 3. S3 buckets

Three buckets per environment, in `ap-south-1`, so each kind of data gets its own lifecycle and access rules.
Local development uses RustFS instead (`S3_ENDPOINT_URL`, ADR 0003). Terraform (plan task 1.3) will codify this
section.

| Bucket | Setting | Holds |
| --- | --- | --- |
| `sabha-<env>-audio-<suffix>` | `S3_BUCKET_AUDIO` | Uploaded originals |
| `sabha-<env>-artefacts-<suffix>` | `S3_BUCKET_ARTEFACTS` | Pipeline outputs: derived audio, transcripts, analyses |
| `sabha-<env>-backups-<suffix>` | `S3_BUCKET_BACKUPS` | Database backups (plan task 7.3) |

- [ ] Create the three buckets for staging and for production in `ap-south-1` (bucket names are global, so add a
      suffix).
- [ ] **Block Public Access:** turn on all four settings at the **account** level and on each bucket.
- [ ] **Object Ownership:** "Bucket owner enforced" (ACLs disabled).
- [ ] **Default encryption:** SSE-S3 (or SSE-KMS with a key in `ap-south-1` if you want key-level audit).
- [ ] **TLS only:** add a bucket policy that denies requests where `aws:SecureTransport` is `false`.
- [ ] **Lifecycle rules:**
  - [ ] *Audio bucket:* expire objects after 90 days (the default audio retention). Plan task 1.3 also moves them to
        Infrequent Access after 30 days.
  - [ ] *Artefacts bucket:* expire derived audio (normalised, compact and playback copies) after 90 days with a rule
        filtered by object tag `data-class=audio`; the preprocessing code (plan task 3.2) must set that tag.
  - [ ] *Audio bucket:* abort incomplete multipart uploads after 7 days. Browser uploads are multipart; abandoned
        ones otherwise keep costing storage.
  - [ ] *Backups bucket:* turn on versioning (plan task 1.3); retention is decided in plan task 7.3.
  - [ ] If you turn on versioning, also expire noncurrent versions after the same number of days, or deleted audio
        survives as old versions.
  - [ ] Retention for transcripts and reports: wait for the lawyer's answer (`docs/legal/drafts/`); do not add a
        rule yet.
- [ ] **CORS** (browsers upload directly with presigned URLs, golden rule 2): allow the web app origin only, methods
      `PUT` and `GET`, and expose the `ETag` header (multipart completion needs it).

```json
[
  {
    "AllowedOrigins": ["https://app.<your-domain>"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

## 4. IAM for the application

Prefer an **IAM role** attached to the compute (EC2 instance profile or ECS task role). The app then needs no
access keys: leave `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` empty and the AWS SDK picks up the role.

- [ ] Create role `sabha-app-<env>` in each account with only this policy (replace the placeholders):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOwnBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:ListBucketMultipartUploads"],
      "Resource": [
        "arn:aws:s3:::<audio-bucket>",
        "arn:aws:s3:::<artefacts-bucket>",
        "arn:aws:s3:::<backups-bucket>"
      ]
    },
    {
      "Sid": "ReadWriteOwnObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetObjectTagging",
        "s3:PutObjectTagging",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts"
      ],
      "Resource": [
        "arn:aws:s3:::<audio-bucket>/*",
        "arn:aws:s3:::<artefacts-bucket>/*",
        "arn:aws:s3:::<backups-bucket>/*"
      ]
    },
    {
      "Sid": "SendFromOurDomainInMumbai",
      "Effect": "Allow",
      "Action": ["ses:SendEmail", "ses:SendRawEmail"],
      "Resource": "arn:aws:ses:ap-south-1:<account-id>:identity/<your-domain>"
    }
  ]
}
```

- [ ] Do not grant `s3:*`, bucket-policy or IAM permissions to the app.
- [ ] If an IAM **user** with access keys is unavoidable (for example, a server outside AWS), give it the same policy,
      keep the keys in the deployment's secret store, and rotate them at least every 90 days.

## 5. MongoDB Atlas (Mumbai)

- [ ] Create the Atlas organisation (team mailbox as owner, MFA on) and one project per environment.
- [ ] Create an **M10** cluster per environment on **AWS, Mumbai (`ap-south-1`)**, MongoDB **7**. Atlas clusters are
      replica sets, which Sabha needs for transactions and change streams.
- [ ] Turn on Cloud Backup; choose the snapshot schedule and retention with plan task 7.3.
- [ ] **Network access:** use a private endpoint or VPC peering to the app's VPC if possible. Otherwise add only the
      app servers' fixed IPs to the access list. Never `0.0.0.0/0`.
- [ ] **Database user** per environment: `readWrite` on the `sabha` database only, a generated password, stored in
      the secret store.
- [ ] Copy the `mongodb+srv://` connection string into the secret store as `MONGO_URI`.
- [ ] Atlas billing alerts for the organisation, sent to the team mailbox.

## 6. GitHub

GitHub hosts code, not customer data; keep it that way (no recordings, transcripts or real names in the repo).

- [ ] Create the GitHub organisation; require two-factor authentication for all members.
- [ ] Create the private repository `sabha` with default branch `main`, then push this repo.
- [ ] Ruleset on `main`: pull request required with at least one approval, required status checks (add them after
      plan task 1.2 creates CI), no force pushes, no deletion.
- [ ] Turn on Dependabot alerts, and secret scanning with push protection if your plan includes it.
- [ ] Actions: allow only GitHub-authored and selected actions; set workflow permissions to read-only by default.
- [ ] Create `staging` and `production` environments; require a reviewer for `production` deployments.

## 7. Sentry

- [ ] **Before creating anything,** check which regions Sentry can store your organisation's data in. If none is
      in India, using it sends error data outside India and needs an explicit decision (golden rule 12). The options
      are to self-host Sentry in `ap-south-1`, or to get approval and turn on server-side scrubbing so no
      transcript text, names or contact details are sent.
- [ ] Once decided: create one project for the API and workers and one for the web app, with separate environments
      for staging and production. Put each DSN in the secret store as `SENTRY_DSN`.
- [ ] Turn on default PII scrubbing and IP address scrubbing.

## 8. Not in this checklist

- **Langfuse:** self-host in `ap-south-1` unless a hosted region is approved (same rule as Sentry). Covered when
  plan task 5.1 builds the LLM gateway.
- **LLM providers:** decided through `docs/llm-providers.md` (plan task 0.6).
- **Amazon SES:** verify the sending domain in `ap-south-1` (with DKIM) and request production access before
  notifications ship (plan task 2.7).
- **Identity provider (OIDC):** Auth0 or Keycloak, decided in ADR 0002 (plan task 1.5).

## 9. Check it works

- [ ] Fill in the environment's settings (see `.env.example`) from the secret store.
- [ ] Run `uv run python scripts/check_env.py` on a machine in that environment. Every service should print PASS.
