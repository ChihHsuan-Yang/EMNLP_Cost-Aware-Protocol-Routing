# Security policy

This repository contains research code, analysis scripts, and derived datasets.
It does not run a service, accept untrusted network input, or handle user
credentials, so the usual web-application threat model does not apply.

## Reporting a vulnerability or an exposure

Please email **bellayang@anl.gov** rather than opening a public issue if you
find:

- a credential, API key, token, or private path that we failed to remove from
  the repository, its history, or the released datasets;
- personally identifying information in any released artifact;
- benchmark content whose redistribution we should not have permitted.

We will confirm receipt, remove or restrict the affected artifact, and document
the correction. For accidental credential exposure, please do not include the
secret itself in your report - a file path and line reference is enough.

## Scope

In scope: this repository, the released Hugging Face dataset and model
repositories, and the project website.

Out of scope: vulnerabilities in third-party dependencies (report those
upstream), and the behaviour of the foundation models evaluated in the paper.

## Running untrusted content

The confidence probe prompts in this artifact treat benchmark problem text and
model answers as *untrusted data*, and instruct the model not to follow
instructions contained in them. If you adapt this code, keep that boundary.
