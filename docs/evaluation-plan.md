## Material Passport

Origin Skill: experiment-agent
Origin Mode: plan
Origin Date: 2026-10-23
Verification Status: UNVERIFIED
Version Label: study_protocol_v1

# ResearchScope evaluation plan

The current scores, reading levels, venue suggestions and cited answers need independent judgments before ResearchScope can describe them as useful research guidance. Passing a CLI or browser check establishes that a path works, not that its advice is correct.

The proposed studies do not change product defaults. No participants have been recruited and no study results are reported here. The maintainer must approve the target users, decision thresholds and any paid model use before collection starts.

## Scope and current evidence

Assume the intended users are researchers and graduate students looking for papers in machine learning and related fields. The repository does not establish one target level of expertise. Evaluate introductory reading and specialist discovery separately.

The implementation at commit `a32e4efe95f9841c81cfe065703d3bdbccf8b01f` provides the baseline. Keep the corpus snapshot, configuration, generated outputs and dependency versions with each study run. The following source paths define the decisions under review.

1. [Paper scoring](../src/scoring/scorer.py) combines citation, venue, keyword and other signals. [Search](../backend/app/routers/search.py) adds the paper score to text relevance, while the browser can use a smaller static corpus. Neither a high score nor agreement with the current order is an independent relevance judgment.
2. [Reading levels](../src/difficulty/assessor.py) use text rules and can return Unknown. [Content generation](../src/content/generator.py) distinguishes an unavailable abstract from an excerpt, but the usefulness of generated advice remains unmeasured.
3. [Gap extraction](../src/gaps/gap_extractor.py) groups text cues and topic coverage. A cue can support an author's stated limitation. It does not establish that a proposed question is new.
4. [Venue profiles](../src/sitegen/conference_recommender.py) and the [journal profiles](../src/sitegen/journal_recommender.py) use selected paper text and metadata. [Chat retrieval](../backend/app/services/retrieval_service.py) combines lexical and embedding results. [Citation checks](../backend/app/services/chat_service.py) can detect citation markers without proving that a passage supports a claim.

Local archives, browser subsets and the production database are different populations. Record counts and identifiers for the population actually evaluated. No production coverage claim is possible without access to that population.

## Shared study controls

First, freeze the eligible corpus and group versions of the same work before sampling. Keep a reason for every inclusion, exclusion and unresolved identity. Split by work, not by record, so a preprint and its published version cannot appear on opposite sides of a comparison.

Second, choose task examples without looking at which method wins. Reserve a development set for instructions and thresholds, then lock a separate evaluation set. For historical comparisons, use only records and metadata that were available at the cutoff. Today's citation counts and revised abstracts would leak later information.

Third, use two reviewers who did not implement the method. Show results in a shuffled order and hide method names. Hide citation counts, venue prestige and author names during the initial relevance judgment when the task permits it. Preserve each original judgment before a third reviewer resolves disagreements. Do not treat the resolved judgment as evidence that reviewers originally agreed.

Report missing judgments and inaccessible documents separately from negative judgments. Report results by source, year, topic, publication type and popularity group where there are enough examples. Do not infer a population error rate from a purposive sample.

The proposed samples below are feasibility pilots, not samples justified by a power calculation. Report paired differences and uncertainty at the task or work level. Repeated answers from one work are not independent papers. If a pilot is inconclusive, estimate the required follow up sample from the observed variability and the smallest useful effect agreed with the maintainer. Do not continue collecting until a preferred result appears.

## Discovery and reading order

### Question and hypothesis

Does the current score help a researcher find relevant papers sooner than text relevance alone or publication date? Does the reading score identify an appropriate starting paper for a stated background?

The hypothesis is that the current scores improve the first five results for a stated task. The competing explanation is that they mainly promote popular venues, authors or older papers.

### Sample and method

Use 24 task descriptions, with eight each from language, vision and another covered area such as reinforcement learning. Include both introductory and specialist tasks. Use two tasks per area to refine the instructions and keep the remaining 18 for evaluation. Record the source of every task and the author's assumed background.

For each evaluation task, compare the current search order, text relevance without the added paper score, and newest first among matching papers. Collapse versions within each ranked list before taking its first five works. Pool those works for review, then add the first three works from each reading order comparison for introductory tasks. Remove repeated works within each task's review pool and hide which method selected them. Keep the same eligible corpus and matching rule across methods. Record the actual pool size; the discovery methods contribute at most 270 task and work pairs before overlap removal.

Ask reviewers to rate relevance as 0 for unrelated, 1 for partly useful, 2 for useful and 3 for directly useful. For introductory tasks, separately rate whether the paper is a suitable first reading for the stated background. Reviewers must inspect enough of the original paper to support that decision.

Use the same pooled records to check reading scores and difficulty labels. Record an unsupported or Unknown label separately from an incorrect label. Do not count abstention as a correct prediction.

### Measurements and decision

