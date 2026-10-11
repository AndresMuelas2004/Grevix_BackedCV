# Fabrication set: live run, 2026-10-11 02:46

Guards, then the app's real verifier on the suggestions the guards let through, one call per CV section. A failed verifier call leaves its suggestions `not checked`.

## dev (20 cases)

### Fabricated (10)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 4 | C02, C06, C08, C16 |
| caught by verifier | 5 | C10, C12, C14, C18, C20 |
| missed | 1 | C09 |
| not checked | 0 | - |

### Faithful (10)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 1 | C13 |
| passed | 9 | C01, C03, C04, C05, C07, C11, C15, C17, C19 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

- C13: The CV does not identify this project as an LLM agent.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 2 | 2 | 0 | 0 | 0 |
| invented_certification_or_degree | 1 | 0 | 1 | 0 | 0 |
| invented_employer_or_title | 1 | 0 | 1 | 0 | 0 |
| invented_number | 1 | 1 | 0 | 0 | 0 |
| invented_tool | 2 | 0 | 2 | 0 | 0 |
| posting_entity_copied | 1 | 1 | 0 | 0 | 0 |
| scope_inflation | 2 | 0 | 1 | 1 | 0 |

## heldout (20 cases)

### Fabricated (10)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 2 | C22, C24 |
| caught by verifier | 8 | C26, C28, C30, C32, C34, C36, C38, C40 |
| missed | 0 | - |
| not checked | 0 | - |

### Faithful (10)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 1 | C29 |
| passed | 9 | C21, C23, C25, C27, C31, C33, C35, C37, C39 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

- C29: The CV says she presented to one operations lead, not multiple operations leads.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 1 | 1 | 0 | 0 | 0 |
| invented_certification_or_degree | 1 | 0 | 1 | 0 | 0 |
| invented_employer_or_title | 1 | 0 | 1 | 0 | 0 |
| invented_number | 1 | 1 | 0 | 0 | 0 |
| invented_tool | 1 | 0 | 1 | 0 | 0 |
| posting_entity_copied | 1 | 0 | 1 | 0 | 0 |
| scope_inflation | 2 | 0 | 2 | 0 | 0 |
| unsupported_soft_claim | 2 | 0 | 2 | 0 | 0 |

## all (40 cases)

### Fabricated (20)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 6 | C02, C06, C08, C16, C22, C24 |
| caught by verifier | 13 | C10, C12, C14, C18, C20, C26, C28, C30, C32, C34, C36, C38, C40 |
| missed | 1 | C09 |
| not checked | 0 | - |

### Faithful (20)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 2 | C13, C29 |
| passed | 18 | C01, C03, C04, C05, C07, C11, C15, C17, C19, C21, C23, C25, C27, C31, C33, C35, C37, C39 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

- C13: The CV does not identify this project as an LLM agent.
- C29: The CV says she presented to one operations lead, not multiple operations leads.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 3 | 3 | 0 | 0 | 0 |
| invented_certification_or_degree | 2 | 0 | 2 | 0 | 0 |
| invented_employer_or_title | 2 | 0 | 2 | 0 | 0 |
| invented_number | 2 | 2 | 0 | 0 | 0 |
| invented_tool | 3 | 0 | 3 | 0 | 0 |
| posting_entity_copied | 2 | 1 | 1 | 0 | 0 |
| scope_inflation | 4 | 0 | 3 | 1 | 0 |
| unsupported_soft_claim | 2 | 0 | 2 | 0 | 0 |

## Verifier cost

| Calls | Input tokens | Output tokens | Cost (USD) | Failed calls |
|---:|---:|---:|---:|---:|
| 10 | 17452 | 7000 | 0.0052 | 0 |

## All cases

| Case | Split | Expected | Fabrication type | Outcome | Reason |
|---|---|---|---|---|---|
| C01 | dev | verified | - | passed | - |
| C02 | dev | unsupported | invented_number | caught by guards | numbers_backed: not in the cited lines or the original: 12 |
| C03 | dev | verified | - | passed | - |
| C04 | dev | verified | - | passed | - |
| C05 | dev | verified | - | passed | - |
| C06 | dev | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 3 |
| C07 | dev | verified | - | passed | - |
| C08 | dev | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 30 |
| C09 | dev | unsupported | scope_inflation | missed | - |
| C10 | dev | unsupported | invented_tool | caught by verifier | The CV does not show Kubernetes experience. |
| C11 | dev | verified | - | passed | - |
| C12 | dev | unsupported | invented_tool | caught by verifier | The CV does not show LangSmith use or end-to-end tracing. |
| C13 | dev | verified | - | wrongly blocked by verifier | The CV does not identify this project as an LLM agent. |
| C14 | dev | unsupported | invented_employer_or_title | caught by verifier | The CV gives no seniority level for this role. |
| C15 | dev | verified | - | passed | - |
| C16 | dev | unsupported | posting_entity_copied | caught by guards | no_posting_entities: names the posting's company 'Vantarix Labs' outside the CV entries |
| C17 | dev | verified | - | passed | - |
| C18 | dev | unsupported | invented_certification_or_degree | caught by verifier | The CV lists a BSc, not a master's degree or MSc. |
| C19 | dev | verified | - | passed | - |
| C20 | dev | unsupported | scope_inflation | caught by verifier | The CV says the candidate helped maintain the app, but does not show that they led its maintenance. |
| C21 | heldout | verified | - | passed | - |
| C22 | heldout | unsupported | invented_number | caught by guards | numbers_backed: not in the cited lines or the original: 12 |
| C23 | heldout | verified | - | passed | - |
| C24 | heldout | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 8 |
| C25 | heldout | verified | - | passed | - |
| C26 | heldout | unsupported | invented_tool | caught by verifier | The CV does not show experience with Airflow. |
| C27 | heldout | verified | - | passed | - |
| C28 | heldout | unsupported | invented_employer_or_title | caught by verifier | The CV names Torvane Logistics as the employer, not Halvard Robotics. |
| C29 | heldout | verified | - | wrongly blocked by verifier | The CV says she presented to one operations lead, not multiple operations leads. |
| C30 | heldout | unsupported | scope_inflation | caught by verifier | The CV says the candidate cleaned and joined the data, but does not say they designed this work. |
| C31 | heldout | verified | - | passed | - |
| C32 | heldout | unsupported | scope_inflation | caught by verifier | The CV does not say the candidate led the team. |
| C33 | heldout | verified | - | passed | - |
| C34 | heldout | unsupported | invented_certification_or_degree | caught by verifier | The CV does not show AWS certification or this credential. |
| C35 | heldout | verified | - | passed | - |
| C36 | heldout | unsupported | posting_entity_copied | caught by verifier | The CV describes LLM-powered tools in a project but does not show an LLM Application Engineer role or title. |
| C37 | heldout | verified | - | passed | - |
| C38 | heldout | unsupported | unsupported_soft_claim | caught by verifier | The CV does not describe leadership ability or establish that she is known for it. |
| C39 | heldout | verified | - | passed | - |
| C40 | heldout | unsupported | unsupported_soft_claim | caught by verifier | The CV does not describe team leadership or confidence as a leader. |
