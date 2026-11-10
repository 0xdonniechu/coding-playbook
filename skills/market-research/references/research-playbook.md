# Market research playbook

Open this file for deep research. Pick the sections that fit the question; don't turn the checklist into an end in itself.

## 1. Question and scope

Before searching, write down:

> I need to know **[what]** about **[segment/market/audience]** in order to decide **[action]**.

State the cutoff date, geography, ICP, channels, language, customer type, currency, time horizon, and evidence limits. If the user asks about one competitor, don't expand it into a market census on your own; if they ask about the whole market, don't stop at a list of prominent vendors.

## 2. Sources and reliability

| Evidence type | Examples | How to use |
|---|---|---|
| Primary record/data | government agencies, filings, pricing/help centers, investor/company releases, original APIs | Confirm only the exact data field or claim the page states. A filing confirms the issuer submitted a statement; it does not itself confirm the statement is true. |
| Secondary | press, analyst/database, investor portfolios, review platforms | Note author, methodology/date, and interests that may shape it. Trace to the origin where available. |
| Vendor claim | homepage, sales copy, founder quotes, product demos | Tag `[VENDOR-CLAIMED]`; don't call it an independent result. |
| Derived / scenario | calculations from cited inputs, sizing models | Print the formula, input labels, assumptions, and range; tag `[INFERENCE]` or `[ASSUMPTION]`. |

Prefer release dates and "last updated" over access date alone. When sources conflict, present both versions and explain why you picked/didn't pick each; don't silently take the number that suits the thesis.
GitHub-specific facts such as stars, license, default branch and last push belong to the GitHub API/repository itself, not a blog post or copied profile.
Note the source's interests, selection/survivorship bias, and the chance that many articles merely copy the same origin. Actively seek counter-evidence and alternative explanations; many articles repeating one claim does not make multiple independent confirmations.

## 3. Controlled parallelization

Use at most 2–3 independent streams when the task is broad and delegation tooling is available:

1. Competitor/product/pricing: origins and packaging.
2. Customer evidence: reviews, forums, community; both positive and negative.
3. Market/funding/finance: market definition, official data, rounds/funding/traction.

Each brief must carry the same question, scope, cutoff date, the return template, and the evidence contract: original URL, access date, labels, calculations/definitions, disagreements, and unknowns. Don't ask agents to guess from summaries. The synthesizer re-opens at least one important claim per stream, or every claim that could flip the conclusion. Without delegation, run the streams sequentially and state the limitation.

## 4. Competitor research

Build a longlist from varied queries and directories, then classify:

- **Direct:** same buyer/job and replaces most of the workflow.
- **Adjacent:** overlaps part of the workflow or buyer.
- **Substitute:** services, self-built agents, agencies, spreadsheets, or manual processes.

State the shortlist inclusion rule and which groups are still missing. Cross-check pricing pages, product docs, integrations, permissions, and limits. Record billing cycle, account/channel/brand/user counts, credits/tokens, usage limits, media spend, spend-based fees, onboarding, and add-ons. Don't convert tokens/credits into equivalent units without knowing the burn rate.

A capability matrix encodes only described evidence: `C` clear, `P` partial/conditional/human- or third-party-dependent, `?` no sufficient evidence found. Cite sources per row or column. Don't treat a competitor's feature list as the final verdict.

Battlecard only when needed for sales/positioning:

| Item | Evidence required |
|---|---|
| Persona and pitch | Sourced persona, promise labeled as vendor claim |
| Price/package | cycle, limits, incidentals, setup |
| Claims and experience | claims cross-checked against docs/reviews/tests; reviews are not facts |
| Risk/weakness | multi-evidence patterns, samples and counter-evidence; unknown is not a flaw |
| Wedge to test | verifiable difference, don't call it a "kill shot" yet |
| Objection response | answer precisely with evidenced features, don't belittle competitors |

## 5. Customer/review evidence

When fitting reviews exist, take both 1★/2★ and 4★/5★. Record platform, rating, total sample, review period, date, and invitation/verification markers where present. Reviews are self-selected reports; don't assert causes, policies, or verified bugs. Quote briefly, prefer paraphrase with direct links. Distinguish reviews of the specific product from the whole suite/agency/support.

## 6. TAM / SAM / SOM

Use when deciding market entry, pricing, build-for-sale, or when the user requests sizing. A proxy model may be presented instead of declaring "the market is worth":

```text
TAM = accounts with demand per definition × fitting annual spend/revenue
SAM = TAM accounts × share matching ICP/geography/channel/language/servability
SOM = SAM accounts × reachable/convertible share within the time horizon
```

Separate count from value. Source the customer count and annual price/spend; don't mix advertiser counts with business counts, ad budgets with software, or survey shares with whole populations when definitions don't match. SAM/SOM percentages must be `[ASSUMPTION]` or measured from pipeline/capacity; give low/base/high scenarios and sensitivity. Sanity-check bottom-up with sales capacity, conversion, ACV, and sales cycle. When denominators/material inputs are missing, leave range/unknown and say what data is needed; don't fill numbers to complete the table.

## 7. Funding, revenue, valuation

Use a table with entity, currency, amount, round/filing/status, date, source class, valuation status, and caveat. Separate funding amount from valuation; a funding round does not disclose valuation unless the source says so. Separate market cap (public shares × price at timestamp), private-round valuation, asking price, modeled EV, revenue, ARR/MRR, GMV, and total funding. Don't assign same-named legal entities to the same product without proof.

For TrustMRR or payment-connected services: record the exact page metric, `data updated` timestamp, access date, active subscription definition, and connection/staleness status. State clearly that this is connected-account data, may change, and does not automatically represent consolidated/audited revenue or profit.

Don't infer private-company valuation from ARR/MRR multiples unless the user requests a scenario; if you do, call it a sensitivity model, state the multiple is an assumption, and don't call it an observed valuation.

## 8. Investor / fund diligence

Depending on the question, record fund size, vintage, stage, typical check, geography, thesis, relevant portfolio, recent activity, source date, and fit/mismatch. Verify facts via fund/company/filing; database profiles are secondary. Distinguish public thesis from actual investability. Don't infer current dry powder/check availability from old portfolios.

## 9. Vendor / technology research

Record actual functionality, integrations/permissions, data flow, dependencies, lock-in, pricing basis, security/compliance claims, and operational cost. Security/compliance certification claims must be checked against issuer/certificate scope and date. Untried means write "per documentation", never as test results. Don't send user data to a vendor to "try it" without permission.

## 10. Report package

Pick the right sections, write in the user's language unless they ask otherwise; a deep report usually has:

1. Decision question, scope, cutoff date.
2. Conclusion / conditional options.
3. Market grouping and comparison matrix.
4. Pricing / packaging.
5. Customer evidence and counter-evidence.
6. Market sizing model when fitting.
7. Funding, revenue, valuation when relevant.
8. Risk, data gaps, rejected numbers.
9. Method, sources, and access dates.
10. Next step / experiment; don't claim unmeasured outcomes.

When the user wants a proof-based case study, use only real verifiable results: snapshot; baseline; deployment method; quantified result; checkable quotes; takeaway. Missing data means no fabricated quotes, baselines, or ROI.

For substantial market research, produce an HTML file that opens directly on the web and send the verified URL. Prefer existing hosting inside the user-authorized repo/project; keep charts, numbers, tables, and sources consistent with the report. Don't publish sensitive research or create new hosting accounts; without an authorized hosting location, hand over the local HTML and state clearly what is still missing for a web link.
