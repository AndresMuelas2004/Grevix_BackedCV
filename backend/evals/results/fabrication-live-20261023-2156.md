# Fabrication set: live run, 2026-10-23 21:56

Guards, then the app's real verifier on the suggestions the guards let through, one call per CV section. A failed verifier call leaves its suggestions `not checked`.

## dev (20 cases)

### Fabricated (10)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 5 | C02, C06, C08, C09, C16 |
| caught by verifier | 5 | C10, C12, C14, C18, C20 |
| missed | 0 | - |
| not checked | 0 | - |

### Faithful (10)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 1 | C19 |
| passed | 9 | C01, C03, C04, C05, C07, C11, C13, C15, C17 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

- C19: The CV does not say the data checks caused the 25% cut; it lists them separately.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 2 | 2 | 0 | 0 | 0 |
| invented_certification_or_degree | 1 | 0 | 1 | 0 | 0 |
| invented_employer_or_title | 1 | 0 | 1 | 0 | 0 |
| invented_number | 1 | 1 | 0 | 0 | 0 |
| invented_tool | 2 | 0 | 2 | 0 | 0 |
| posting_entity_copied | 1 | 1 | 0 | 0 | 0 |
| scope_inflation | 2 | 1 | 1 | 0 | 0 |

## heldout (20 cases)

### Fabricated (10)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 3 | C22, C24, C36 |
| caught by verifier | 7 | C26, C28, C30, C32, C34, C38, C40 |
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

- C29: The CV names the OpenAI API for one project only, not for the tools in general.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 1 | 1 | 0 | 0 | 0 |
| invented_certification_or_degree | 1 | 0 | 1 | 0 | 0 |
| invented_employer_or_title | 1 | 0 | 1 | 0 | 0 |
| invented_number | 1 | 1 | 0 | 0 | 0 |
| invented_tool | 1 | 0 | 1 | 0 | 0 |
| posting_entity_copied | 1 | 1 | 0 | 0 | 0 |
| scope_inflation | 2 | 0 | 2 | 0 | 0 |
| unsupported_soft_claim | 2 | 0 | 2 | 0 | 0 |

## all (40 cases)

### Fabricated (20)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 8 | C02, C06, C08, C09, C16, C22, C24, C36 |
| caught by verifier | 12 | C10, C12, C14, C18, C20, C26, C28, C30, C32, C34, C38, C40 |
| missed | 0 | - |
| not checked | 0 | - |

### Faithful (20)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 2 | C19, C29 |
| passed | 18 | C01, C03, C04, C05, C07, C11, C13, C15, C17, C21, C23, C25, C27, C31, C33, C35, C37, C39 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

- C19: The CV does not say the data checks caused the 25% cut; it lists them separately.
- C29: The CV names the OpenAI API for one project only, not for the tools in general.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 3 | 3 | 0 | 0 | 0 |
| invented_certification_or_degree | 2 | 0 | 2 | 0 | 0 |
| invented_employer_or_title | 2 | 0 | 2 | 0 | 0 |
| invented_number | 2 | 2 | 0 | 0 | 0 |
| invented_tool | 3 | 0 | 3 | 0 | 0 |
| posting_entity_copied | 2 | 2 | 0 | 0 | 0 |
| scope_inflation | 4 | 1 | 3 | 0 | 0 |
| unsupported_soft_claim | 2 | 0 | 2 | 0 | 0 |

## Verifier cost

| Calls | Input tokens | Output tokens | Cost (USD) | Failed calls |
|---:|---:|---:|---:|---:|
| 10 | 36416 | 22228 | 0.0148 | 0 |

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
| C09 | dev | unsupported | scope_inflation | caught by guards | fact_scope: A computed total (F01) covers the whole CV; it cannot be attached to one role, skill or employer. |
| C10 | dev | unsupported | invented_tool | caught by verifier | The CV mentions Docker for containers, but does not mention Kubernetes anywhere. |
| C11 | dev | verified | - | passed | - |
| C12 | dev | unsupported | invented_tool | caught by verifier | The CV does not say the agent is traced or that LangSmith is used. |
| C13 | dev | verified | - | passed | - |
| C14 | dev | unsupported | invented_employer_or_title | caught by verifier | The CV shows the title Data Engineer, not Senior. |
| C15 | dev | verified | - | passed | - |
| C16 | dev | unsupported | posting_entity_copied | caught by guards | no_posting_entities: names the posting's company 'Vantarix Labs' outside the CV entries |
| C17 | dev | verified | - | passed | - |
| C18 | dev | unsupported | invented_certification_or_degree | caught by verifier | The CV shows a BSc in Computer Science, not a Master's degree. |
| C19 | dev | verified | - | wrongly blocked by verifier | The CV does not say the data checks caused the 25% cut; it lists them separately. |
| C20 | dev | unsupported | scope_inflation | caught by verifier | The CV shows helping with maintenance of the app, not leading it. |
| C21 | heldout | verified | - | passed | - |
| C22 | heldout | unsupported | invented_number | caught by guards | numbers_backed: not in the cited lines or the original: 12 |
| C23 | heldout | verified | - | passed | - |
| C24 | heldout | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 8 |
| C25 | heldout | verified | - | passed | - |
| C26 | heldout | unsupported | invented_tool | caught by verifier | The CV does not mention Airflow; the ETL jobs are described only as Python jobs. |
| C27 | heldout | verified | - | passed | - |
| C28 | heldout | unsupported | invented_employer_or_title | caught by verifier | The CV lists this role at Torvane Logistics, not Halvard Robotics. |
| C29 | heldout | verified | - | wrongly blocked by verifier | The CV names the OpenAI API for one project only, not for the tools in general. |
| C30 | heldout | unsupported | scope_inflation | caught by verifier | The CV shows the candidate cleaned the data, not that they designed or led the work. |
| C31 | heldout | verified | - | passed | - |
| C32 | heldout | unsupported | scope_inflation | caught by verifier | The CV does not say the candidate led a team on this work. |
| C33 | heldout | verified | - | passed | - |
| C34 | heldout | unsupported | invented_certification_or_degree | caught by verifier | The CV lists no AWS certification; only a computer science degree is shown. |
| C35 | heldout | verified | - | passed | - |
| C36 | heldout | unsupported | posting_entity_copied | caught by guards | fact_scope: A computed total (F01) covers the whole CV; it cannot be attached to one role, skill or employer. |
| C37 | heldout | verified | - | passed | - |
| C38 | heldout | unsupported | unsupported_soft_claim | caught by verifier | The 3.2 years is total experience across all roles, not time as a data engineer. |
| C39 | heldout | verified | - | passed | - |
| C40 | heldout | unsupported | unsupported_soft_claim | caught by verifier | The CV does not show the candidate leading a team. |
