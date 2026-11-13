# ADR 0013: What the agent said well and badly, checked against product information

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Sales and support managers said the report does not show what the agent said right and wrong. Two reasons:

- The went-well, needs-work and next-time lists are private coaching. Managers see only each rubric point's score,
  a short reason and quotes, and the quotes are not marked good or bad.
- Approved product information (`product_info`) was used only for the sales next-time coaching tips. A wrong price
  or policy never affected a score, and support used it not at all.

The owner decided on 2026-11-13:

1. A per-call list of plus points and drawbacks is the call's evaluation, so managers see it as well as the agent.
   Next-time coaching stays private.
2. A product statement that contradicts the approved information lowers the relevant scores.

## Decision

1. **A new step, `sabha_analytics.moments`**, runs for sales and support calls whether or not the scores verified.
   It lists up to 10 moments, each with:
   - `kind`: plus or drawback;
   - `text`: at most 30 words, in English, naming the agent by role, never by gender or name;
   - `evidence`: a verified quote (golden rule 5);
   - `fact`: for product statements, `matches` or `contradicts` with the approved entry's id, or `not_covered`.

   An id that was not given, or a verdict that does not fit its id, is refused and re-asked once. So a moment can
   never claim a check against unapproved information, and a statement the information does not cover is never
   called wrong. Moments whose quote is not found are left out and counted.
2. **Scoring sees the approved information for sales and support.** The scoring context (`scoring.context` v2) gets
   an "Approved product information" section with one rule: a contradicted fact lowers the product, value, price
   or troubleshooting dimensions, and the rationale says what the entry says. Other types get no section, so their
   prompt is unchanged.
3. **The API returns `moments` to everyone who may see the report** (not in `PRIVATE_COACHING`), with each entry's
   title and text attached.
4. **The report page** shows a one-line count at the top ("3 plus points, 5 drawbacks (3 wrong product facts)") that
   opens a "What <name> said" panel: plus points and drawbacks side by side, each with its time, quote and the entry
   it matched or contradicted.
5. **Up to 80 active product information entries** (was 40). All of them go into the scoring, moments and coaching
   prompts, about 45 × 800 characters today.

## Consequences

- One more LLM call per sales or support analysis, and a longer scoring prompt when entries exist. Prompt caching
  covers the repeated prefix.
- How often the model's fact verdicts are right is not yet measured. There is no human-annotated set for it
  (golden rule 6). The verdicts cite the entry, so a manager can check one with a click.
- Reports made before this decision have no `moments`. Re-analysis adds them.
