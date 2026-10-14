# Annotation guidelines: gold transcripts

For people who label recordings in Label Studio (setup: `infra/annotation/README.md`).

Your transcripts become the **gold set**: the reference we compare Sabha's automatic transcripts and
speaker labels against. A mistake in the gold set turns into a wrong score for the system, so we
prefer slow and exact over fast. When a rule below doesn't cover what you hear, ask the annotation lead
and note the task number, rather than guessing.

## Before you start

- **The recordings are real.** They contain real teachers, front-desk staff, parents and students.
  Listen with headphones in a private place. Work only inside Label Studio: don't download recordings,
  don't copy transcript text out, and never paste it into another website or app (translation or
  transliteration sites, chatbots, online keyboards). Text pasted there leaves our control.
- **Typing Devanagari.** Use the Hindi phonetic or transliteration keyboard built into Windows or
  macOS, which works offline. Don't use websites or browser extensions to type Hindi. If you can't type
  Devanagari, take only recordings marked `english` (shown above the waveform as the language mix).
- **Stop if a recording shouldn't be there.** If you hear something that doesn't look like a lesson or
  a front-desk conversation (a counselling session, a private phone call, a medical conversation), stop
  and tell the lead. Don't annotate it.

## How a task works

1. Press a label key (`1` Teacher, `2` Student(s), `3` Receptionist, `4` Caller, `5` Other,
   `6` Silence) or click the label.
2. Drag across the waveform over one speaker's turn. That makes a region.
3. Click the region and type what was said in the box. Leave the box empty only for Silence.
4. Repeat until every part of the recording where someone speaks is covered, then **Submit**.

The short version of these rules is shown above the waveform in every task.

## 1. Regions

- One region is one speaker's turn. When the speaker changes, start a new region.
- Split a turn longer than about 30 seconds at a natural pause. Short regions are easier to check.
- Start the region just before the first sound of the first word and end it just after the last word.
  Zoom in on the waveform to place the edges. Never cut through a word.
- Small gaps between regions are fine. Regions of different speakers may overlap (section 8).
- Every stretch of speech that belongs to the conversation must be inside a region.

## 2. Speaker labels

Labels describe the person's **role in this recording**, not who they are. Never try to work out or note
which student is speaking.

| Label | Use for |
| --- | --- |
| Teacher | The staff member leading the lesson. One person per recording. A second adult in the room (another teacher, the principal on a visit, an assistant) is **Other**. |
| Student(s) | Any student or group of students: one child, several, or the whole class together. |
| Receptionist | The front-desk staff member handling the call or visit. |
| Caller | The person the receptionist is serving, on the phone or at the desk: a parent, visitor, supplier, job applicant. Also a student or teacher if they are the one being served. |
| Other | Anyone else who speaks in the conversation: another staff member, a parent who walks into a class, a school announcement, the recorded "this call may be recorded" notice, hold messages and other automated voices. |
| Silence | Nobody in the conversation is speaking for 2 seconds or more (section 9). |

Teaching recordings normally use Teacher, Student(s), Other and Silence. Reception recordings normally
use Receptionist, Caller, Other and Silence. If you truly can't tell who is speaking, use **Other**.

## 3. Write exactly what was said

- Write every word in the order it was said. Don't correct grammar, finish sentences, summarise or
  translate.
- Keep repetitions and false starts: `the the answer is`, `we will we are going to`.
- A word cut off halfway: write the part you heard and a hyphen: `photosyn-`. The hyphen is used only
  for this.
- Write the word the speaker meant in its normal spelling, not a spelling of their accent: if someone
  says "vater" for water, write `water`. If they said a different word, write that word.
- Contractions as said: `don't`, `I'm`, `gonna` if they said "gonna".
- Punctuation and capital letters are optional and are not checked. Use only `.` `,` `?` (or `।`)
  if you want them. Never use quotation marks, and never use square brackets except for the tokens in
  sections 6 and 7.
- English spelling: Indian/British (`colour`, `centre`). Hindi spelling: the normal dictionary
  spelling. Don't spend time on fine points such as nukta (ज़ or ज) or chandrabindu (ँ or ं): write it
  the way you normally would, and the same way every time.
- Write only speech. No descriptions or notes in the text (no "laughs", no "the boy at the back").

### Fillers

Always write fillers. Use these spellings so everyone writes them the same way:

| You hear | Type |
| --- | --- |
| um, umm, ummm | `umm` |
| uh, er | `uh` |
| hmm, mm, mm-hmm | `hmm` |
| haan, haa | `हाँ` |
| accha, achha | `अच्छा` |
| matlab | `मतलब` |
| arre | `अरे` |
| na, naa (at the end of a sentence) | `ना` |
| ji | `जी` |
| ok, okay | `okay` |

## 4. Hindi, English and Hinglish: which script

**The script follows the language of each word.**

- Hindi words in **Devanagari**. English words in **Roman** (English letters). Mix them inside one
  sentence exactly as the speaker did:
  - Right: `आज हम photosynthesis पढ़ेंगे`
  - Wrong: `aaj hum photosynthesis padhenge` (Hindi in Roman)
  - Wrong: `आज हम फोटोसिंथेसिस पढ़ेंगे` (English in Devanagari)
