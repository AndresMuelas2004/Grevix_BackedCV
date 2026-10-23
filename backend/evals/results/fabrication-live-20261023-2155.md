# Fabrication set: live run, 2026-10-23 21:55

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

- C19: The CV lists the checks and the 25% cut side by side but does not say the checks caused the cut.

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
| wrongly blocked by verifier | 2 | C29, C35 |
| passed | 8 | C21, C23, C25, C27, C31, C33, C37, C39 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

- C29: The CV mentions one operations lead, not several.
- C35: The CV does not name LangGraph; it only says the assistant is an agent.

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
| wrongly blocked by verifier | 3 | C19, C29, C35 |
| passed | 17 | C01, C03, C04, C05, C07, C11, C13, C15, C17, C21, C23, C25, C27, C31, C33, C37, C39 |
| not checked | 0 | - |

### Faithful cases wrongly blocked

- C19: The CV lists the checks and the 25% cut side by side but does not say the checks caused the cut.
- C29: The CV mentions one operations lead, not several.
- C35: The CV does not name LangGraph; it only says the assistant is an agent.

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
| 10 | 36416 | 13441 | 0.0104 | 0 |

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
| C10 | dev | unsupported | invented_tool | caught by verifier | The CV does not mention Kubernetes; it only says services were containerized with Docker. |
| C11 | dev | verified | - | passed | - |
| C12 | dev | unsupported | invented_tool | caught by verifier | The CV does not say the assistant is traced or monitored with any tool. |
| C13 | dev | verified | - | passed | - |
| C14 | dev | unsupported | invented_employer_or_title | caught by verifier | The CV lists the title as Data Engineer and shows no senior level. |
| C15 | dev | verified | - | passed | - |
| C16 | dev | unsupported | posting_entity_copied | caught by guards | no_posting_entities: names the posting's company 'Vantarix Labs' outside the CV entries |
| C17 | dev | verified | - | passed | - |
| C18 | dev | unsupported | invented_certification_or_degree | caught by verifier | The CV shows a BSc in Computer Science, not a Master's degree. |
| C19 | dev | verified | - | wrongly blocked by verifier | The CV lists the checks and the 25% cut side by side but does not say the checks caused the cut. |
| C20 | dev | unsupported | scope_inflation | caught by verifier | The CV says the candidate helped maintain the app, not that they led its maintenance. |
| C21 | heldout | verified | - | passed | - |
| C22 | heldout | unsupported | invented_number | caught by guards | numbers_backed: not in the cited lines or the original: 12 |
| C23 | heldout | verified | - | passed | - |
| C24 | heldout | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 8 |
| C25 | heldout | verified | - | passed | - |
| C26 | heldout | unsupported | invented_tool | caught by verifier | The CV does not mention Airflow; the ETL jobs are described without naming a tool. |
| C27 | heldout | verified | - | passed | - |
| C28 | heldout | unsupported | invented_employer_or_title | caught by verifier | The CV names Torvane Logistics as this employer, not Halvard Robotics. |
| C29 | heldout | verified | - | wrongly blocked by verifier | The CV mentions one operations lead, not several. |
| C30 | heldout | unsupported | scope_inflation | caught by verifier | The CV shows cleaning the shipment data, not designing or leading that work. |
| C31 | heldout | verified | - | passed | - |
| C32 | heldout | unsupported | scope_inflation | caught by verifier | The CV does not say this person led a team; it shows the container work only. |
| C33 | heldout | verified | - | passed | - |
| C34 | heldout | unsupported | invented_certification_or_degree | caught by verifier | The CV shows no AWS certification; the only education line is a BSc in Computer Science. |
| C35 | heldout | verified | - | wrongly blocked by verifier | The CV does not name LangGraph; it only says the assistant is an agent. |
| C36 | heldout | unsupported | posting_entity_copied | caught by guards | fact_scope: A computed total (F01) covers the whole CV; it cannot be attached to one role, skill or employer. |
| C37 | heldout | verified | - | passed | - |
| C38 | heldout | unsupported | unsupported_soft_claim | caught by verifier | The CV does not show any leadership role or leadership skill. |
| C39 | heldout | verified | - | passed | - |
| C40 | heldout | unsupported | unsupported_soft_claim | caught by verifier | The CV does not show team leadership or a confident manner. |