The primary discovery measure is the number of results rated 2 or 3 in the first five. Report graded ranking gain as a secondary measure, with its exact gain and rank discount formula saved before evaluation. Report first useful rank, reviewer disagreement and source coverage.

For reading order, compare the current reading score with newest first and a simple survey first ordering. Measure the number of suitable starting papers in the first three. Report difficulty agreement and the proportion with a nonempty label.

As a proposed pilot rule, adopt the added paper score only if the lower bound of a 95% paired bootstrap interval for the mean difference in useful results is above zero against both alternatives. Resample the 18 tasks with replacement 10,000 times using a recorded seed. Also require no mean loss of 0.5 or more useful papers against either alternative in any topic or expertise group with at least six tasks. Report smaller groups descriptively without a claim of no harm. Treat the other measures as exploratory. The maintainer must approve these choices before evaluation, including the minimum useful improvement. An inconclusive pilot does not justify a new model or a change of default; plan any further sample from the pilot's variability.

If the current score helps, remove one component at a time on the development tasks before a new evaluation. Start with institution and author prestige, then citation and recency terms. Do not tune the weights on the held out tasks.

## Gap suggestions and novelty

### Question and hypothesis

Can a researcher trace a gap card to a faithful statement in its cited paper? The hypothesis is that the repaired cue grouping produces useful starting points for investigation, without presenting them as verified novel questions.

### Sample and method

Select ten explicit cue cards, ten pattern cue cards and ten starter cards, spread across first topic tag, publication type and attached record count. Record a smaller sample if a type has fewer eligible cards. For explicit and pattern cards, find and inspect the claimed cue in each attached original paper. Compare the card with a simple display of that passage and its bibliographic link. Record a missing or inaccessible passage rather than assuming that an attached paper supports the card.

For explicit and pattern cards, have reviewers assign one of four outcomes. The paper explicitly states the limitation, the card reasonably infers an opportunity, the excerpt does not support the card, or the evidence is insufficient. Record the precise passage and the direction of the claim, including positive results that contradict an alleged limitation. Starter cards are generated topic suggestions with example papers, not attributed limitations. Review whether their wording preserves that distinction and whether their examples fit the topic; exclude them from the attribution accuracy denominator.

Only after that check, select five supported opportunities for a focused novelty investigation. For each opportunity, write one specific question and search its method, task, population and proposed difference. Record the exact academic index queries, dates, exclusions and nearest competing papers. Read the methods and results needed to compare them. A search that finds no match supports only a statement about the searched sources and date.

### Measurements and decision

Report supported cue cards out of the inspected explicit and pattern cards, with wrong attribution, polarity errors, inaccessible evidence and reviewer disagreement. Report starter wording and topic fit separately with their own denominator. Report how many investigated opportunities already have a close answer in the searched literature.

Keep a card only if its wording matches its evidence category. A wrong citation or reversed finding requires a source repair, regardless of average results. Do not introduce a novelty score from this pilot. Retain the review notice until a repeatable search and review process exists.

## Venue suggestions

### Question and hypothesis

Do the suggested venues fit a manuscript's subject and contribution better than broad field matching? The hypothesis concerns scope fit, not acceptance probability.

### Sample and method

Choose 24 recent papers across at least six represented venues and multiple topics. Use only title and abstract as query text, with venue names and explicit acceptance statements removed. Build venue profiles from earlier works. Exclude the query work and every known version from the profiles.

Compare the current venue ranking with a simple field match and an unweighted keyword overlap. Have reviewers judge the first three suggestions against each venue's official aims, scope and submission rules as of the study date. The venue that published a paper is one plausible answer, not the only correct answer.

Use publication venue retrieval as a secondary diagnostic. It cannot measure rejection outcomes or establish a submission success rate.

### Measurements and decision

Report suitable venues in the first three, inappropriate suggestions, missing venues and source coverage. Separate scope fit from deadlines, fees, review duration and bibliometric claims. Verify each displayed operational fact against its own dated official source.

Prefer the current ranking only if it improves scope judgments over both simple alternatives without relying on leaked venue text. Unsupported deadline or journal metric claims need a data repair before the ranking study. Do not add another venue dataset solely to enlarge the venue count.

## Cited answers

### Question and hypothesis

Does a generated answer accurately answer the question, and do its cited passages support its claims? The hypothesis is that the current retrieval combination improves supported answers over lexical retrieval alone.

### Sample and method

Choose 12 papers across at least three sources, two publication types and short and long documents. Record the exact source document version and extraction output. Write three questions per paper before seeing generated answers. Include a factual question, a method or result question, and a question that the paper cannot answer.

Compare current retrieval with lexical retrieval alone only for questions that enter the retrieval path. Before evaluation, verify the query embedding succeeds and record the matching model and dimension coverage of stored chunk vectors. Record failures and fallback calls as failures of the intended comparison, not as hybrid results. Global questions use a separate full context path; report them separately and exclude them from the hybrid comparison. Keep the model, prompt, output limit and document version fixed. Removing the section bonus is a separate comparison only if the first comparison leaves its benefit unresolved. A direct excerpt display is the nonmodel baseline.

