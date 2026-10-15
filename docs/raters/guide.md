# Rater guide: scoring lessons with the teaching rubric

For the people who score lessons by hand (plan task P4.4). Your scores are the reference the software is checked
against, so they matter more than speed.

## The ground rules

- **Score the teacher's teaching, never the students.** Students' answers are only evidence of what the teacher
  did. Never write a student's name in a note.
- **Score blind.** Your sheet has no AI scores, and you must not look for them. Don't discuss scores with other
  raters until the coordinator says the round is closed.
- **Score what you can point to.** Every anchor below describes something you can hear or read. If you can't point
  to a moment for a score, choose the lower level.
- **Use the whole lesson.** Listen to, or read, the full recording before scoring any dimension.
- **One score per dimension, a whole number from 1 to 5.** The sheet rejects blanks, halves and anything outside
  1 to 5.

## How to fill in your sheet

1. Open your sheet (`scores-<your rater id>.csv`, imported into Google Sheets) and the **anchors** tab next to it.
2. Each row is one recording and one dimension, in a shuffled order. Open the transcript link in the row.
3. Read the dimension's anchors, find the level that matches what you saw, and type the number in `score`.
4. In `note`, write the time of the moment that decided your score, for example `12:40 asks "kyun?" and waits`.
   One short line is enough.
5. When every row has a score, download the sheet as CSV and send it to the coordinator. The import script checks
   it; if anything is missing or out of range, the whole sheet comes back to you with the list of problems.

## Choosing between two levels

- Start from level 3 and ask: does the lesson clearly show everything in level 4? If yes, check level 5. If no,
  check whether it falls short of level 3.
- If a lesson shows level 5 behaviour once and level 2 behaviour the rest of the time, score what was typical,
  and mention the strong moment in the note.
- Can't decide between two levels after reading both anchors twice? Choose the lower one and say why in the note.

## Worked examples

These use the example lines written into the rubric file, so they show the two ends of each scale.

**1. Checks for understanding.** The teacher says: *"Sab samajh aa gaya na? Good. Chalo next topic."* and nothing
else checks understanding in the lesson. That is a yes/no check accepted without anyone explaining anything. It
matches level 1 ("asks 'samajh aaya?' and moves on without waiting for a reply"). **Score: 1.** Note: the time of
the line.

Compare: *"Ek kaam karo, copy mein 2/5 + 1/5 solve karke dikhao. ... Kuch logon ne 3/10 likha hai. Ruko, ek baar
phir dekhte hain denominator ke saath kya hota hai."* Students apply the idea, the teacher looks at the answers and
re-explains because of them. If the teacher does this at several points with more than one student, that is level
5. If it happens once, level 4 fits better: "responds to wrong answers by correcting or re-explaining".

**2. Use of examples.** *"Fractions add karne ka rule board pe likh diya hai, bas yaad kar lo, exam mein aayega."*
No example, no worked problem: level 1. Against that, *"Socho ek pizza ke 8 slices hain aur Aman ne 3 kha liye, toh
usne pizza ka 3/8 khaaya. Ab yahi 3/8 number line pe dikhaate hain, dekho same cheez hai."* is an everyday example
linked back to the concept. Level 5 also asks for two or more examples and one worked step by step, so check the
rest of the lesson before giving 5.

**3. Recap and closure.** *"Bell baj gayi, chalo bas, kal milte hain."* The lesson ends with no summary: level 1.
If the recording stops before the end of the lesson, don't guess: write `recording ends early` in the note and tell
the coordinator, because the rubric does not yet say how to score that case.

## The anchors (teaching rubric v0.1)

Generated from `rubrics/teaching.school.v0.1.yaml`. The anchors tab in your sheet comes from the same file; if the
two ever differ, the sheet is right and this guide needs regenerating.

### Concept clarity (`concept_clarity`)

