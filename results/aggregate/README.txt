Ancillary aggregate results for
"LLMs Can Predict Failure Risk, But Struggle to Predict Which Collaboration
Protocol Pays Off: Cost-Aware Protocol Routing Across Reasoning Tasks."

Files
-----
main_routing_heldout.csv
  Representative policies on the primary 423-problem held-out split.

matched_protocol_coverage.csv
  Four-protocol solve rates and fixed-order-oracle coverage for the 10 paired
  model-condition settings.

oracle_label_distribution.csv
  Fixed-order-oracle label percentages for the same 10 paired settings.

postanswer_confidence.csv
  Post-answer, pre-collaboration failure-risk metrics for six settings.

failure_and_protocol_value_targets.csv
  The same no-leakage failure score evaluated against failure and increasingly
  protocol-specific collaboration-value targets.

heldout_router_evaluation.csv
  Text-and-metadata router results on identical held-out problem identifiers.

heldout_router_paired_differences.csv
  Paired solve-rate differences against Tier-majority and Baseline.

per_broadcast_interaction.csv
  PER and Broadcast outcomes conditional on Baseline and Single both failing.

Conventions
-----------
Rates are proportions unless a column name ends in "_pct" or "_points".
Confidence intervals are 95 percent percentile intervals from 2,000
problem-level bootstrap resamples. Oracle means the first successful protocol
in the fixed order Baseline, Single, PER, Broadcast; None means all four fail.
These files contain aggregate results only. The companion dataset archive named
in the paper provides trace and per-problem outcome artifacts subject to each
upstream benchmark's terms.
