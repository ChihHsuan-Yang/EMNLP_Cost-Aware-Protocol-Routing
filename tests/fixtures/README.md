# Fixtures

Six SYNTHETIC problems, written for this release. They contain NO text from
Omni-MATH, JEEBench, SciBench or LAB-Bench, and nothing here is a benchmark
item. Their only purpose is to let the mock backend exercise the four-protocol
pipeline end to end with zero network and zero cost.

`tiny_math.jsonl` follows the omni-math on-disk schema, including the quirk
that matters most: `answer` is the literal string `"None"` and the real gold
value lives in `answer_number`. A loader that reads `answer` first scores the
whole file against `"None"`, which is exactly the failure this fixture exists
to catch.
