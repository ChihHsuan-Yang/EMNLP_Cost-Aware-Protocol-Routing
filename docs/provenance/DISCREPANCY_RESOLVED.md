# Resolved: routing_benchmark.csv (May) vs matched_labels (camera-ready), OmniMath / gpt-oss-120b

## Verdict
SAME underlying protocol executions, DIFFERENT baseline scoring version.
The camera-ready matched_labels file is authoritative. The May-era
routing_benchmark.csv must NOT be released as the matched-outcome table.

## Evidence
Join: the two artifacts share no usable ID space (`global_example_idx` in
routing_benchmark.csv is per-tier, not global: 1106 unique values over 4181 rows).
Joined instead on whitespace-normalised problem text via the Aurora probe_inputs.jsonl,
which carries BOTH the text and the camera-ready `problem_uid`: 4181/4181 matched.

CAUTION recorded: 13 problem texts are duplicated (4168 unique texts over 4181 rows)
on BOTH sides, with identical group sizes. A naive row-wise text join therefore
reports 4 baseline disagreements; the correct per-group multiset comparison reports 3,
which is the true figure and matches the net count delta exactly. The spurious 4th
(tier02:226 / omni2_3199) was a mis-pairing inside a duplicate-text group.

## The 3 differing problems (outcome tuple = baseline,single,PER,broadcast)
| May id    | camera-ready uid | May             | camera-ready    |
|-----------|------------------|-----------------|-----------------|
| tier08:37 | omni2_94         | F,T,T,T         | T,T,T,T         |
| tier09:85 | omni2_3997       | F,T,T,T         | T,F,T,T         |
| tier09:86 | omni2_4006       | F,T,T,T         | T,T,T,T         |

All three are baseline re-scored False -> True. PER and Broadcast outcomes are
IDENTICAL across all 4181 problems in both artifacts (0 disagreements).
Single differs on exactly 1 problem (omni2_3997).

Net effect on the headline table: baseline 2373 -> 2376 (56.76% -> 56.83%),
single_agent oracle label 961 -> 958. PER 366, Broadcast 175, None 306 unchanged.
56.83% is the camera-ready published value and is the one that reproduces.

## Consequence for the release
- data/matched_labels.csv MUST come from the camera-ready matched_labels files.
- routing_benchmark.csv may be released only as the PRIMARY-SPLIT (n=423, seed 42)
  study input, clearly dated and labelled as the earlier scoring pass, or omitted.
- Document this in docs/provenance.md so a reader who finds both is not misled.
