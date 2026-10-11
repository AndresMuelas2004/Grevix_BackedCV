# Fabrication set: live run, 2026-10-11 02:45

Guards, then the app's real verifier on the suggestions the guards let through, one call per CV section. A failed verifier call leaves its suggestions `not checked`.

## dev (20 cases)

### Fabricated (10)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 4 | C02, C06, C08, C16 |
| caught by verifier | 6 | C09, C10, C12, C14, C18, C20 |
| missed | 0 | - |
| not checked | 0 | - |

### Faithful (10)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 0 | - |
| passed | 10 | C01, C03, C04, C05, C07, C11, C13, C15, C17, C19 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

None.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 2 | 2 | 0 | 0 | 0 |
| invented_certification_or_degree | 1 | 0 | 1 | 0 | 0 |
| invented_employer_or_title | 1 | 0 | 1 | 0 | 0 |
| invented_number | 1 | 1 | 0 | 0 | 0 |
| invented_tool | 2 | 0 | 2 | 0 | 0 |
| posting_entity_copied | 1 | 1 | 0 | 0 | 0 |
| scope_inflation | 2 | 0 | 2 | 0 | 0 |

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

- C29: The CV names one operations lead, not multiple operations leads.

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
| caught by verifier | 14 | C09, C10, C12, C14, C18, C20, C26, C28, C30, C32, C34, C36, C38, C40 |
| missed | 0 | - |
| not checked | 0 | - |

### Faithful (20)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 1 | C29 |
| passed | 19 | C01, C03, C04, C05, C07, C11, C13, C15, C17, C19, C21, C23, C25, C27, C31, C33, C35, C37, C39 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

- C29: The CV names one operations lead, not multiple operations leads.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 3 | 3 | 0 | 0 | 0 |
| invented_certification_or_degree | 2 | 0 | 2 | 0 | 0 |
| invented_employer_or_title | 2 | 0 | 2 | 0 | 0 |
| invented_number | 2 | 2 | 0 | 0 | 0 |
| invented_tool | 3 | 0 | 3 | 0 | 0 |
| posting_entity_copied | 2 | 1 | 1 | 0 | 0 |
| scope_inflation | 4 | 0 | 4 | 0 | 0 |
| unsupported_soft_claim | 2 | 0 | 2 | 0 | 0 |

## Verifier cost

| Calls | Input tokens | Output tokens | Cost (USD) | Failed calls |
|---:|---:|---:|---:|---:|
| 10 | 17452 | 5833 | 0.0047 | 0 |

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
| C09 | dev | unsupported | scope_inflation | caught by verifier | The CV shows 3.2 years of total professional experience, but not 3.2 years building these pipelines. |
| C10 | dev | unsupported | invented_tool | caught by verifier | The CV does not show Kubernetes experience. |
| C11 | dev | verified | - | passed | - |
| C12 | dev | unsupported | invented_tool | caught by verifier | The CV does not show LangSmith use or end-to-end tracing. |
| C13 | dev | verified | - | passed | - |
| C14 | dev | unsupported | invented_employer_or_title | caught by verifier | The CV identifies the candidate as a data engineer but does not show a senior title or level. |
| C15 | dev | verified | - | passed | - |
| C16 | dev | unsupported | posting_entity_copied | caught by guards | no_posting_entities: names the posting's company 'Vantarix Labs' outside the CV entries |
| C17 | dev | verified | - | passed | - |
| C18 | dev | unsupported | invented_certification_or_degree | caught by verifier | The CV lists a BSc, not a master's degree. |
| C19 | dev | verified | - | passed | - |
| C20 | dev | unsupported | scope_inflation | caught by verifier | The CV says the candidate helped maintain the app, not that they led its maintenance. |
| C21 | heldout | verified | - | passed | - |
| C22 | heldout | unsupported | invented_number | caught by guards | numbers_backed: not in the cited lines or the original: 12 |
| C23 | heldout | verified | - | passed | - |
| C24 | heldout | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 8 |
| C25 | heldout | verified | - | passed | - |
| C26 | heldout | unsupported | invented_tool | caught by verifier | The CV does not show experience with Airflow. |
| C27 | heldout | verified | - | passed | - |
| C28 | heldout | unsupported | invented_employer_or_title | caught by verifier | The CV names Torvane Logistics as the employer, not Halvard Robotics. |
| C29 | heldout | verified | - | wrongly blocked by verifier | The CV names one operations lead, not multiple operations leads. |
| C30 | heldout | unsupported | scope_inflation | caught by verifier | The CV does not say the candidate designed or led this work. |
| C31 | heldout | verified | - | passed | - |
| C32 | heldout | unsupported | scope_inflation | caught by verifier | The CV does not say the candidate led a team. |
| C33 | heldout | verified | - | passed | - |
| C34 | heldout | unsupported | invented_certification_or_degree | caught by verifier | The CV does not show AWS experience. |
| C35 | heldout | verified | - | passed | - |
| C36 | heldout | unsupported | posting_entity_copied | caught by verifier | The CV does not show an LLM Application Engineer role or title. |
| C37 | heldout | verified | - | passed | - |
| C38 | heldout | unsupported | unsupported_soft_claim | caught by verifier | The CV does not describe leadership strength or recognition. |
| C39 | heldout | verified | - | passed | - |
| C40 | heldout | unsupported | unsupported_soft_claim | caught by verifier | The CV does not show team leadership or confidence as a leader. |
