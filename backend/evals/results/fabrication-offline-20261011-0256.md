# Fabrication set: offline run, 2026-10-11 02:56

Guards only, no network. The verifier did not run, so a case that passes the guards is `not checked`, not `passed`.

## dev (20 cases)

### Fabricated (10)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 5 | C02, C06, C08, C09, C16 |
| caught by verifier | 0 | - |
| missed | 0 | - |
| not checked | 5 | C10, C12, C14, C18, C20 |

### Faithful (10)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 0 | - |
| passed | 0 | - |
| not checked | 10 | C01, C03, C04, C05, C07, C11, C13, C15, C17, C19 |

### Faithful cases wrongly blocked

None.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 2 | 2 | 0 | 0 | 0 |
| invented_certification_or_degree | 1 | 0 | 0 | 0 | 1 |
| invented_employer_or_title | 1 | 0 | 0 | 0 | 1 |
| invented_number | 1 | 1 | 0 | 0 | 0 |
| invented_tool | 2 | 0 | 0 | 0 | 2 |
| posting_entity_copied | 1 | 1 | 0 | 0 | 0 |
| scope_inflation | 2 | 1 | 0 | 0 | 1 |

## heldout (20 cases)

### Fabricated (10)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 3 | C22, C24, C36 |
| caught by verifier | 0 | - |
| missed | 0 | - |
| not checked | 7 | C26, C28, C30, C32, C34, C38, C40 |

### Faithful (10)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 0 | - |
| passed | 0 | - |
| not checked | 10 | C21, C23, C25, C27, C29, C31, C33, C35, C37, C39 |

### Faithful cases wrongly blocked

None.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 1 | 1 | 0 | 0 | 0 |
| invented_certification_or_degree | 1 | 0 | 0 | 0 | 1 |
| invented_employer_or_title | 1 | 0 | 0 | 0 | 1 |
| invented_number | 1 | 1 | 0 | 0 | 0 |
| invented_tool | 1 | 0 | 0 | 0 | 1 |
| posting_entity_copied | 1 | 1 | 0 | 0 | 0 |
| scope_inflation | 2 | 0 | 0 | 0 | 2 |
| unsupported_soft_claim | 2 | 0 | 0 | 0 | 2 |

## all (40 cases)

### Fabricated (20)

| Outcome | Count | Cases |
|---|---:|---|
| caught by guards | 8 | C02, C06, C08, C09, C16, C22, C24, C36 |
| caught by verifier | 0 | - |
| missed | 0 | - |
| not checked | 12 | C10, C12, C14, C18, C20, C26, C28, C30, C32, C34, C38, C40 |

### Faithful (20)

| Outcome | Count | Cases |
|---|---:|---|
| wrongly blocked by guards | 0 | - |
| wrongly blocked by verifier | 0 | - |
| passed | 0 | - |
| not checked | 20 | C01, C03, C04, C05, C07, C11, C13, C15, C17, C19, C21, C23, C25, C27, C29, C31, C33, C35, C37, C39 |

### Faithful cases wrongly blocked

None.

### By fabrication type

| Type | Cases | Caught by guards | Caught by verifier | Missed | Not checked |
|---|---:|---:|---:|---:|---:|
| inflated_number | 3 | 3 | 0 | 0 | 0 |
| invented_certification_or_degree | 2 | 0 | 0 | 0 | 2 |
| invented_employer_or_title | 2 | 0 | 0 | 0 | 2 |
| invented_number | 2 | 2 | 0 | 0 | 0 |
| invented_tool | 3 | 0 | 0 | 0 | 3 |
| posting_entity_copied | 2 | 2 | 0 | 0 | 0 |
| scope_inflation | 4 | 1 | 0 | 0 | 3 |
| unsupported_soft_claim | 2 | 0 | 0 | 0 | 2 |

## All cases

| Case | Split | Expected | Fabrication type | Outcome | Reason |
|---|---|---|---|---|---|
| C01 | dev | verified | - | not checked | verifier not run (offline) |
| C02 | dev | unsupported | invented_number | caught by guards | numbers_backed: not in the cited lines or the original: 12 |
| C03 | dev | verified | - | not checked | verifier not run (offline) |
| C04 | dev | verified | - | not checked | verifier not run (offline) |
| C05 | dev | verified | - | not checked | verifier not run (offline) |
| C06 | dev | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 3 |
| C07 | dev | verified | - | not checked | verifier not run (offline) |
| C08 | dev | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 30 |
| C09 | dev | unsupported | scope_inflation | caught by guards | fact_scope: A computed total (F01) covers the whole CV; it cannot be attached to one role, skill or employer. |
| C10 | dev | unsupported | invented_tool | not checked | verifier not run (offline) |
| C11 | dev | verified | - | not checked | verifier not run (offline) |
| C12 | dev | unsupported | invented_tool | not checked | verifier not run (offline) |
| C13 | dev | verified | - | not checked | verifier not run (offline) |
| C14 | dev | unsupported | invented_employer_or_title | not checked | verifier not run (offline) |
| C15 | dev | verified | - | not checked | verifier not run (offline) |
| C16 | dev | unsupported | posting_entity_copied | caught by guards | no_posting_entities: names the posting's company 'Vantarix Labs' outside the CV entries |
| C17 | dev | verified | - | not checked | verifier not run (offline) |
| C18 | dev | unsupported | invented_certification_or_degree | not checked | verifier not run (offline) |
| C19 | dev | verified | - | not checked | verifier not run (offline) |
| C20 | dev | unsupported | scope_inflation | not checked | verifier not run (offline) |
| C21 | heldout | verified | - | not checked | verifier not run (offline) |
| C22 | heldout | unsupported | invented_number | caught by guards | numbers_backed: not in the cited lines or the original: 12 |
| C23 | heldout | verified | - | not checked | verifier not run (offline) |
| C24 | heldout | unsupported | inflated_number | caught by guards | numbers_backed: not in the cited lines or the original: 8 |
| C25 | heldout | verified | - | not checked | verifier not run (offline) |
| C26 | heldout | unsupported | invented_tool | not checked | verifier not run (offline) |
| C27 | heldout | verified | - | not checked | verifier not run (offline) |
| C28 | heldout | unsupported | invented_employer_or_title | not checked | verifier not run (offline) |
| C29 | heldout | verified | - | not checked | verifier not run (offline) |
| C30 | heldout | unsupported | scope_inflation | not checked | verifier not run (offline) |
| C31 | heldout | verified | - | not checked | verifier not run (offline) |
| C32 | heldout | unsupported | scope_inflation | not checked | verifier not run (offline) |
| C33 | heldout | verified | - | not checked | verifier not run (offline) |
| C34 | heldout | unsupported | invented_certification_or_degree | not checked | verifier not run (offline) |
| C35 | heldout | verified | - | not checked | verifier not run (offline) |
| C36 | heldout | unsupported | posting_entity_copied | caught by guards | fact_scope: A computed total (F01) covers the whole CV; it cannot be attached to one role, skill or employer. |
| C37 | heldout | verified | - | not checked | verifier not run (offline) |
| C38 | heldout | unsupported | unsupported_soft_claim | not checked | verifier not run (offline) |
| C39 | heldout | verified | - | not checked | verifier not run (offline) |
| C40 | heldout | unsupported | unsupported_soft_claim | not checked | verifier not run (offline) |