The teacher states the main idea of the lesson, defines its key terms and explains it in a logical order of steps.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher never states the main idea, and the explanation contradicts itself or contains a clear factual error that is not corrected. |
| 2 | The teacher names the topic but uses key terms without defining them, and the explanation skips steps or jumps back and forth. |
| 3 | The teacher states the main idea and defines most key terms, but at least one step is skipped or explained out of order. |
| 4 | The teacher states the main idea, defines each key term when first used, and explains it step by step in order. |
| 5 | The teacher states the main idea at the start, defines each key term when first used, explains it step by step, and re-explains it in a different way (simpler words, the other language or a board diagram) when a student asks a question or gives a wrong answer. |

### Use of examples (`use_of_examples`)

The teacher uses examples, analogies, demonstrations or worked problems that match the concept being taught and links them back to it.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher gives no example, analogy, demonstration or worked problem at any point in the explanation. |
| 2 | The teacher mentions an example only in passing or gives one that does not match the concept being taught. |
| 3 | The teacher gives at least one relevant example or worked problem but does not say how it connects to the concept. |
| 4 | The teacher gives two or more relevant examples or worked problems and says how each connects to the concept. |
| 5 | The teacher gives two or more relevant examples, including one from an everyday setting such as home, the market or sports, works at least one through step by step, and links each back to the concept. |

### Checks for understanding (`checks_for_understanding`)

The teacher checks at points during the lesson whether students can explain or use the idea, and acts on what the answers show.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher does not check understanding at any point, or asks 'samajh aaya?' and moves on without waiting for a reply. |
| 2 | The teacher asks only yes/no checks such as 'clear hai?' and accepts a chorus 'yes' without asking anyone to explain or show working. |
| 3 | The teacher asks at least one check that needs students to explain, answer or show working, but moves on without responding to wrong or missing answers. |
| 4 | The teacher asks checks that need an answer or explanation at more than one point in the lesson and responds to wrong answers by correcting or re-explaining. |
| 5 | The teacher checks at several points with tasks that need students to explain or apply the idea, invites answers from more than one student, and re-explains or changes the next step based on the answers given. |

### Questioning quality (`questioning_quality`)

The teacher asks a mix of questions, including open questions that ask students to explain, compare or predict, gives time to answer and follows up on answers.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher asks no questions, or answers their own questions straight away without pausing for students. |
| 2 | The teacher asks only recall questions with one-word answers and moves on after the first answer. |
| 3 | The teacher asks mostly recall questions with at least one open question (why, how, what if), but answers it themselves or takes the first reply without a pause. |
| 4 | The teacher asks several open questions, pauses for answers, and follows up on some answers with prompts such as 'kyun?' or 'kaise pata?'. |
| 5 | The teacher regularly asks open questions, pauses before taking answers, and follows up by asking for reasons or by asking another student to agree, disagree or build on an answer. |

### Pacing (`pacing`)

The teacher moves through the parts of the lesson at a speed that leaves time for explanation, questions and practice, and changes speed in response to student questions or answers.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher talks through the material without pausing for questions or practice, or leaves long stretches with no instruction, and rushes or skips content at the end ('baaki ghar pe padh lena'). |
| 2 | The teacher spends most of the lesson on one part and rushes through the rest, with few pauses for questions or practice. |
| 3 | The teacher gives time to each part of the lesson with some pauses for questions, but keeps the same speed after student questions or wrong answers. |
| 4 | The teacher gives time to each part of the lesson, including practice, pauses for questions, and slows down at least once to re-explain after a student question or wrong answer. |
| 5 | The teacher announces the move from one part of the lesson to the next, pauses for questions and practice in each part, slows down to re-explain after wrong answers, and moves on once students answer correctly. |

### Recap and closure (`recap_and_closure`)

The teacher ends the lesson by restating the key points, connecting them to the lesson's aim and saying what comes next.

| Score | What you can point to |
| --- | --- |
| 1 | The lesson ends without any summary, for example stopping mid-explanation at the bell or ending with only 'chalo, bas'. |
| 2 | The teacher ends with only a homework instruction or 'revise kar lena' without restating any key point. |
| 3 | The teacher lists what was covered ('aaj humne X aur Y kiya') but does not restate the key points themselves. |
| 4 | The teacher restates the key points of the lesson at the end and says what comes next or what the homework practises. |
| 5 | The teacher asks students to state the key points, adds or corrects what is missing, connects them to the lesson's aim, and says what comes next or what the homework practises. |
