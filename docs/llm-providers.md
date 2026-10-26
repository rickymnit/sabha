# LLM providers

Plan task 0.6. A comparison sheet to fill in from each provider's own documents and written answers. Every value
starts as **TBD** and is replaced only with something a provider has published or written to us, with the source
link and the date checked. Nothing here comes from memory (golden rules 6 and 12).

## Decision so far

- **2026-10-24:** OpenAI **shut down `o3-mini` on 2026-10-23** (deprecations page, checked 2026-10-24: replacement
  suggested `gpt-5.6-sol`); our calls failed with HTTP 404 "model has been deprecated". The product owner chose
  **`gpt-6-luna`** for both tiers (scoring and synthesis, and the role tie-breaker), the lowest-priced current model.
  Rejected as stop-gaps: `gpt-5` and `gpt-5-mini`, which OpenAI shuts down on 2026-12-11, inside the pilot.
  Whether luna judges as well as a larger model is not yet measured: the bake-off (P5.3) compares models on
  human-rated recordings, and no quality figure is claimed until then (golden rule 6).
- **2026-10-16:** the product owner chose **OpenAI** with the model **`o3-mini`** for scoring and synthesis.
  To confirm from OpenAI's documentation and our API dashboard, not from memory:
  - that `o3-mini` is available to our API project and not scheduled for retirement;
  - which reasoning-effort setting to use (the bake-off can compare them);
  - whether it accepts a `temperature` parameter. The plan (P5.6) assumes temperature 0 for repeatable scores; if
    a reasoning model does not take one, the bake-off (P5.3) must measure score stability across repeated runs
    instead of assuming it.
- ChatGPT is the consumer app. Sabha calls the **OpenAI API** with the key of a dedicated Sabha project, under the
  API's terms, not a ChatGPT account.
- **Not yet approved for real school data.** Golden rule 12 keeps data in India. Before any real transcript is
  sent, the residency and retention answers below must be in writing and the lawyer must answer
  `docs/legal/drafts/questions-for-lawyer.md`, group E (cross-border AI processing). Only then does an
  `OPENAI_API_KEY` go into the staging or production configuration. This is a process rule: the code does not
  enforce it (decided 2026-10-16), so whoever configures a deployment checks it.
- Text sent is always redacted first (phones, Aadhaar-like and PAN-like numbers, emails, listed student names;
  `packages/llm/sabha_llm/redact.py`). That reduces what leaves, but it is not a residency answer.

## Comparison

One row per provider. The bake-off (plan task 5.3) compares up to three; rows 2 and 3 stay empty if OpenAI is the
only candidate.

| Field | OpenAI | Candidate 2 | Candidate 3 |
| --- | --- | --- | --- |
| Models we would use: mid tier (scoring, synthesis) | `gpt-6-luna` (chosen 2026-10-24). Model page, 2026-10-24: no deprecation or shutdown date listed; Responses API; structured outputs supported. Was `o3-mini` (chosen 2026-10-16, shut down 2026-10-23) | TBD | TBD |
| Models we would use: small tier (role tie-breaker) | `gpt-6-luna` (chosen 2026-10-24) | TBD | TBD |
| Reasoning effort / temperature support | `gpt-6-luna`: reasoning effort none, low, medium (default), high, xhigh, max (model page, 2026-10-24); temperature not stated, so not sent | TBD | TBD |
| India region available (yes / no / how) | TBD | TBD | TBD |
| Data retention policy (API inputs and outputs) | TBD | TBD | TBD |
| Training on our data (default, and how to opt out) | TBD | TBD | TBD |
| DPA available (and covers DPDP Act, 2023?) | TBD | TBD | TBD |
| Structured output / JSON schema support | Supported (model page, 2026-10-19) | TBD | TBD |
| Prompt caching (how, minimum prefix, price) | `gpt-6-luna`: cached input $0.01, cache writes $0.125 per million tokens (model page, 2026-10-24). Automatic; usage reports `cached_tokens` and `cache_write_tokens`, both part of `input_tokens` (seen in our own calls, 2026-10-26) | TBD | TBD |
| Batch API and discount | TBD | TBD | TBD |
| Rate limits for our tier | TBD | TBD | TBD |
| Price per million input tokens | $0.10 (`gpt-6-luna`, model page, 2026-10-24); was $1.10 (`o3-mini`, 2026-10-19) | TBD | TBD |
| Price per million output tokens | $0.50 (`gpt-6-luna`, model page, 2026-10-24); was $4.40 (`o3-mini`, 2026-10-19) | TBD | TBD |
| Source link(s) | https://developers.openai.com/api/docs/models/gpt-6-luna, https://developers.openai.com/api/docs/deprecations (o3-mini: https://developers.openai.com/api/docs/models/o3-mini) | TBD | TBD |
| Date checked | 2026-10-24 (o3-mini: 2026-10-19) | TBD | TBD |

Prices go into the gateway's price table (plan task 5.1) only from this sheet, with the date; cost figures are
never estimated.

## Decision rule

In this order:

1. **Data residency.** A provider that cannot keep processing and storage in India, or whose cross-border
   processing the lawyer has not approved for redacted transcripts, is out, however good it is.
2. **Agreement with human raters** in the bake-off (plan task 5.3): JSON validity, grounding pass rate (quotes
   found in the transcript), stability across repeated runs, and agreement with the calibration raters.
3. **Cost**, from the prices in this sheet and the measured tokens per recording.

The choice is recorded in `docs/adr/0004-llm-choice.md` with the bake-off report.

## Email to send each provider

> **Subject:** Data residency, retention and DPA terms for API use (education product, India)
>
> Hello,
>
> We are building Sabha, a product that gives teachers and school staff in India feedback on recorded lessons
> and front-desk calls. We plan to use your API to score transcripts against a teaching rubric. Personal data
> (phone numbers, ID numbers, emails and students' names) is removed before any text is sent, but the text is
> still classroom speech from schools in India, so we need the following in writing before we use the API with
> real data:
>
> 1. **Data residency.** Can API requests be processed and any data stored only in India? If so, how is this
>    set up (region, endpoint, project or account setting) and for which models? If not, in which countries
>    are requests processed and stored?
> 2. **Retention.** How long are API inputs, outputs and logs kept, including for abuse monitoring? Is zero or
>    reduced retention available, and how is it enabled?
> 3. **Training.** Are API inputs or outputs used to train or improve models, by default or ever? How is this
>    confirmed for our account?
> 4. **Data processing agreement.** Do you offer a DPA, and does it address India's Digital Personal Data
>    Protection Act, 2023? Please send the current version.
> 5. **Sub-processors.** Which sub-processors may handle our data, and where are they located?
> 6. **Models and features.** For o3-mini, please confirm whether it is available to our project and for how long,
>    whether it accepts a temperature setting, and structured output with a JSON schema, prompt
>    caching, batch processing and the rate limits for our expected tier.
> 7. **Pricing.** Current input, output, cached-input and batch prices per million tokens for o3-mini.
>
> Links to the current published documents are fine where they answer a question. Thank you.
>
> [Name], [Role], Schoollog / Sabha
> [Email], [Phone]