Independent reviewers first identify answerable questions and supporting passages from the original document. Then they split each generated answer into factual claims and judge each citation for support. Preserve contradictions, missing citations and claims with no supporting passage. A valid S1 marker is not evidence of support.

### Measurements and decision

Report answer correctness, supported factual claims, citation support, citation coverage and appropriate abstention on unanswerable questions. Measure retrieval of the reference passage separately from generation quality. Also report latency, input and output tokens, failures and cancelled requests.

A provider or retrieval change must not increase unsupported claims in the locked sample. Prefer it only if it improves supported answers or reduces measured cost with equivalent support. A single wrong citation should produce a reproducible case and a repair decision, not be hidden by an average.

No paid or external model call is authorized by this protocol. Until the maintainer approves a provider and content policy, use local contract fixtures only for request, stream, citation and cancellation behavior. Fixture answers do not count as semantic evaluation.

The distinction between answer quality and citation support follows the targeted reading of sections 3.2, 3.3 and 6 and appendices E and F in Gao et al., [Enabling Large Language Models to Generate Text with Citations](https://aclanthology.org/2023.emnlp-main.398/), checked on 23 October 2026. The paper is a method reference; ResearchScope has not reproduced its evaluation.

## Performance and a bounded Rust decision

The actual CLI already has a documented scale concern. One local run on 32,499 output papers took 268.833091 seconds and reached 1,443,600 KiB of peak RSS for the pipeline process. One run is not a stable baseline or evidence for a particular language change.

First, measure the slow stages on the same full workload. Keep fixture responses, archive hashes, output limits and CPU allocation fixed. Separate instrumented diagnosis from unprofiled timing. Check CPU work, allocation, disk and network waits before choosing an optimization.

Second, try the smallest change at the limiting stage. Reuse existing data or avoid duplicate serialization before adding a second runtime. Consider a Rust component only if the measured stage is suitable for a contained replacement and the existing interface can remain unchanged.

Third, compare at least five paired unprofiled runs in alternating order after a warmup. Record wall time and peak memory for the actual pipeline process, plus output counts and normalized content hashes. Exclude only declared volatile timestamps. Preserve identifiers, field types, ordering where users rely on it, failures and partial result behavior.

A proposed acceptance rule is at least 1.25× lower median latency or 20% lower peak memory on the limiting workload, with no correctness difference or material regression in the other measure. The maintainer should approve the threshold against the maintenance cost. Report absolute measurements and baseline time divided by candidate time. Do not infer a production saving from a local fixture.

Keep the current implementation available until packaging and deployment checks pass. A Rust experiment must not silently change the minimum platform, build requirements or output format.

## Dataset decision

Add a dataset only after one of the studies identifies a concrete missing field or coverage gap. Compare a bounded sample with the existing corpus before choosing a connector.

For each candidate, retain original documentation and item identifiers. Measure unique useful records, overlap, version links, missing required fields and freshness. Record access limits and the cost of maintaining updates. Check metadata access, full text access, redistribution and training permission separately. An open metadata API does not establish permission for every full text use.

Prefer fixing a discarded field in an existing connector when it supplies the needed evidence. Keep an unresolved rights question as a blocker, not as an assumed permission.

## Ethics, records and stop conditions

Human study status is ETHICS_BLOCKED. The maintainer has not selected a consent procedure, private storage, access policy or retention period. Institutional approval or exemption has not been assessed. The applicable institution must determine whether review is required.

Planning can continue, but participant recruitment and data collection must wait. Use adult volunteers with relevant background, avoid recruiting anyone whose grades or employment depend on participation, and record voluntary withdrawal terms. Do not put identities, private manuscripts or raw participant records in Git or send them to model services.

Before collection, name the study owner and approve the consent text, risk assessment, storage and deletion plan. Keep pseudonymous judgments separately from contact details. Record missing data without inventing replacements. Decide whether any anonymized results may be shared.

Stop a study if its reference evidence cannot be inspected, its corpus changes, a work appears in both development and evaluation sets, or a required permission is missing. Repair the protocol before continuing. Do not change a decision rule after viewing evaluation outcomes.

## Review and delivery

Keep the approved protocol, source and input hashes, sampling manifest, method versions and analysis choices with the results. Report each study's actual denominator and exclusions. Distinguish executable checks, independent judgments and deployment observations.

The discovery measure uses graded relevance as a secondary view, informed by the abstract of Järvelin and Kekäläinen, [Cumulated gain based evaluation of IR techniques](https://doi.org/10.1145/582415.582418), checked on 23 October 2026. Only the publication record and abstract were read. The sample sizes and decision rules here are proposed project choices, not thresholds taken from that paper.

Run the discovery and reading pilot first because those scores affect several downstream views. Run the gap and cited answer checks before making stronger claims about either feature. Defer model replacement, broader datasets and a Rust port until the relevant comparison supports them.