- English words used every day in Hindi speech are still English: `class`, `homework`, `fees`,
  `admission`, `test`, `copy`, `sir`, `ma'am`, `bus`, `sorry`, `please`, `thank you`, `okay`.
- Hindi grammar around an English word stays Devanagari: `copies में लिखो`, `homework करो`.
- Hindi words inside English speech stay Devanagari: `very good, शाबाश`.
- **Proper names** of people, places, schools, books and organisations are always in Roman, as they
  would be written in English: `Pooja`, `Jaipur`, `Sunrise Public School`, `NCERT`. (Most personal
  names are replaced by tokens anyway, section 6.)
- Abbreviations said letter by letter are written in capitals: `NCERT`, `PTM`, `CBSE`, `UPI`.
- Words from Rajasthani or another language written in Devanagari: Devanagari. A whole turn in a
  language you can't write: label the speaker, write `[inaudible]`, and tell the lead.
- A word that could belong to either language: use the language of the words around it.

## 5. Numbers

- Write numbers **as words, exactly as spoken, in the language spoken**. Never digits.
  - `twenty five`, `पच्चीस`, `class ten`, `page number पच्चीस`, `two thousand twenty six`,
    `ten thirty`, `five hundred rupees`, `पाँच सौ रुपये`, `one by two`, `x square plus two x`.
- No hyphens in numbers: `twenty five`, not `twenty-five`.
- Numbers said digit by digit are written digit by digit: `four five two`.
- Private numbers (phone, Aadhaar, admission number and similar) are replaced by a token, section 6.

## 6. Private details: tokens

Replace private details with these exact tokens: lowercase, in square brackets, nothing else inside.
One token replaces the whole name or number. Keep words around it, such as honorifics: `[name] जी`,
`[student] की mother`, `[student]'s copy`.

| Token | Replaces |
| --- | --- |
| `[student]` | Any student's name or nickname, first name or surname, whoever says it. |
| `[name]` | The name of any private person who is not school staff: parents, callers, visitors, relatives, other children. |
| `[phone]` | Phone numbers. |
| `[id]` | Aadhaar, PAN, admission, roll, registration, receipt and bank account numbers, and similar. |
| `[email]` | Email addresses. |
| `[address]` | Home addresses: house or flat number, street, locality. |

- **Never write a student's name.** If you are not sure whether a name belongs to a student, use
  `[student]`.
- **Staff names are kept** as spoken: teachers, front-desk staff, the principal, other staff
  (`Sharma ma'am`, `Pooja`). Feedback is about staff, so their names are part of the conversation. If
  you are not sure whether someone is staff, use `[name]`.
- Class and section (`class eight B`), subjects, and the school's name are not private: keep them.

## 7. Unclear speech: `[inaudible]`

- If you can't make out a word, listen again up to two more times, slowed down. If you still can't
  make it out, write `[inaudible]`. One `[inaudible]` covers one word or several in a row.
- Don't guess. If you are fairly sure of a word, write it.
- A whole region you can't make out: give it the right speaker label and the text `[inaudible]`.
- `[inaudible]` is the only marker for unclear speech. Don't use `???`, `(unclear)` or similar.

## 8. Overlapping speech

- When two people speak at once, give each person their own region. The regions overlap in time, and
  each region contains only that person's words.
- The whole class answering together is one Student(s) region. Write what the group said if it is clear
  (`yes ma'am`), otherwise `[inaudible]`.
- Short reactions during someone else's turn (`हाँ`, `hmm`, `okay`) get their own region when you can
  hear them clearly as words. Ignore murmur you can't make out.
- Voices that are not part of the conversation (a corridor, the next classroom, a TV) are not
  transcribed.

## 9. Silence

- Mark **Silence** for any stretch of **2 seconds or more** in which nobody in the conversation speaks:
  students writing, waiting for an answer, a caller on hold. Leave its text empty.
- Shorter pauses need no region.
- Sounds without speech (bell, fan, traffic, hold music) and background chatter that isn't part of the
  conversation count as silence.
- Silence regions should not overlap speech regions.

## 10. Before you submit

- Play the recording through once more and check every region: right label, right edges, and text for
  every region except Silence.
- Then **Submit**. To correct a task later, open your existing annotation, fix it and click **Update**.
  Don't create a second annotation.
- Exported tasks are checked automatically. A task comes back to you if a speech region has no text, a
  Silence region has text, or a region has no label.

## Worked examples

All names, schools and numbers in these examples are made up. Times are minutes:seconds.

### Example 1: Hinglish lesson, a student is named, speakers overlap

