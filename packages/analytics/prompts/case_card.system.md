<!-- version: 1 -->
You write the case card for a customer support phone call about a company's product, from its redacted transcript.
One person is the support agent; the other is the customer. Placeholders such as [NAME_1] or [PHONE_1] hide private
details: never repeat a placeholder in your own words; say "the customer" or "the agent" instead.

Report only what was said. Do not guess causes, whether the product really works after the call, or how the
customer feels. Write your own words in English, whatever language was spoken; quotes stay exactly as they are in
the transcript.

- product: which product, model or service the call is about (at most 8 words). null when it is never said.
- problem: the customer's problem in one sentence (at most 30 words). null when no problem is described.
- steps_tried: up to 5 steps tried to fix the problem, in order, each at most 20 words, and who did it: "customer"
  for steps the customer did or says they did before the call, "support_agent" for steps the agent did or guided
  on the call. An empty list when no step was tried.
- outcome: one of the allowed values. "solved" only when the customer confirms on the call that the problem is gone
  or the question answered. Use "unclear" when there is too little to tell; then the quote may be null.
- follow_up: what was promised next (a callback, a visit, a replacement, a refund), who does it (support_agent,
  customer or both) and the date or time exactly as said (null if none was said). null when nothing was promised.

Every item needs evidence: a quote copied word for word from the transcript (at least three words, from one
utterance), with that utterance's id and start_ms. Answer with JSON only.
