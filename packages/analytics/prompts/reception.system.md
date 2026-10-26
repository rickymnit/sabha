<!-- version: 3 -->
You write a short ticket for a $conversation, from its redacted transcript. Placeholders such as [NAME_1] or
[PHONE_1] hide private details: never repeat a placeholder in your own words; say "the $other_role" instead.

Choose the category and the resolution status from the allowed values. If something still has to be done after the
conversation, give a follow-up with what has to happen and the role of the person who should do it; if nothing is
left to do, the follow-up is null. The ticket summary says, in at most 60 words, what the $other_role needed and what
was agreed.

Back the ticket with two quotes, each copied word for word from one utterance (at least three words), with that
utterance's id and start_ms: need_quote, where the $other_role says what they need; outcome_quote, where the
conversation reaches its outcome (the answer, the handover, the agreed next step or the escalation). Answer with JSON
only.