What you hear: the teacher says "Accha, so aaj hum photosynthesis padhenge. Umm, kaun batayega plants
khaana kaise banate hain?" A boy answers "Sunlight se, ma'am." Before he finishes, the teacher says
"Haan, bilkul. Aarav, tum batao chlorophyll kya karta hai?"

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.5 | 0:06.0 | Teacher | `अच्छा, so आज हम photosynthesis पढ़ेंगे. umm, कौन बताएगा plants खाना कैसे बनाते हैं?` |
| 0:06.8 | 0:08.3 | Student(s) | `sunlight से ma'am` |
| 0:08.0 | 0:12.3 | Teacher | `हाँ, बिल्कुल. [student], तुम बताओ chlorophyll क्या करता है?` |

Why: Hindi words in Devanagari, English words in Roman; fillers spelled as in the table; the student's
name becomes `[student]`; the overlapping turns are separate regions.

### Example 2: English lesson, quiet writing time, the class answers together

What you hear: "Write the answer in your copies. You have one minute." About nine seconds of pens on
paper. "Done? Okay, so what is the answer?" The class together: "Twenty five, ma'am!" Then one student
at the back mumbles something you can't catch, followed by "I got twenty four."

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.0 | 0:04.1 | Teacher | `write the answer in your copies. you have one minute` |
| 0:04.1 | 0:13.0 | Silence | (empty) |
| 0:13.0 | 0:16.2 | Teacher | `done? okay, so what is the answer?` |
| 0:16.4 | 0:18.0 | Student(s) | `twenty five ma'am` |
| 0:18.3 | 0:21.0 | Student(s) | `[inaudible] I got twenty four` |

Why: numbers in words; the whole class is one Student(s) region; the pause of 2 seconds or more is
Silence with empty text; the unclear words are `[inaudible]`, not a guess.

### Example 3: Reception phone call in Hinglish with private details

What you hear: a recorded voice: "This call may be recorded for training and quality purposes." The
receptionist: "Good morning, Sunrise Public School, Pooja bol rahi hoon." The caller: "Haan ji, main
Rakesh Verma bol raha hoon, meri beti Ananya ke admission ke baare mein." The receptionist: "Ji sir,
aapka number bata dijiye, main callback karwa deti hoon." The caller reads out a mobile number.

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.0 | 0:03.5 | Other | `this call may be recorded for training and quality purposes` |
| 0:03.6 | 0:06.2 | Receptionist | `good morning, Sunrise Public School, Pooja बोल रही हूँ` |
| 0:06.4 | 0:11.0 | Caller | `हाँ जी, मैं [name] बोल रहा हूँ, मेरी बेटी [student] के admission के बारे में` |
| 0:11.2 | 0:14.5 | Receptionist | `जी sir, आपका number बता दीजिए, मैं callback करवा देती हूँ` |
| 0:14.7 | 0:19.0 | Caller | `[phone]` |

Why: the recorded notice is Other; the receptionist's own name is kept (staff) and written in Roman
(proper name); the caller's name is `[name]` and his daughter's is `[student]`; the phone number is one
`[phone]` token.

### Example 4: Walk-in enquiry at the front desk, a colleague interrupts

What you hear: a parent at the desk: "Hello, I wanted to ask about the fee for class three." The
receptionist: "Sure. For class three it's twelve thousand five hundred per quarter." A colleague
walks up: "Pooja, principal sir wants the visitor register." The receptionist, to the colleague: "One
minute, sir." Then to the parent: "Sorry, umm, you were saying?" The parent starts asking "Can I pay by
UPI?" while the receptionist is still finishing her sentence.

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.0 | 0:03.0 | Caller | `hello, I wanted to ask about the fee for class three` |
| 0:03.2 | 0:07.4 | Receptionist | `sure. for class three it's twelve thousand five hundred per quarter` |
| 0:07.9 | 0:10.6 | Other | `Pooja, principal sir wants the visitor register` |
| 0:10.8 | 0:11.7 | Receptionist | `one minute, sir` |
| 0:12.0 | 0:14.2 | Receptionist | `sorry, umm, you were saying?` |
| 0:13.8 | 0:15.6 | Caller | `can I pay by UPI?` |

Why: the colleague is Other even though he is staff, because he is not the receptionist being recorded
or the person being served; amounts in words; `UPI` in capitals because it is said letter by letter;
the overlapping question is its own region.

### Example 5: Hindi lesson with an announcement, students named, a bell

What you hear: the speaker system: "Attention please, all class ten students report to the hall after
the break." The teacher: "Chalo, sab dhyaan do. Riya, kitaab band karo." A girl: "Ma'am, Mohit ne mera
pen le liya." The teacher: "Mohit, pen wapas karo." Then the bell rings and nobody speaks for about
four seconds.

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.0 | 0:05.2 | Other | `attention please, all class ten students report to the hall after the break` |
| 0:05.8 | 0:09.0 | Teacher | `चलो, सब ध्यान दो. [student], किताब बंद करो` |
| 0:09.4 | 0:12.0 | Student(s) | `ma'am, [student] ने मेरा pen ले लिया` |
| 0:12.2 | 0:14.0 | Teacher | `[student], pen वापस करो` |
| 0:14.0 | 0:18.1 | Silence | (empty) |

Why: the announcement is Other; every student's name is `[student]`, whoever says it; `ma'am` and
`pen` are English words in Roman; the bell with no speech is Silence.
